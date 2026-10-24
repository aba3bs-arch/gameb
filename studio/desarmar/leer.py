"""Pide a la IA la lista de piezas y las palabras del título. No acepta el rectángulo final."""
import io
import json
import os
import re

from studio.auth import access_token
from studio.datos import decode_data
from studio.desarmar.catalogo import CATALOGO, preparar_catalogo
from studio.desarmar.recortar import Image
from studio.desarmar.unir import LEER_TITULO, _is_title_kind, unir_titulo
from studio.openai_client import choose_model, openai_response

TIPOS = ['Fondo', 'Título / logo', 'Marco de rodillos', 'Símbolo', 'Jackpot', 'Botón', 'Contador', 'Panel', 'Bonus', 'Decoración', 'Efecto', 'Otro']


def fallback_components(width=1000, height=600, cols=5, rows=3):
    items = [
        {'id': 'background', 'name': 'Fondo principal', 'type': 'Fondo', 'x': 0, 'y': 0, 'w': width, 'h': height, 'confidence': 0.35},
        {'id': 'title', 'name': 'Título / logotipo', 'type': 'Título / logo', 'x': int(width * .28), 'y': int(height * .02), 'w': int(width * .44), 'h': int(height * .13), 'confidence': 0.25},
        {'id': 'reels_frame', 'name': 'Marco de rodillos', 'type': 'Marco de rodillos', 'x': int(width * .25), 'y': int(height * .2), 'w': int(width * .5), 'h': int(height * .55), 'confidence': 0.25},
    ]
    cw = width * .5 / cols
    ch = height * .55 / rows
    for row in range(rows):
        for col in range(cols):
            items.append({
                'id': f'cell_{row * cols + col + 1}',
                'name': f'Celda {row * cols + col + 1}',
                'type': 'Símbolo',
                'x': int(width * .25 + col * cw),
                'y': int(height * .2 + row * ch),
                'w': int(cw),
                'h': int(ch),
                'confidence': 0.2,
            })
    items += [
        {'id': 'jackpot_grand', 'name': 'Jackpot GRAND', 'type': 'Jackpot', 'x': int(width * .04), 'y': int(height * .1), 'w': int(width * .18), 'h': int(height * .1), 'confidence': 0.2},
        {'id': 'spin_button', 'name': 'Botón girar', 'type': 'Botón', 'x': int(width * .78), 'y': int(height * .78), 'w': int(width * .16), 'h': int(height * .15), 'confidence': 0.2},
        {'id': 'credits_counter', 'name': 'Contador de créditos', 'type': 'Contador', 'x': int(width * .38), 'y': int(height * .85), 'w': int(width * .22), 'h': int(height * .08), 'confidence': 0.2},
    ]
    return items


def _numero(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _cajas_en(raw):
    """Cajas del componente, de sus partes y del hueco, sin recortarlas todavía."""
    if not isinstance(raw, dict):
        return []
    boxes = []
    nums = [_numero(raw.get(key)) for key in ('x', 'y', 'w', 'h')]
    if all(num is not None for num in nums) and nums[2] > 0 and nums[3] > 0:
        boxes.append(tuple(nums))
    for key in ('hole', 'hueco'):
        boxes.extend(_cajas_en(raw.get(key)))
    parts = raw.get('parts')
    if isinstance(parts, list):
        for part in parts[:16]:
            boxes.extend(_cajas_en(part))
    return boxes


def _escala_del_boceto(components, width, height):
    """Lleva las cajas al tamaño real. El modelo a veces usa 0–1, 0–100, 0–1000 u otra foto más chica."""
    if not isinstance(components, list) or width < 2 or height < 2:
        return 1.0, 1.0
    boxes = []
    for raw in components:
        boxes.extend(_cajas_en(raw))
    if not boxes:
        return 1.0, 1.0
    max_x = max(max(x, w, x + w) for x, _y, w, _h in boxes)
    max_y = max(max(y, h, y + h) for _x, y, _w, h in boxes)
    if max_x <= 1.5 and max_y <= 1.5:
        return float(width), float(height)
    spans_hundred = any(w >= 90 or h >= 90 for _x, _y, w, h in boxes)
    if max_x <= 100 and max_y <= 100 and spans_hundred and width > 150 and height > 150:
        return width / 100.0, height / 100.0
    parece_mil = max_x <= 1050 and max_y <= 1050 and max_x >= 500 and max_y >= 300
    cabe = max_x <= width * 1.04 and max_y <= height * 1.04
    cerca_de_mil = abs(max_x - 1000) <= 80 and abs(max_y - 1000) <= 120
    imagen_distinta = abs(width - 1000) > 60 or abs(height - 1000) > 60
    if parece_mil and (not cabe or (cerca_de_mil and imagen_distinta)):
        return width / 1000.0, height / 1000.0
    if max_x >= 80 and max_y >= 80 and max_x < width * 0.78 and max_y < height * 0.78:
        sx = width / max_x
        sy = height / max_y
        if 1.05 < sx < 8 and 1.05 < sy < 8 and abs(sx - sy) / max(sx, sy) <= 0.12:
            return sx, sy
    if max_x > width * 1.12 and max_y > height * 1.12:
        sx = width / max_x
        sy = height / max_y
        if 0.15 <= sx <= 1 and 0.15 <= sy <= 1 and abs(sx - sy) / max(sx, sy) <= 0.35:
            return sx, sy
    return 1.0, 1.0


def _escalar_caja(raw, sx, sy):
    if not isinstance(raw, dict) or (sx == 1 and sy == 1):
        return
    for key, scale in (('x', sx), ('y', sy), ('w', sx), ('h', sy)):
        value = _numero(raw.get(key))
        if value is not None:
            raw[key] = int(round(value * scale))
    for key in ('hole', 'hueco'):
        _escalar_caja(raw.get(key), sx, sy)
    parts = raw.get('parts')
    if isinstance(parts, list):
        for part in parts[:16]:
            _escalar_caja(part, sx, sy)


def _normalizar(raw, index, width, height):
    try:
        x = max(0, min(width, int(raw.get('x', 0))))
        y = max(0, min(height, int(raw.get('y', 0))))
        w = max(1, min(width - x, int(raw.get('w', 1))))
        h = max(1, min(height - y, int(raw.get('h', 1))))
    except Exception:
        return None
    tipo = raw.get('type') if raw.get('type') in TIPOS else 'Otro'
    nombre = str(raw.get('name') or f'Componente {index + 1}')[:100]
    ident = re.sub('[^a-zA-Z0-9_]+', '_', str(raw.get('id') or f'component_{index + 1}')).strip('_')[:60] or f'component_{index + 1}'
    try:
        confidence = max(0, min(1, float(raw.get('confidence', .5))))
    except (TypeError, ValueError):
        confidence = .5
    comp = {'id': ident, 'name': nombre, 'type': tipo, 'x': x, 'y': y, 'w': w, 'h': h, 'confidence': confidence}
    if isinstance(raw.get('parts'), list):
        comp['_parts'] = raw.get('parts')
    hole = raw.get('hole') if isinstance(raw.get('hole'), dict) else raw.get('hueco')
    if isinstance(hole, dict):
        comp['_hole'] = hole
    return comp


def _aplicar_titulo(comp, raw, width, height):
    united = unir_titulo(raw if isinstance(raw, dict) else {}, width, height)
    comp['titleWords'] = united['titleWords']
    comp['titleOrnaments'] = united['titleOrnaments']
    comp['titleReviewed'] = True
    comp['titleFailed'] = united['titleFailed']
    comp['titleReason'] = united['titleReason']
    comp['skipSave'] = united['skipSave']
    if 'x' in united:
        comp['x'], comp['y'], comp['w'], comp['h'] = united['x'], united['y'], united['w'], united['h']
    if united['titleWords'] and not united['titleFailed']:
        comp['name'] = ' '.join(united['titleWords'])
    return comp


def analyze_with_openai(image_data, name, cols, rows, notes):
    token = access_token()
    auth_mode = 'chatgpt'
    if not token:
        key = os.environ.get('OPENAI_API_KEY', '').strip()
        if not key:
            return None
        token = key
        auth_mode = 'api'
    head, raw = decode_data(image_data)
    width, height = 1000, 600
    if Image:
        try:
            width, height = Image.open(io.BytesIO(raw)).size
        except Exception:
            pass
    prompt = f"""Actúa como un sistema profesional de segmentación de assets para videojuegos. Analiza toda la imagen primero e identifica cada componente visible por separado. Devuelve SOLO JSON válido con shape {{"summary":"...","components":[{{"id":"snake_case","name":"nombre español","type":"Fondo|Título / logo|Marco de rodillos|Símbolo|Jackpot|Botón|Contador|Panel","x":int,"y":int,"w":int,"h":int,"confidence":0.0,"hole":{{"x":int,"y":int,"w":int,"h":int}},"parts":[{{"text":"PALABRA","role":"palabra|adorno|cifra","x":int,"y":int,"w":int,"h":int,"missing":false}}]}}]}}. La imagen mide exactamente {width} píxeles de ancho y {height} de alto. x, y, w y h son enteros en ESOS píxeles, para cualquier boceto y cualquier pieza: fondo, título, cada jackpot, marco, cada símbolo, cada botón y cada panel. El origen es la esquina superior izquierda. x+w no pasa de {width} y y+h no pasa de {height}. Una caja que solo cubre la palabra o el centro deja la pieza incompleta: la caja llega hasta el borde visible del objeto, adornos incluidos. El fondo completo es x=0, y=0, w={width}, h={height}. Las partes y el hole usan la misma medida. {LEER_TITULO} {CATALOGO} REGLAS OBLIGATORIAS: (1) Si dos objetos se tocan o están muy juntos, NO los unas en una sola pieza: crea una caja independiente por objeto, aunque sus cajas se solapen un poco. El título no se entrega como un rectángulo final: sus palabras y adornos van en parts y el programa los une. (2) La caja debe abarcar el COMPONENTE VISUAL COMPLETO, no solo el texto o la parte central. En un título, cada parte cubre esa palabra o ese adorno completo. (3) No uses una caja enorme que incluya varios componentes distintos. (4) Identifica y separa primero las piezas de primer plano; trata el fondo/escena como una capa independiente al final. (5) En grupos de símbolos repetidos, devuelve una caja por símbolo. (6) Si una frontera no puede determinarse con seguridad, conserva la caja individual más razonable y baja confidence. Si una palabra del título no tiene frontera, márcala missing true. (7) No inventes píxeles ocultos. Si las notas piden una sola caja para el título, ignóralas: parts manda. Columna/filas esperadas {cols}x{rows}. Nombre del juego: {name or 'sin nombre'}. Notas adicionales: {notes}. No incluyas decoración, efectos, pedazos de paisaje ni los tipos Otro o Bonus. Si un dibujo no es fondo, título, marco, símbolo de rodillo, jackpot, botón, panel o letrero de líneas, no lo pongas en la lista. Máximo 80 componentes. Si la imagen es boceto, identifica regiones propuestas, no afirmes que son PNG ya extraídos."""
    body = {
        'model': choose_model(token),
        'input': [{'role': 'user', 'content': [
            {'type': 'input_text', 'text': prompt},
            {'type': 'input_image', 'image_url': image_data, 'detail': 'high'},
        ]}],
        'text': {'format': {'type': 'json_object'}},
    }
    parsed = json.loads(openai_response(body, token))
    encontrados = parsed.get('components', [])
    if not isinstance(encontrados, list):
        encontrados = []
    sx, sy = _escala_del_boceto(encontrados, width, height)
    scale_notes = []
    if abs(sx - 1) > 0.01 or abs(sy - 1) > 0.01:
        for raw_component in encontrados:
            _escalar_caja(raw_component, sx, sy)
        scale_notes.append('Las cajas se ajustaron al tamaño real de la imagen, ' + str(width) + '×' + str(height) + ' px.')
    comps = []
    title_notes = []
    for index, raw_component in enumerate(encontrados[:80]):
        if not isinstance(raw_component, dict):
            continue
        comp = _normalizar(raw_component, index, width, height)
        if not comp:
            continue
        if _is_title_kind(comp.get('type')) or _is_title_kind(comp.get('name')):
            _aplicar_titulo(comp, raw_component, width, height)
            title_notes.append('Título «' + comp['name'] + '»: ' + comp['titleReason'])
        comps.append(comp)
    comps, catalog_notes = preparar_catalogo(comps, width, height)
    summary = str(parsed.get('summary', 'Análisis terminado. Revisa todas las cajas antes de extraer.'))
    extras = scale_notes + title_notes + catalog_notes
    if extras:
        summary = summary + ' ' + ' '.join(extras)
    return {
        'summary': summary,
        'components': comps,
        'aiUsed': True,
        'authMode': auth_mode,
        'imageWidth': width,
        'imageHeight': height,
    }


def analizar(data):
    head, raw = decode_data(data.get('image', ''))
    width, height = 1000, 600
    if Image:
        image = Image.open(io.BytesIO(raw))
        width, height = image.size
    try:
        columns = int(data.get('columns', 5))
        rows = int(data.get('rows', 3))
        result = analyze_with_openai(data.get('image', ''), data.get('name', ''), columns, rows, data.get('notes', ''))
    except Exception as exc:
        return 502, {'error': str(exc)}
    if result is None:
        components, catalog_notes = preparar_catalogo(
            fallback_components(width, height, int(data.get('columns', 5)), int(data.get('rows', 3))),
            width,
            height,
        )
        summary = 'No hay OPENAI_API_KEY en el entorno. Se muestra una plantilla geométrica de respaldo, no una detección IA. Ajusta las cajas manualmente.'
        if catalog_notes:
            summary = summary + ' ' + ' '.join(catalog_notes)
        result = {
            'summary': summary,
            'components': components,
            'aiUsed': False,
            'imageWidth': width,
            'imageHeight': height,
        }
    return 200, result
