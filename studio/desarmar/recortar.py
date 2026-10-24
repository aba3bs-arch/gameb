"""Recorte de cada pieza, para cualquier boceto.

El fondo se deja entero. Una placa o un marco se suelta por el color del borde.
Un símbolo entra como cuadrado solo si su contorno exterior es un rectángulo
de lados rectos; el PNG es ese rectángulo, sin el paisaje de alrededor.
Cualquier otro dibujo sigue su contorno. No se usa una figura concreta.
"""
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

def _spread_color(rgb, seeds, steps):
    """Lleva el color de una zona hacia los píxeles vecinos, sin mezclar el otro lado."""
    np = _need_numpy()
    color = np.zeros(rgb.shape, np.float32)
    known = seeds.copy()
    color[known] = rgb[known]
    for _ in range(steps):
        acc = np.zeros_like(color)
        count = np.zeros(color.shape[:2], np.float32)
        for dy, dx in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            shifted_known = _shift_bool(known, dy, dx)
            acc += _shift_color(color, dy, dx) * shifted_known[..., None]
            count += shifted_known
        fill = ~known & (count > 0)
        if not np.any(fill):
            break
        color[fill] = acc[fill] / count[fill, None]
        known |= fill
    return color, known


def _peel_background(rgb_src, rgb_cut, alpha, limit=18):
    """Quita el fondo que la máscara marcó como sólido, si sigue el color de afuera.

    El color de referencia sale del boceto, justo donde ya no hay máscara. Se compara
    con el color guardado en el recorte: un anillo de otro color, o un borde ya mezclado,
    no se camina. Un hueco interior solo entra si el recorte sigue siendo fondo.
    """
    np = _need_numpy()
    from collections import deque
    h, w = alpha.shape
    transparent = alpha < 16
    target = alpha >= 16
    touch = np.zeros((h, w), dtype=bool)
    for dy, dx in ((-1, 0), (1, 0), (0, -1), (0, 1)):
        touch |= _shift_bool(target, dy, dx)
    seeds = transparent & touch
    seen = transparent.copy()
    eaten = np.zeros((h, w), dtype=bool)
    ref = np.zeros((h, w, 3), np.int16)
    ys, xs = np.nonzero(seeds)
    ref[ys, xs] = rgb_src[ys, xs]
    cut = rgb_cut.astype(np.int16)
    queue = deque(zip(ys.tolist(), xs.tolist()))
    while queue:
        y, x = queue.popleft()
        base = ref[y, x]
        for ny, nx in ((y - 1, x), (y + 1, x), (y, x - 1), (y, x + 1)):
            if ny < 0 or nx < 0 or ny >= h or nx >= w or seen[ny, nx] or not target[ny, nx]:
                continue
            if int(np.max(np.abs(cut[ny, nx] - base))) > limit:
                continue
            seen[ny, nx] = True
            eaten[ny, nx] = True
            ref[ny, nx] = base
            queue.append((ny, nx))
    return eaten


def _defringe(src, out):
    """El borde usa el fondo de al lado y el color del objeto. La alfa es solo la mezcla real.

    El color observado es el del recorte (ahí está la mezcla). Donde la máscara ya es
    transparente se mira el boceto, para no rellenar un hueco con un borde inventado.
    Cada pasada lee ese color original: si se guardara ya el color limpio, la siguiente
    pasada vería cobertura total y volvería el borde opaco.
    """
    np = _need_numpy()
    rgb_src = src[:, :, :3]
    observed = out[:, :, :3].copy()
    alpha = out[:, :, 3]
    if int(np.count_nonzero(alpha < 16)) >= 8 and np.any(alpha >= 16):
        eaten = _peel_background(rgb_src, observed, alpha)
        out[:, :, 3][eaten] = 0
    for _ in range(4):
        alpha = out[:, :, 3]
        before = alpha.copy()
        transparent = alpha < 16
        if int(np.count_nonzero(transparent)) < 8:
            break
        opaque = alpha >= 240
        interior = opaque.copy()
        for dy, dx in ((-1, 0), (1, 0), (0, -1), (0, 1), (-1, -1), (-1, 1), (1, -1), (1, 1)):
            interior &= _shift_bool(opaque, dy, dx)
        if not np.any(interior):
            break
        bg, bg_known = _spread_color(rgb_src, transparent, 6)
        fg, fg_known = _spread_color(observed, interior, 6)
        near = np.zeros(alpha.shape, dtype=bool)
        for dy, dx in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            near |= _shift_bool(alpha >= 16, dy, dx)
        candidate = ((alpha >= 16) | (transparent & near)) & bg_known & fg_known & ~interior
        if not np.any(candidate):
            break
        diff = fg - bg
        denom = np.sum(diff * diff, axis=2)
        safe = denom > 64.0
        obs = observed.astype(np.float32)
        obs[transparent] = rgb_src[transparent]
        numer = np.sum((obs - bg) * diff, axis=2)
        coverage = np.zeros(alpha.shape, np.float32)
        np.divide(numer, denom, out=coverage, where=safe)
        np.clip(coverage, 0, 1, out=coverage)
        new_a = alpha.astype(np.float32)
        inside = candidate & (alpha >= 16) & safe
        new_a[inside & (coverage < 0.12)] = 0
        partial = inside & (coverage >= 0.12) & (coverage < 0.88)
        new_a[partial] = coverage[partial] * 255.0
        new_a[inside & (coverage >= 0.88)] = 255
        outside = candidate & (alpha < 16) & safe & (coverage > 0.22) & (coverage < 0.9)
        new_a[outside] = coverage[outside] * 255.0
        paint = (partial | outside | (inside & (coverage >= 0.88))) & safe
        out[:, :, :3][paint] = np.clip(fg[paint], 0, 255).astype(np.uint8)
        out[:, :, 3] = np.clip(new_a, 0, 255).astype(np.uint8)
        if np.array_equal(out[:, :, 3], before) and not np.any(outside):
            break

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
    if int(np.max(alpha)) < 8:
        raise RuntimeError('La máscara quedó prácticamente vacía; no se exportó una silueta incorrecta.')
    out[:, :, 3] = alpha
    _defringe(src, out)
    out[:, :, 3][out[:, :, 3] < 12] = 0
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

def _clase_de_pieza(kind):
    """Cada tipo de pieza se corta con su propia regla."""
    text = str(kind or '').lower()
    if 'fondo' in text:
        return 'fondo'
    if 'marco' in text:
        return 'marco'
    if 'jackpot' in text or 'panel' in text:
        return 'placa'
    return 'silueta'


def _fondo_conectado_al_borde(rgb, salto=24):
    """El paisaje que toca el borde del recorte. Se detiene en el filo de la pieza.

    La semilla es el color más repetido del borde. Un adorno que llega a la orilla
    no abre el relleno hacia dentro de la placa.
    """
    np = _need_numpy()
    from collections import deque
    h, w = rgb.shape[:2]
    color = rgb.astype(np.int16)
    fondo = np.zeros((h, w), dtype=bool)
    if h < 3 or w < 3:
        return fondo
    borde = np.zeros((h, w), dtype=bool)
    borde[0, :] = borde[-1, :] = True
    borde[:, 0] = borde[:, -1] = True
    ref = np.median(color[borde], axis=0)
    ys, xs = np.nonzero(borde)
    queue = deque()
    for y, x in zip(ys.tolist(), xs.tolist()):
        if int(np.max(np.abs(color[y, x] - ref))) <= salto:
            fondo[y, x] = True
            queue.append((y, x))
    while queue:
        y, x = queue.popleft()
        base = color[y, x]
        for ny, nx in ((y - 1, x), (y + 1, x), (y, x - 1), (y, x + 1)):
            if ny < 0 or nx < 0 or ny >= h or nx >= w or fondo[ny, nx]:
                continue
            if int(np.max(np.abs(color[ny, nx] - base))) > salto:
                continue
            fondo[ny, nx] = True
            queue.append((ny, nx))
    return fondo


def _erode_bool(mask, radius):
    return ~_dilate_bool(~mask, radius)


def _cerrar_bool(mask, radius=1):
    """Cierra mordidas de un píxel en el filo, sin alcanzar una chispa separada."""
    return _erode_bool(_dilate_bool(mask, radius), radius)


def _quitar_islas(alpha, fraccion=0.03, minimo=40):
    """Quita chispas sueltas. Una letra o la placa, que son grandes, se quedan."""
    np = _need_numpy()
    labels, count = _label_components(alpha >= 16)
    if count <= 1:
        return alpha
    areas = np.bincount(labels.ravel(), minlength=count + 1)
    mayor = int(areas[1:].max())
    if mayor < minimo:
        return alpha
    corte = max(minimo, int(mayor * fraccion))
    keep = areas >= corte
    keep[0] = False
    return np.where(keep[labels], alpha, 0).astype(np.uint8)


def _aplicar_mascara(source, mask):
    np = _need_numpy()
    arr = np.array(source.convert('RGBA'))
    arr[~mask, 3] = 0
    arr[~mask, :3] = 0
    return arr


def _pieza_de_la_caja(pieza, inner):
    """La pieza es la que cae en su caja. Un vecino que entró por el margen no se queda."""
    np = _need_numpy()
    if not isinstance(inner, dict) or pieza.size == 0:
        return pieza
    h, w = pieza.shape
    ix, iy, iw, ih = _parse_inner(inner, w, h)
    if iw * ih >= int(w * h * 0.92):
        return pieza
    dentro = np.zeros((h, w), dtype=bool)
    dentro[iy:iy + ih, ix:ix + iw] = True
    labels, count = _label_components(pieza)
    if count == 0:
        return pieza
    overlap = np.bincount(labels[dentro & pieza].ravel(), minlength=count + 1)
    keep = overlap > 0
    keep[0] = False
    elegida = keep[labels]
    if not np.any(elegida):
        return pieza
    if int((elegida & pieza & dentro).sum()) < int((pieza & dentro).sum()) * 0.5:
        return pieza
    return elegida


def _recortar_desde_el_borde(source, clase, inner=None):
    """Placa y marco: suelta el paisaje del borde y tira las chispas que no son la pieza."""
    np = _need_numpy()
    rgb = np.array(source.convert('RGB'))
    fondo = _fondo_conectado_al_borde(rgb)
    ratio = float(fondo.mean()) if fondo.size else 0.0
    limite = 0.40 if clase == 'placa' else 0.55
    arr = np.array(source.convert('RGBA'))
    if 0.015 <= ratio <= limite:
        pieza = _cerrar_bool(~fondo, 1)
        if clase == 'placa':
            pieza = _pieza_de_la_caja(pieza, inner)
        pieza = _quitar_islas(np.where(pieza, 255, 0).astype(np.uint8), 0.03, 48) >= 16
        arr = _aplicar_mascara(source, pieza)
    refined, info = refine_cutout(source, Image.fromarray(arr, 'RGBA'), None)
    out = np.array(refined)
    limpio = _quitar_islas(out[:, :, 3], 0.03, 48)
    out[:, :, 3] = limpio
    out[limpio < 16, :3] = 0
    info['engine'] = 'borde-' + clase
    return Image.fromarray(out, 'RGBA'), info


def _es_simbolo(kind):
    text = str(kind or '').lower().replace('í', 'i').replace('Í', 'i')
    return 'simbolo' in text


def _cuadrado_de_simbolo(rgb, inner):
    """El cuadrado es un borde recto y continuo, no la caja de búsqueda ni un dibujo concreto."""
    np = _need_numpy()
    if not isinstance(inner, dict) or getattr(rgb, 'ndim', 0) != 3:
        return None
    alto, ancho = rgb.shape[:2]
    ix, iy, iw, ih = _parse_inner(inner, ancho, alto)
    if iw < 32 or ih < 32 or alto < 16 or ancho < 16:
        return None
    margen_x = max(4, int(iw * 0.18))
    margen_y = max(4, int(ih * 0.18))
    x0, y0 = max(1, ix - margen_x), max(1, iy - margen_y)
    x1, y1 = min(ancho - 1, ix + iw + margen_x), min(alto - 1, iy + ih + margen_y)
    if x1 - x0 < 32 or y1 - y0 < 32:
        return None
    color = rgb.astype(np.int16)
    salto_x = np.zeros((alto, ancho), np.float32)
    salto_y = np.zeros((alto, ancho), np.float32)
    salto_x[:, 1:] = np.max(np.abs(color[:, 1:] - color[:, :-1]), axis=2)
    salto_y[1:, :] = np.max(np.abs(color[1:, :] - color[:-1, :]), axis=2)
    columnas = salto_x[y0:y1, x0:x1].mean(axis=0)
    filas = salto_y[y0:y1, x0:x1].mean(axis=1)
    mitad_x, mitad_y = columnas.size // 2, filas.size // 2
    if mitad_x < 8 or mitad_y < 8:
        return None
    izquierda = int(np.argmax(columnas[:mitad_x]))
    derecha = int(np.argmax(columnas[mitad_x:])) + mitad_x
    arriba = int(np.argmax(filas[:mitad_y]))
    abajo = int(np.argmax(filas[mitad_y:])) + mitad_y
    fuerza_x = float(np.median(columnas))
    fuerza_y = float(np.median(filas))
    if min(float(columnas[izquierda]), float(columnas[derecha])) < max(36.0, fuerza_x * 2.0):
        return None
    if min(float(filas[arriba]), float(filas[abajo])) < max(36.0, fuerza_y * 2.0):
        return None
    if derecha - izquierda < 28 or abajo - arriba < 28:
        return None
    lado_izq = salto_x[y0 + arriba:y0 + abajo, x0 + izquierda]
    lado_der = salto_x[y0 + arriba:y0 + abajo, x0 + derecha]
    lado_arr = salto_y[y0 + arriba, x0 + izquierda:x0 + derecha]
    lado_aba = salto_y[y0 + abajo, x0 + izquierda:x0 + derecha]
    if min(lado_izq.size, lado_der.size, lado_arr.size, lado_aba.size) < 8:
        return None
    continuo = min(
        float((lado_izq >= 30).mean()),
        float((lado_der >= 30).mean()),
        float((lado_arr >= 30).mean()),
        float((lado_aba >= 30).mean()),
    )
    if continuo < 0.68:
        return None
    bx, by = x0 + izquierda, y0 + arriba
    bw, bh = derecha - izquierda, abajo - arriba
    proporcion = bw / float(bh)
    if proporcion < 0.80 or proporcion > 1.25:
        return None
    return {'x': bx, 'y': by, 'w': bw, 'h': bh}


def _borde_suave(src, out, x0, y0, x1, y1):
    """El píxel mezclado del filo usa el color del cuadrado y una alfa real, no el color del fondo."""
    np = _need_numpy()
    alto, ancho = out.shape[:2]
    dentro = np.zeros((alto, ancho), dtype=bool)
    dentro[y0:y1, x0:x1] = True
    afuera = ~dentro
    if int(afuera.sum()) < 8:
        return
    escena = np.median(src[:, :, :3][afuera].astype(np.int16), axis=0)
    y_a, y_b = max(0, y0 - 1), min(alto, y1 + 1)
    x_a, x_b = max(0, x0 - 1), min(ancho, x1 + 1)
    for y in range(y_a, y_b):
        for x in range(x_a, x_b):
            if dentro[y, x]:
                continue
            vecino = None
            for ny, nx in ((y - 1, x), (y + 1, x), (y, x - 1), (y, x + 1)):
                if 0 <= ny < alto and 0 <= nx < ancho and dentro[ny, nx]:
                    vecino = src[ny, nx, :3].astype(np.float32)
                    break
            if vecino is None:
                continue
            obs = src[y, x, :3].astype(np.float32)
            diff = vecino - escena.astype(np.float32)
            denom = float(np.dot(diff, diff))
            if denom <= 64.0:
                continue
            cobertura = float(np.dot(obs - escena, diff) / denom)
            if cobertura < 0.15 or cobertura > 0.92:
                continue
            out[y, x, :3] = np.clip(vecino, 0, 255).astype(np.uint8)
            out[y, x, 3] = int(round(cobertura * 255))


def _recortar_cuadrado(source, rect):
    """El símbolo cuadrado se queda entero: marco, fondo de la ficha y dibujo, con el filo limpio."""
    np = _need_numpy()
    src = np.array(source.convert('RGBA'))
    alto, ancho = src.shape[:2]
    x0 = max(0, min(ancho - 1, int(rect['x'])))
    y0 = max(0, min(alto - 1, int(rect['y'])))
    x1 = max(x0 + 1, min(ancho, x0 + int(rect['w'])))
    y1 = max(y0 + 1, min(alto, y0 + int(rect['h'])))
    out = np.zeros_like(src)
    out[y0:y1, x0:x1] = src[y0:y1, x0:x1]
    out[y0:y1, x0:x1, 3] = 255
    _borde_suave(src, out, x0, y0, x1, y1)
    ys, xs = np.nonzero(out[:, :, 3] > 8)
    pad = 1
    recorte_x = max(0, int(xs.min()) - pad)
    recorte_y = max(0, int(ys.min()) - pad)
    recorte_x1 = min(ancho, int(xs.max()) + 1 + pad)
    recorte_y1 = min(alto, int(ys.max()) + 1 + pad)
    imagen = Image.fromarray(out, 'RGBA').crop((recorte_x, recorte_y, recorte_x1, recorte_y1))
    return imagen, {
        'removedFragments': 0,
        'trimX': recorte_x,
        'trimY': recorte_y,
        'width': imagen.width,
        'height': imagen.height,
        'engine': 'cuadrado',
        'usable': True,
    }


def _paisaje_del_borde(rgb, salto=26):
    """Color del borde. No sigue un degradado hasta comerse el dibujo."""
    np = _need_numpy()
    from collections import deque
    alto, ancho = rgb.shape[:2]
    color = rgb.astype(np.int16)
    fondo = np.zeros((alto, ancho), dtype=bool)
    if alto < 3 or ancho < 3:
        return fondo
    borde = np.zeros((alto, ancho), dtype=bool)
    borde[0, :] = borde[-1, :] = True
    borde[:, 0] = borde[:, -1] = True
    ref = np.median(color[borde], axis=0)
    ys, xs = np.nonzero(borde)
    queue = deque()
    for y, x in zip(ys.tolist(), xs.tolist()):
        if int(np.max(np.abs(color[y, x] - ref))) <= salto:
            fondo[y, x] = True
            queue.append((y, x))
    while queue:
        y, x = queue.popleft()
        for ny, nx in ((y - 1, x), (y + 1, x), (y, x - 1), (y, x + 1)):
            if ny < 0 or nx < 0 or ny >= alto or nx >= ancho or fondo[ny, nx]:
                continue
            if int(np.max(np.abs(color[ny, nx] - ref))) > salto:
                continue
            fondo[ny, nx] = True
            queue.append((ny, nx))
    return fondo


def _completar_contorno(rgb, mask):
    """Suma el filo real del dibujo. No rellena un hueco con el color del fondo."""
    np = _need_numpy()
    if mask is None or not np.any(mask):
        return mask
    alto, ancho = mask.shape
    color = rgb.astype(np.int16) if rgb.dtype != np.int16 else rgb
    if color.ndim != 3:
        return mask
    borde = np.zeros((alto, ancho), dtype=bool)
    borde[0, :] = borde[-1, :] = True
    borde[:, 0] = borde[:, -1] = True
    if int(borde.sum()) < 4:
        return mask
    escena = np.median(color[borde], axis=0)
    difiere = np.max(np.abs(color - escena), axis=2) > 26
    cerca = _dilate_bool(mask, 1) & ~mask
    return mask | (cerca & difiere)


def _silueta_por_contraste(rgb, inner):
    """El dibujo dentro de su caja. El paisaje que rodea las letras o el símbolo sale."""
    np = _need_numpy()
    from collections import deque
    h, w = rgb.shape[:2]
    ix, iy, iw, ih = _parse_inner(inner, w, h)
    if iw < 8 or ih < 8:
        return None
    small_w, small_h = max(8, w // 12), max(8, h // 12)
    resample = Image.Resampling.BILINEAR if hasattr(Image, 'Resampling') else Image.BILINEAR
    blur = np.asarray(
        Image.fromarray(rgb.astype(np.uint8), 'RGB').resize((small_w, small_h), resample).resize((w, h), resample),
        np.int16,
    )
    tinta = np.max(np.abs(rgb.astype(np.int16) - blur), axis=2) > 26
    dentro = np.zeros((h, w), dtype=bool)
    dentro[iy:iy + ih, ix:ix + iw] = True
    semillas = np.zeros((h, w), dtype=bool)
    semillas[iy, ix:ix + iw] = True
    semillas[min(h - 1, iy + ih - 1), ix:ix + iw] = True
    semillas[iy:iy + ih, ix] = True
    semillas[iy:iy + ih, min(w - 1, ix + iw - 1)] = True
    semillas &= dentro & ~tinta
    if int(semillas.sum()) < 8:
        return None
    color = rgb.astype(np.int16)
    fondo = semillas.copy()
    ys, xs = np.nonzero(semillas)
    queue = deque(zip(ys.tolist(), xs.tolist()))
    y1, x1 = iy + ih, ix + iw
    while queue:
        y, x = queue.popleft()
        base = color[y, x]
        for ny, nx in ((y - 1, x), (y + 1, x), (y, x - 1), (y, x + 1)):
            if ny < iy or nx < ix or ny >= y1 or nx >= x1 or fondo[ny, nx] or tinta[ny, nx]:
                continue
            if int(np.max(np.abs(color[ny, nx] - base))) > 22:
                continue
            fondo[ny, nx] = True
            queue.append((ny, nx))
    sujeto = (dentro & ~fondo) | (tinta & dentro)
    cubierto = float(sujeto.sum()) / float(iw * ih)
    if cubierto < 0.12 or cubierto > 0.97:
        return None
    # Lo que sigue pegado y se sale de la caja se queda, si está unido al dibujo.
    paisaje = _paisaje_del_borde(rgb if rgb.dtype == np.uint8 else rgb.astype(np.uint8))
    labels, count = _label_components(~paisaje)
    if count == 0:
        return _completar_contorno(rgb, sujeto)
    overlap = np.bincount(labels[sujeto].ravel(), minlength=count + 1)
    keep = overlap > 0
    keep[0] = False
    crecido = keep[labels]
    if int((crecido & sujeto).sum()) < int(sujeto.sum()) * 0.5:
        return _completar_contorno(rgb, sujeto)
    return _completar_contorno(rgb, crecido)


def _recortar_silueta(source, inner):
    """Título, símbolo y botón: recorta el dibujo de su caja, sin el paisaje de alrededor."""
    np = _need_numpy()
    rgb = np.array(source.convert('RGB'))
    sujeto = _silueta_por_contraste(rgb, inner)
    if sujeto is None:
        return None, {'usable': False}
    arr = _aplicar_mascara(source, sujeto)
    arr[:, :, 3] = _quitar_islas(arr[:, :, 3], 0.008, 18)
    arr[arr[:, :, 3] < 16, :3] = 0
    try:
        refined, info = refine_cutout(source, Image.fromarray(arr, 'RGBA'), inner)
    except RuntimeError:
        return None, {'usable': False}
    out = np.array(refined)
    limpio = _quitar_islas(out[:, :, 3], 0.008, 18)
    out[:, :, 3] = limpio
    out[limpio < 16, :3] = 0
    info['engine'] = 'contraste'
    info['usable'] = True
    return Image.fromarray(out, 'RGBA'), info


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
            alpha = _need_numpy().array(raw)[:, :, 3]
            cols, solid = _coverage(alpha, parsed_inner)
            if _should_restore(kind, cols, solid):
                raw = _restore_title_letters(source, raw, parsed_inner)
                alpha = _need_numpy().array(raw)[:, :, 3]
                cols, solid = _coverage(alpha, parsed_inner)
            if _drawing_disappeared(solid, parsed_inner):
                raise RuntimeError('La máscara borró casi todo el dibujo. No se guardó un PNG vacío.')
            refined, info = refine_cutout(source, raw, inner)
            info['engine'] = model
            return refined, info
        except Exception as exc:
            errors.append(model+': '+str(exc)[:160])
    raise RuntimeError('No se pudo separar la pieza. '+' | '.join(errors))

def _coverage(alpha, inner):
    """Ancho cubierto y área con dibujo opaco dentro de la caja original."""
    np = _need_numpy()
    ix, iy, iw, ih = inner
    region = alpha[iy:iy + ih, ix:ix + iw]
    if region.size == 0 or iw < 1 or ih < 1:
        return 1.0, 1.0
    cols = float(np.any(region > 32, axis=0).mean())
    solid = float((region > 32).mean())
    return cols, solid


def _should_restore(kind, cols, solid):
    """Una mancha no es una pieza. El título además tiene que cubrir todas sus palabras."""
    if solid < 0.22:
        return True
    return _is_title_kind(kind) and cols < 0.72


def _drawing_disappeared(solid, inner):
    iw, ih = inner[2], inner[3]
    return iw * ih >= 80 and solid < 0.06


def _grow_same_color(color, seeds, limit=36):
    """Extiende la mancha por el color plano del objeto, sin caminar un degradado."""
    np = _need_numpy()
    from collections import deque
    h, w = seeds.shape
    seen = seeds.copy()
    ref = np.zeros((h, w, 3), np.int16)
    ref[seeds] = color[seeds]
    ys, xs = np.nonzero(seeds)
    queue = deque(zip(ys.tolist(), xs.tolist()))
    while queue:
        y, x = queue.popleft()
        base = ref[y, x]
        for ny, nx in ((y - 1, x), (y + 1, x), (y, x - 1), (y, x + 1)):
            if ny < 0 or nx < 0 or ny >= h or nx >= w or seen[ny, nx]:
                continue
            if int(np.max(np.abs(color[ny, nx].astype(np.int16) - base))) > limit:
                continue
            seen[ny, nx] = True
            ref[ny, nx] = base
            queue.append((ny, nx))
    return seen


def _restore_title_letters(source, cutout, inner):
    """Si el recorte se quedó en una mancha, recupera el dibujo que sigue dentro de la caja."""
    np = _need_numpy()
    src = np.array(source.convert('RGBA'))
    out = np.array(cutout.convert('RGBA'))
    if src.shape[:2] != out.shape[:2]:
        return cutout
    ix, iy, iw, ih = inner
    region = out[iy:iy+ih, ix:ix+iw, 3]
    if iw < 4 or ih < 4 or region.size == 0:
        return cutout
    covered, solid = _coverage(out[:, :, 3], inner)
    if covered >= 0.72 and solid >= 0.22:
        return cutout
    rgb = src[:, :, :3].astype(np.int16)
    small_w, small_h = max(8, src.shape[1] // 12), max(8, src.shape[0] // 12)
    resample = Image.Resampling.BILINEAR if hasattr(Image, 'Resampling') else Image.BILINEAR
    blur = np.asarray(Image.fromarray(src[:, :, :3], 'RGB').resize((small_w, small_h), resample).resize((src.shape[1], src.shape[0]), resample), np.int16)
    differ = np.max(np.abs(rgb - blur), axis=2) > 34
    sub_seeds = differ[iy:iy+ih, ix:ix+iw]
    if int(np.count_nonzero(sub_seeds)) < 30:
        return cutout
    grown = _grow_same_color(src[iy:iy+ih, ix:ix+iw, :3], sub_seeds)
    keep = np.zeros(differ.shape, dtype=bool)
    keep[iy:iy+ih, ix:ix+iw] = grown
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
        kind = str(data.get('kind') or '')[:80]
        clase = _clase_de_pieza(kind)
        if clase == 'fondo':
            result, info = source, {'trimX': 0, 'trimY': 0, 'engine': 'fondo', 'removedFragments': 0}
        elif clase in ('placa', 'marco'):
            result, info = _recortar_desde_el_borde(source, clase, data.get('inner'))
        else:
            np = _need_numpy()
            rect = _cuadrado_de_simbolo(np.array(source.convert('RGB')), data.get('inner')) if _es_simbolo(kind) else None
            if rect is not None:
                result, info = _recortar_cuadrado(source, rect)
            else:
                result, info = _recortar_silueta(source, data.get('inner'))
                if not info.get('usable'):
                    result, info = _segment_cutout(source, data.get('inner'), kind)
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
