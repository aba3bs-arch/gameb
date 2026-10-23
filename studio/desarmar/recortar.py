"""Recorte de cada pieza y recuperación de letras que la máscara se comió."""
import io, threading
try:
    from PIL import Image
except Exception:
    Image = None
from studio.datos import decode_data
from studio.desarmar.unir import _is_title_kind

# Reutiliza cada modelo de segmentación. isnet conserva mejor letras y adornos que u2net.
_REMBG_SESSIONS = {}
_REMBG_FAILED = set()
_REMBG_SESSION_LOCK = threading.RLock()
_SEGMENT_MODELS = ('isnet-general-use', 'u2net')

def _get_rembg_session(new_session, model_name):
    """Inicializa una sesión de rembg bajo bloqueo; no oculta errores del modelo."""
    with _REMBG_SESSION_LOCK:
        if model_name in _REMBG_SESSIONS:
            return _REMBG_SESSIONS[model_name]
        if model_name in _REMBG_FAILED:
            raise RuntimeError('El modelo '+model_name+' no está disponible en este equipo.')
        try:
            session = new_session(model_name)
        except Exception as exc:
            _REMBG_FAILED.add(model_name)
            raise RuntimeError('No se pudo cargar '+model_name+': '+str(exc)[:180])
        if session is None:
            _REMBG_FAILED.add(model_name)
            raise RuntimeError('rembg no pudo crear la sesión '+model_name+'.')
        _REMBG_SESSIONS[model_name] = session
        return session

def _warm_segmenter():
    try:
        from rembg import new_session
        _get_rembg_session(new_session, _SEGMENT_MODELS[0])
        print('Modelo de recorte listo:', _SEGMENT_MODELS[0])
    except Exception as exc:
        print('Aviso: no se pudo preparar', _SEGMENT_MODELS[0], '('+str(exc)[:180]+'). El recorte intentará u2net.')

def _need_numpy():
    try:
        import numpy as np
    except Exception as exc:
        raise RuntimeError('Falta numpy para limpiar los PNG. Ejecuta INSTALAR_DEPENDENCIAS.bat. '+str(exc)[:120])
    return np

def _parse_inner(inner, width, height):
    if not isinstance(inner, dict):
        margin = max(1, int(round(min(width, height) * 0.02)))
        return margin, margin, max(1, width - 2 * margin), max(1, height - 2 * margin)
    try:
        x = int(float(inner.get('x', 0)))
        y = int(float(inner.get('y', 0)))
        w = int(float(inner.get('w', width)))
        h = int(float(inner.get('h', height)))
    except (TypeError, ValueError):
        return 0, 0, width, height
    x = max(0, min(width - 1, x))
    y = max(0, min(height - 1, y))
    w = max(1, min(width - x, w))
    h = max(1, min(height - y, h))
    return x, y, w, h

def _shift_bool(mask, dy, dx):
    np = _need_numpy()
    out = np.zeros_like(mask)
    h, w = mask.shape
    y_dst = slice(max(0, dy), h + min(0, dy))
    x_dst = slice(max(0, dx), w + min(0, dx))
    y_src = slice(max(0, -dy), h - max(0, dy))
    x_src = slice(max(0, -dx), w - max(0, dx))
    out[y_dst, x_dst] = mask[y_src, x_src]
    return out

def _shift_color(arr, dy, dx):
    np = _need_numpy()
    out = np.zeros_like(arr)
    h, w = arr.shape[:2]
    y_dst = slice(max(0, dy), h + min(0, dy))
    x_dst = slice(max(0, dx), w + min(0, dx))
    y_src = slice(max(0, -dy), h - max(0, dy))
    x_src = slice(max(0, -dx), w - max(0, dx))
    out[y_dst, x_dst] = arr[y_src, x_src]
    return out

def _dilate_bool(mask, radius):
    out = mask.copy()
    for dy in range(-radius, radius + 1):
        for dx in range(-radius, radius + 1):
            if dy * dy + dx * dx > radius * radius:
                continue
            out |= _shift_bool(mask, dy, dx)
    return out

def _label_components(mask):
    np = _need_numpy()
    try:
        from scipy import ndimage
        labels, count = ndimage.label(mask, structure=np.ones((3, 3), dtype=np.uint8))
        return labels, int(count)
    except Exception:
        return _label_components_py(mask)

def _label_components_py(mask):
    np = _need_numpy()
    h, w = mask.shape
    labels = np.zeros((h, w), np.int32)
    count = 0
    ys, xs = np.nonzero(mask)
    seen = np.zeros(h * w, np.uint8)
    flat = mask.reshape(-1)
    for y0, x0 in zip(ys.tolist(), xs.tolist()):
        start = y0 * w + x0
        if seen[start]:
            continue
        count += 1
        stack = [start]
        seen[start] = 1
        labels[y0, x0] = count
        while stack:
            i = stack.pop()
            y, x = divmod(i, w)
            y_lo, y_hi = max(0, y - 1), min(h, y + 2)
            x_lo, x_hi = max(0, x - 1), min(w, x + 2)
            for ny in range(y_lo, y_hi):
                row = ny * w
                for nx in range(x_lo, x_hi):
                    j = row + nx
                    if seen[j] or not flat[j]:
                        continue
                    seen[j] = 1
                    labels[ny, nx] = count
                    stack.append(j)
    return labels, count

def _keep_components(alpha, inner):
    """Quita fragmentos que no pertenecen a la caja original, como un vecino metido en el margen."""
    np = _need_numpy()
    fg = alpha >= 16
    h, w = alpha.shape
    ix, iy, iw, ih = inner
    labels, count = _label_components(fg)
    if count <= 1:
        return alpha, 0
    region = np.zeros((h, w), dtype=bool)
    region[iy:iy + ih, ix:ix + iw] = True
    overlap = np.bincount(labels[fg & region].ravel(), minlength=count + 1)
    area = np.bincount(labels[fg].ravel(), minlength=count + 1)
    keep = np.zeros(count + 1, dtype=bool)
    for i in range(1, count + 1):
        if area[i] and overlap[i] / area[i] >= 0.30:
            keep[i] = True
    kept = keep[labels]
    if int(np.count_nonzero(kept)) < max(8, int(np.count_nonzero(fg) * 0.15)):
        return alpha, 0
    cleaned = np.where(kept, alpha, 0).astype(np.uint8)
    removed = int(count - int(np.count_nonzero(keep[1:])))
    return cleaned, removed

def _defringe(src, out):
    """Recupera el color del borde para que no quede un halo del fondo."""
    np = _need_numpy()
    alpha = out[:, :, 3]
    transparent = alpha < 12
    if int(np.count_nonzero(transparent)) >= 8:
        bg = np.median(src[:, :, :3][transparent], axis=0)
    else:
        corners = np.stack([src[0, 0, :3], src[0, -1, :3], src[-1, 0, :3], src[-1, -1, :3]])
        bg = np.median(corners, axis=0)
    a = alpha.astype(np.float32) / 255.0
    rgb = out[:, :, :3].astype(np.float32)
    edge = (alpha > 0) & (alpha < 248)
    if np.any(edge):
        unmixed = (rgb - bg * (1.0 - a)[..., None]) / np.maximum(a, 0.12)[..., None]
        rgb[edge] = np.clip(unmixed[edge], 0, 255)
        out[:, :, :3] = rgb.astype(np.uint8)
    opaque = alpha > 240
    interior = opaque.copy()
    for dy, dx in ((-1, 0), (1, 0), (0, -1), (0, 1), (-1, -1), (-1, 1), (1, -1), (1, 1)):
        interior &= _shift_bool(opaque, dy, dx)
    rim = opaque & ~interior
    if not np.any(rim) or not np.any(interior):
        return
    color = out[:, :, :3].copy()
    known = interior
    for _ in range(2):
        nxt = color.copy()
        nxt_known = known.copy()
        for dy, dx in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            shifted = _shift_color(color, dy, dx)
            shifted_known = _shift_bool(known, dy, dx)
            take = rim & ~nxt_known & shifted_known
            nxt[take] = shifted[take]
            nxt_known |= take
        color, known = nxt, nxt_known
    out[:, :, :3][rim] = color[rim]

def refine_cutout(source_rgba, cutout_rgba, inner=None):
    """Limpia la máscara: quita vecinos, el halo y el margen vacío."""
    np = _need_numpy()
    if Image is None:
        raise RuntimeError('Falta Pillow.')
    source_rgba = source_rgba.convert('RGBA')
    cutout_rgba = cutout_rgba.convert('RGBA')
    if cutout_rgba.size != source_rgba.size:
        resample = Image.Resampling.NEAREST if hasattr(Image, 'Resampling') else Image.NEAREST
        cutout_rgba = cutout_rgba.resize(source_rgba.size, resample)
    src = np.array(source_rgba)
    out = np.array(cutout_rgba)
    h, w = out.shape[:2]
    alpha, removed = _keep_components(out[:, :, 3], _parse_inner(inner, w, h))
    alpha = alpha.copy()
    alpha[alpha < 12] = 0
    if int(np.max(alpha)) < 8:
        raise RuntimeError('La máscara quedó prácticamente vacía; no se exportó una silueta incorrecta.')
    out[:, :, 3] = alpha
    _defringe(src, out)
    out[out[:, :, 3] == 0, :3] = 0
    image = Image.fromarray(out, 'RGBA')
    ys, xs = np.nonzero(out[:, :, 3] > 8)
    if len(xs) == 0:
        raise RuntimeError('La máscara quedó prácticamente vacía; no se exportó una silueta incorrecta.')
    pad = 2
    x0 = max(0, int(xs.min()) - pad)
    y0 = max(0, int(ys.min()) - pad)
    x1 = min(w, int(xs.max()) + 1 + pad)
    y1 = min(h, int(ys.max()) + 1 + pad)
    trimmed = image.crop((x0, y0, x1, y1))
    return trimmed, {'removedFragments': removed, 'trimX': x0, 'trimY': y0, 'width': trimmed.width, 'height': trimmed.height}

def _segment_cutout(source, inner, kind=''):
    try:
        from rembg import remove, new_session
    except Exception as imp_err:
        raise RuntimeError('No se pudo cargar rembg/onnxruntime. Ejecuta INSTALAR_DEPENDENCIAS.bat, espera a que termine sin errores y reinicia GAMEB Studio. Detalle: '+str(imp_err)[:180])
    errors = []
    for model in _SEGMENT_MODELS:
        try:
            session = _get_rembg_session(new_session, model)
            raw = remove(source, session=session, alpha_matting=False, post_process_mask=False)
            if not isinstance(raw, Image.Image):
                raw = Image.open(io.BytesIO(raw)).convert('RGBA')
            raw = raw.convert('RGBA')
            parsed_inner = _parse_inner(inner, source.width, source.height)
            if _is_title_kind(kind):
                raw = _restore_title_letters(source, raw, parsed_inner)
            refined, info = refine_cutout(source, raw, inner)
            info['engine'] = model
            return refined, info
        except Exception as exc:
            errors.append(model+': '+str(exc)[:160])
    raise RuntimeError('No se pudo separar la pieza. '+' | '.join(errors))

def _restore_title_letters(source, cutout, inner):
    """Si el recorte se quedó solo con una palabra, recupera las letras que siguen dentro de la caja."""
    np = _need_numpy()
    src = np.array(source.convert('RGBA'))
    out = np.array(cutout.convert('RGBA'))
    if src.shape[:2] != out.shape[:2]:
        return cutout
    ix, iy, iw, ih = inner
    region = out[iy:iy+ih, ix:ix+iw, 3]
    if iw < 4 or ih < 4 or region.size == 0:
        return cutout
    covered = float(np.any(region > 32, axis=0).mean())
    if covered >= 0.72:
        return cutout
    rgb = src[:, :, :3].astype(np.int16)
    small_w, small_h = max(8, src.shape[1] // 12), max(8, src.shape[0] // 12)
    resample = Image.Resampling.BILINEAR if hasattr(Image, 'Resampling') else Image.BILINEAR
    blur = np.asarray(Image.fromarray(src[:, :, :3], 'RGB').resize((small_w, small_h), resample).resize((src.shape[1], src.shape[0]), resample), np.int16)
    differ = np.max(np.abs(rgb - blur), axis=2) > 34
    keep = np.zeros(differ.shape, dtype=bool)
    keep[iy:iy+ih, ix:ix+iw] = differ[iy:iy+ih, ix:ix+iw]
    if int(np.count_nonzero(keep)) < 30:
        return cutout
    out[:, :, 3] = np.maximum(out[:, :, 3], np.where(keep, 255, 0).astype(np.uint8))
    restored = out[:, :, 3] > 32
    out[restored, :3] = src[restored, :3]
    return Image.fromarray(out, 'RGBA')


def quitar_fondo(data):
    """Respuesta de POST /api/remove-background."""
    if Image is None:
        return 503, {'ok': False, 'error': 'Falta Pillow. Instala las dependencias del proyecto.'}
    try:
        head, raw = decode_data(data.get('image', ''))
        if len(raw) > 15 * 1024 * 1024:
            return 413, {'ok': False, 'error': 'El recorte supera 15 MB.'}
        source = Image.open(io.BytesIO(raw)).convert('RGBA')
        if source.width < 2 or source.height < 2:
            return 400, {'ok': False, 'error': 'El recorte está vacío o sus dimensiones no son válidas.'}
        result, info = _segment_cutout(source, data.get('inner'), str(data.get('kind') or '')[:40])
        out = io.BytesIO()
        result.save(out, format='PNG', optimize=True)
        import base64
        encoded = base64.b64encode(out.getvalue()).decode('ascii')
        return 200, {
            'ok': True,
            'image': 'data:image/png;base64,' + encoded,
            'width': result.width,
            'height': result.height,
            'trimX': info.get('trimX', 0),
            'trimY': info.get('trimY', 0),
            'engine': info.get('engine', ''),
            'removedFragments': info.get('removedFragments', 0),
            'alphaMatting': False,
        }
    except Exception as exc:
        return 502, {'ok': False, 'error': 'Falló la segmentación: ' + str(exc)[:300]}
