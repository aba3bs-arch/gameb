"""Genera el PNG de cada pieza igual al boceto, dentro del estudio.

ChatGPT no dibuja estas imágenes. El color sale del propio boceto.
Si el contorno exterior es un cuadrado, el PNG es ese cuadrado entero.
Si no lo es, el PNG sigue ese contorno y lo de afuera queda transparente.
"""
import base64
import io

from studio.datos import decode_data
from studio.desarmar.recortar import (
    Image,
    _clase_de_pieza,
    _cuadrado_de_simbolo,
    _es_simbolo,
    _need_numpy,
    _recortar_cuadrado,
    _recortar_desde_el_borde,
    _recortar_silueta,
    _segment_cutout,
)


def _colores_del_boceto(source, pieza, trim_x, trim_y):
    """El cuerpo de la pieza conserva el color del boceto. El filo ya separado no se vuelve a pintar."""
    np = _need_numpy()
    src = np.array(source.convert('RGBA'))
    out = np.array(pieza.convert('RGBA'))
    alto, ancho = out.shape[:2]
    y0, x0 = max(0, int(trim_y)), max(0, int(trim_x))
    y1, x1 = min(src.shape[0], y0 + alto), min(src.shape[1], x0 + ancho)
    if y1 <= y0 or x1 <= x0:
        return pieza
    solido = out[:y1 - y0, :x1 - x0, 3] >= 200
    out[:y1 - y0, :x1 - x0, :3][solido] = src[y0:y1, x0:x1, :3][solido]
    return Image.fromarray(out, 'RGBA')


def _separar(source, kind, inner):
    clase = _clase_de_pieza(kind)
    if clase == 'fondo':
        return source, {'trimX': 0, 'trimY': 0, 'engine': 'fondo', 'removedFragments': 0}
    if clase in ('placa', 'marco'):
        return _recortar_desde_el_borde(source, clase, inner)
    np = _need_numpy()
    rect = _cuadrado_de_simbolo(np.array(source.convert('RGB')), inner) if _es_simbolo(kind) else None
    if rect is not None:
        return _recortar_cuadrado(source, rect)
    result, info = _recortar_silueta(source, inner)
    if not info.get('usable'):
        result, info = _segment_cutout(source, inner, kind)
    return result, info


def generar_pieza(data):
    """Respuesta de POST /api/generate-piece. No llama a ChatGPT."""
    if Image is None:
        return 503, {'ok': False, 'error': 'Falta Pillow. Instala las dependencias del proyecto.'}
    try:
        _head, raw = decode_data(data.get('image', ''))
        if len(raw) > 15 * 1024 * 1024:
            return 413, {'ok': False, 'error': 'El recorte supera 15 MB.'}
        source = Image.open(io.BytesIO(raw)).convert('RGBA')
        if source.width < 2 or source.height < 2:
            return 400, {'ok': False, 'error': 'El recorte está vacío o sus dimensiones no son válidas.'}
        kind = str(data.get('kind') or '')[:80]
        result, info = _separar(source, kind, data.get('inner'))
        if _clase_de_pieza(kind) != 'fondo':
            result = _colores_del_boceto(source, result, info.get('trimX', 0), info.get('trimY', 0))
        from studio.desarmar.catalogo import aplicar_lamina
        result = aplicar_lamina(
            result,
            info.get('trimX', 0),
            info.get('trimY', 0),
            data.get('hole'),
            data.get('erase'),
            kind,
        )
        out = io.BytesIO()
        result.save(out, format='PNG', optimize=True)
        encoded = base64.b64encode(out.getvalue()).decode('ascii')
        nota = 'La escena se deja entera.' if _clase_de_pieza(kind) == 'fondo' else 'Generada en el estudio, con los colores del boceto.'
        return 200, {
            'ok': True,
            'image': 'data:image/png;base64,' + encoded,
            'width': result.width,
            'height': result.height,
            'trimX': info.get('trimX', 0),
            'trimY': info.get('trimY', 0),
            'engine': 'generado' if _clase_de_pieza(kind) != 'fondo' else 'fondo',
            'removedFragments': info.get('removedFragments', 0),
            'alphaMatting': False,
            'nota': nota,
        }
    except Exception as exc:
        return 502, {'ok': False, 'error': 'No se pudo generar la pieza: ' + str(exc)[:300]}
