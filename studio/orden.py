"""El orden de las imágenes. El estudio lo sigue de la primera a la última.

ChatGPT solo dice dónde está cada pieza. No dibuja los PNG.
"""
import io
import json
import os
import re

from PIL import Image

from studio.auth import access_token
from studio.datos import decode_data
from studio.openai_client import choose_model, openai_response

PASOS = (
    'Primero: el fondo, la escena completa.',
    'Después: el título o el logo.',
    'Después: cada placa, una por una.',
    'Después: el marco de los rodillos, si hay.',
    'Después: cada símbolo, de izquierda a derecha y de arriba abajo.',
    'Después: cada botón.',
    'Después: cada panel.',
    'Al final: los letreros de líneas.',
)

_RANGO = (
    ('fondo', 0),
    ('titulo', 1),
    ('logo', 1),
    ('jackpot', 2),
    ('placa', 2),
    ('marco', 3),
    ('simbolo', 4),
    ('boton', 5),
    ('panel', 6),
    ('letrero', 7),
    ('linea', 7),
)
_PAISAJE = ('escena', 'paisaje', 'cielo', 'ciudad', 'edificio', 'decoracion', 'ambiente', 'nube')


def _numero(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _plegar(text):
    return str(text or '').lower().replace('í', 'i').replace('ó', 'o').replace('á', 'a').replace('é', 'e').replace('ú', 'u')


def _rango(piece):
    texto = _plegar(piece.get('type', '') + ' ' + piece.get('name', ''))
    for palabra, puesto in _RANGO:
        if palabra in texto:
            return puesto
    return 9


def _escala(pieces, width, height):
    boxes = []
    for piece in pieces:
        nums = [_numero(piece.get(key)) for key in ('x', 'y', 'w', 'h')]
        if all(num is not None for num in nums) and nums[2] > 0 and nums[3] > 0:
            boxes.append(tuple(nums))
    if not boxes or width < 2 or height < 2:
        return 1.0, 1.0
    max_x = max(max(x, w, x + w) for x, _y, w, _h in boxes)
    max_y = max(max(y, h, y + h) for _x, y, _w, h in boxes)
    if max_x <= 1.5 and max_y <= 1.5:
        return float(width), float(height)
    if max_x <= 100 and max_y <= 100 and any(w >= 90 or h >= 90 for _x, _y, w, h in boxes) and width > 150 and height > 150:
        return width / 100.0, height / 100.0
    parece_mil = max_x <= 1050 and max_y <= 1050 and max_x >= 500 and max_y >= 300
    cabe = max_x <= width * 1.04 and max_y <= height * 1.04
    cerca_de_mil = abs(max_x - 1000) <= 80 and abs(max_y - 1000) <= 120
    imagen_distinta = abs(width - 1000) > 60 or abs(height - 1000) > 60
    if parece_mil and (not cabe or (cerca_de_mil and imagen_distinta)):
        return width / 1000.0, height / 1000.0
    if max_x >= 80 and max_y >= 80 and max_x < width * 0.78 and max_y < height * 0.78:
        sx, sy = width / max_x, height / max_y
        if 1.05 < sx < 8 and 1.05 < sy < 8 and abs(sx - sy) / max(sx, sy) <= 0.12:
            return sx, sy
    return 1.0, 1.0


def _es_paisaje(piece):
    if _rango(piece) != 4:
        return False
    texto = _plegar(piece.get('name', ''))
    return any(palabra in texto for palabra in _PAISAJE)


def preparar(pieces, width, height):
    """Deja una sola lista, en el orden fijo, con cajas en píxeles reales."""
    if not isinstance(pieces, list):
        pieces = []
    sx, sy = _escala(pieces, width, height)
    limpias = []
    for raw in pieces:
        if not isinstance(raw, dict) or _es_paisaje(raw):
            continue
        if _rango(raw) > 7:
            continue
        x, y, w, h = (_numero(raw.get(key)) for key in ('x', 'y', 'w', 'h'))
        if None in (x, y, w, h) or w <= 0 or h <= 0:
            continue
        x, y, w, h = int(round(x * sx)), int(round(y * sy)), int(round(w * sx)), int(round(h * sy))
        x = max(0, min(width - 1, x))
        y = max(0, min(height - 1, y))
        w = max(1, min(width - x, w))
        h = max(1, min(height - y, h))
        limpias.append({
            'name': str(raw.get('name') or 'pieza')[:80],
            'type': str(raw.get('type') or 'Símbolo')[:40],
            'x': x,
            'y': y,
            'w': w,
            'h': h,
        })
    fondos = [piece for piece in limpias if _rango(piece) == 0]
    if len(fondos) > 1:
        mejor = max(fondos, key=lambda piece: piece['w'] * piece['h'])
        limpias = [piece for piece in limpias if _rango(piece) != 0 or piece is mejor]
    limpias.sort(key=lambda piece: (_rango(piece), piece['y'], piece['x']))
    return limpias


def _instruccion(width, height):
    pasos = ' '.join(str(indice) + '. ' + texto for indice, texto in enumerate(PASOS, 1))
    return (
        'Mira el boceto y devuelve SOLO JSON con forma '
        '{"pieces":[{"name":"nombre","type":"Fondo|Título|Marco|Símbolo|Jackpot|Botón|Panel|Letrero","x":0,"y":0,"w":0,"h":0}]}. '
        f'La imagen mide {width} por {height} píxeles. x, y, w y h van en esos píxeles. '
        'Sigue este orden y no agregues piezas de más. ' + pasos + ' '
        'Un objeto es una imagen. No partas el paisaje. No conviertas el monto de una placa en una pieza. '
        'En un símbolo, si el contorno exterior es un cuadrado, la caja es ese cuadrado completo. '
        'Si no es un cuadrado, la caja sigue el contorno. No busques un dibujo concreto. Máximo 40 piezas.'
    )


def ordenar(data):
    """Respuesta de POST /api/orden."""
    token = access_token()
    if not token:
        token = os.environ.get('OPENAI_API_KEY', '').strip()
    if not token:
        return 401, {'ok': False, 'error': 'Conecta ChatGPT en la página principal. Solo se usa para ubicar las piezas. Las imágenes las hace el estudio, una por una.'}
    try:
        _head, raw = decode_data(data.get('image', ''))
        image = Image.open(io.BytesIO(raw))
        width, height = image.size
    except Exception:
        return 400, {'ok': False, 'error': 'No se pudo leer el boceto.'}
    body = {
        'model': choose_model(token),
        'input': [{'role': 'user', 'content': [
            {'type': 'input_text', 'text': _instruccion(width, height)},
            {'type': 'input_image', 'image_url': data.get('image'), 'detail': 'high'},
        ]}],
        'text': {'format': {'type': 'json_object'}},
    }
    try:
        parsed = json.loads(openai_response(body, token, timeout=120))
    except Exception as exc:
        return 502, {'ok': False, 'error': str(exc)[:300]}
    encontrados = parsed.get('pieces', parsed.get('components', []))
    pieces = preparar(encontrados, width, height)
    if not pieces:
        return 502, {'ok': False, 'error': 'No se encontró ninguna pieza en el boceto.'}
    return 200, {'ok': True, 'pasos': list(PASOS), 'pieces': pieces, 'width': width, 'height': height}
