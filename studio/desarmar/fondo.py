"""Rellena el hueco que dejan las piezas ya recortadas."""
import io
from studio.datos import decode_data
from studio.desarmar.recortar import Image, _need_numpy, _shift_color, _dilate_bool

def _resize_rgb(arr, size):
    np = _need_numpy()
    resample = Image.Resampling.BILINEAR if hasattr(Image, 'Resampling') else Image.BILINEAR
    image = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), 'RGB')
    return np.asarray(image.resize(size, resample), np.float32)

def _resize_mask(mask, size):
    np = _need_numpy()
    resample = Image.Resampling.NEAREST if hasattr(Image, 'Resampling') else Image.NEAREST
    image = Image.fromarray(mask.astype(np.uint8) * 255, 'L')
    return np.asarray(image.resize(size, resample)) > 127

def _smooth_hole(rgb, hole, times):
    np = _need_numpy()
    filled = rgb
    for _ in range(times):
        acc = np.zeros_like(filled)
        for dy, dx in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            acc += _shift_color(filled, dy, dx)
        nxt = filled.copy()
        nxt[hole] = (acc / 4.0)[hole]
        filled = nxt
    return filled

def _pyramid_fill(rgb, hole):
    np = _need_numpy()
    stack = []
    cur_rgb, cur_hole = rgb, hole
    while max(cur_rgb.shape[:2]) > 32 and np.any(cur_hole):
        nh = max(1, cur_rgb.shape[0] // 2)
        nw = max(1, cur_rgb.shape[1] // 2)
        stack.append((cur_rgb, cur_hole))
        cur_rgb = _resize_rgb(cur_rgb, (nw, nh))
        cur_hole = _resize_mask(cur_hole, (nw, nh))
    if np.any(~cur_hole):
        mean = cur_rgb[~cur_hole].reshape(-1, 3).mean(axis=0)
    else:
        mean = np.zeros(3, np.float32)
    filled = cur_rgb.copy()
    filled[cur_hole] = mean
    filled = _smooth_hole(filled, cur_hole, 8)
    while stack:
        up_rgb, up_hole = stack.pop()
        upsampled = _resize_rgb(filled, (up_rgb.shape[1], up_rgb.shape[0]))
        filled = up_rgb.copy()
        filled[up_hole] = upsampled[up_hole]
        filled = _smooth_hole(filled, up_hole, 4)
    return filled

def clean_background(source_rgba, mask_rgba):
    """Quita las piezas ya recortadas y rellena esa zona con la escena de alrededor."""
    np = _need_numpy()
    if Image is None:
        raise RuntimeError('Falta Pillow.')
    source_rgba = source_rgba.convert('RGBA')
    mask_rgba = mask_rgba.convert('RGBA')
    if mask_rgba.size != source_rgba.size:
        resample = Image.Resampling.NEAREST if hasattr(Image, 'Resampling') else Image.NEAREST
        mask_rgba = mask_rgba.resize(source_rgba.size, resample)
    alpha = np.asarray(mask_rgba)[:, :, 3]
    hole = _dilate_bool(alpha > 16, 3)
    ratio = float(hole.mean()) if hole.size else 0.0
    if ratio < 0.002:
        raise RuntimeError('No hay piezas recortadas para retirar del fondo.')
    if ratio > 0.72:
        raise RuntimeError('Las piezas cubren casi toda la imagen; no queda escena suficiente para reconstruir el fondo.')
    src = np.asarray(source_rgba.convert('RGB'), np.float32)
    filled = _pyramid_fill(src, hole)
    rgb = np.asarray(source_rgba.convert('RGB')).copy()
    rgb[hole] = np.clip(filled[hole], 0, 255).astype(np.uint8)
    opaque = np.full(hole.shape, 255, np.uint8)
    return Image.fromarray(np.dstack([rgb, opaque]), 'RGBA')


def limpiar(data):
    """Respuesta de POST /api/clean-background."""
    if Image is None:
        return 503, {'ok': False, 'error': 'Falta Pillow. Instala las dependencias del proyecto.'}
    try:
        head, raw = decode_data(data.get('image', ''))
        if len(raw) > 30 * 1024 * 1024:
            return 413, {'ok': False, 'error': 'La imagen del fondo supera el tamaño permitido.'}
        source = Image.open(io.BytesIO(raw)).convert('RGBA')
        _, mraw = decode_data(data.get('mask', ''))
        if len(mraw) > 30 * 1024 * 1024:
            return 413, {'ok': False, 'error': 'La máscara del fondo supera el tamaño permitido.'}
        mask = Image.open(io.BytesIO(mraw)).convert('RGBA')
        result = clean_background(source, mask)
        out = io.BytesIO()
        result.save(out, format='PNG', optimize=True)
        import base64
        encoded = base64.b64encode(out.getvalue()).decode('ascii')
        return 200, {'ok': True, 'image': 'data:image/png;base64,' + encoded, 'width': result.width, 'height': result.height}
    except Exception as exc:
        return 502, {'ok': False, 'error': 'No se pudo reconstruir el fondo: ' + str(exc)[:300]}
