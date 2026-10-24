"""Una imagen, tomada del recuadro del boceto.

No llama a ChatGPT. El color sale del boceto. Lo de afuera del objeto queda transparente.
"""
import base64
import io

import numpy as np
from PIL import Image

from studio.datos import decode_data


def hacer_imagen(data):
    """Respuesta de POST /api/hacer-imagen."""
    try:
        _head, raw = decode_data(data.get('image', ''))
    except Exception:
        return 400, {'ok': False, 'error': 'La imagen no es válida.'}
    if len(raw) > 15 * 1024 * 1024:
        return 413, {'ok': False, 'error': 'La imagen supera 15 MB.'}
    try:
        source = Image.open(io.BytesIO(raw)).convert('RGBA')
    except Exception:
        return 400, {'ok': False, 'error': 'No se pudo abrir la imagen.'}
    if source.width < 2 or source.height < 2:
        return 400, {'ok': False, 'error': 'El recuadro está vacío.'}
    kind = str(data.get('kind') or '')[:80].lower()
    nota = 'Imagen hecha desde el boceto.'
    if 'fondo' in kind:
        result = source
        nota = 'El fondo es el boceto completo.'
    else:
        rgb = np.array(source.convert('RGB'))
        rect = _rectangulo(rgb) if 'simbolo' in kind.replace('í', 'i') else None
        if rect is not None:
            result = _copiar_rectangulo(source, rect)
            nota = 'Salió el cuadrado completo, sin el paisaje de alrededor.'
        else:
            result = _soltar_borde(source)
            if result is None:
                result = source
                nota = 'No se pudo separar el alrededor. Quedó el recorte de esa pieza.'
            else:
                if 'marco' in kind:
                    result = _vaciar_centro(result)
                    nota = 'Salió el marco. El centro quedó transparente.'
                elif 'jackpot' in kind:
                    result = _quitar_monto(result)
                    nota = 'Salió la placa. El monto quedó del color de la placa.'
                result = _recortar_vacio(result)
    encoded = _png(result)
    return 200, {
        'ok': True,
        'image': 'data:image/png;base64,' + encoded,
        'width': result.width,
        'height': result.height,
        'nota': nota,
    }


def _png(image):
    out = io.BytesIO()
    image.save(out, format='PNG', optimize=True)
    return base64.b64encode(out.getvalue()).decode('ascii')


def _rectangulo(rgb):
    """Un cuadrado es un borde recto y continuo, no un dibujo concreto."""
    alto, ancho = rgb.shape[:2]
    if alto < 32 or ancho < 32:
        return None
    color = rgb.astype(np.int16)
    salto_x = np.zeros((alto, ancho), np.float32)
    salto_y = np.zeros((alto, ancho), np.float32)
    salto_x[:, 1:] = np.max(np.abs(color[:, 1:] - color[:, :-1]), axis=2)
    salto_y[1:, :] = np.max(np.abs(color[1:, :] - color[:-1, :]), axis=2)
    margen_x = max(2, int(ancho * 0.04))
    margen_y = max(2, int(alto * 0.04))
    x0, y0 = margen_x, margen_y
    x1, y1 = ancho - margen_x, alto - margen_y
    if x1 - x0 < 28 or y1 - y0 < 28:
        return None
    columnas = salto_x[y0:y1, x0:x1].mean(axis=0)
    filas = salto_y[y0:y1, x0:x1].mean(axis=1)
    mitad_x, mitad_y = len(columnas) // 2, len(filas) // 2
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
    ancho_rect = derecha - izquierda
    alto_rect = abajo - arriba
    proporcion = ancho_rect / float(alto_rect)
    if proporcion < 0.80 or proporcion > 1.25:
        return None
    return {'x': x0 + izquierda, 'y': y0 + arriba, 'w': ancho_rect, 'h': alto_rect}


def _copiar_rectangulo(source, rect):
    arr = np.array(source.convert('RGBA'))
    x0 = max(0, int(rect['x']))
    y0 = max(0, int(rect['y']))
    x1 = min(arr.shape[1], x0 + int(rect['w']))
    y1 = min(arr.shape[0], y0 + int(rect['h']))
    recorte = arr[y0:y1, x0:x1].copy()
    recorte[:, :, 3] = 255
    return Image.fromarray(recorte, 'RGBA')


def _soltar_borde(source, salto=28):
    """Quita el color que toca el borde del recuadro. El dibujo se queda con su color."""
    arr = np.array(source.convert('RGBA'))
    alto, ancho = arr.shape[:2]
    if alto < 3 or ancho < 3:
        return None
    color = arr[:, :, :3].astype(np.int16)
    borde = np.zeros((alto, ancho), dtype=bool)
    borde[0, :] = borde[-1, :] = True
    borde[:, 0] = borde[:, -1] = True
    ref = np.median(color[borde], axis=0)
    fuera = np.zeros((alto, ancho), dtype=bool)
    pila = []
    ys, xs = np.nonzero(borde)
    for y, x in zip(ys.tolist(), xs.tolist()):
        if int(np.max(np.abs(color[y, x] - ref))) <= salto:
            fuera[y, x] = True
            pila.append((y, x))
    while pila:
        y, x = pila.pop()
        for ny, nx in ((y - 1, x), (y + 1, x), (y, x - 1), (y, x + 1)):
            if ny < 0 or nx < 0 or ny >= alto or nx >= ancho or fuera[ny, nx]:
                continue
            if int(np.max(np.abs(color[ny, nx] - ref))) > salto:
                continue
            fuera[ny, nx] = True
            pila.append((ny, nx))
    proporcion = float(fuera.mean())
    if proporcion < 0.02 or proporcion > 0.92:
        return None
    arr[fuera, 3] = 0
    arr[fuera, :3] = 0
    return Image.fromarray(arr, 'RGBA')


def _componentes(mask):
    """Etiqueta manchas separadas. La del centro del marco no toca el borde."""
    from collections import deque
    alto, ancho = mask.shape
    etiquetas = np.zeros((alto, ancho), np.int32)
    total = 0
    ys, xs = np.nonzero(mask)
    for y, x in zip(ys.tolist(), xs.tolist()):
        if etiquetas[y, x]:
            continue
        total += 1
        pila = deque([(y, x)])
        etiquetas[y, x] = total
        while pila:
            cy, cx = pila.popleft()
            for ny, nx in ((cy - 1, cx), (cy + 1, cx), (cy, cx - 1), (cy, cx + 1)):
                if ny < 0 or nx < 0 or ny >= alto or nx >= ancho or not mask[ny, nx] or etiquetas[ny, nx]:
                    continue
                etiquetas[ny, nx] = total
                pila.append((ny, nx))
    return etiquetas, total


def _vaciar_centro(image):
    """El marco se queda. Lo que está encerrado en la ventana interior sale."""
    arr = np.array(image.convert('RGBA'))
    solido = arr[:, :, 3] > 16
    ys, xs = np.nonzero(solido)
    if len(xs) < 30:
        return image
    x0, x1 = int(xs.min()), int(xs.max()) + 1
    y0, y1 = int(ys.min()), int(ys.max()) + 1
    ancho, alto = x1 - x0, y1 - y0
    if ancho < 24 or alto < 24:
        return image
    margen_x = max(2, int(ancho * 0.08))
    margen_y = max(2, int(alto * 0.08))
    anillo = np.zeros(solido.shape, dtype=bool)
    anillo[y0:y0 + margen_y, x0:x1] = True
    anillo[y1 - margen_y:y1, x0:x1] = True
    anillo[y0:y1, x0:x0 + margen_x] = True
    anillo[y0:y1, x1 - margen_x:x1] = True
    muestra = solido & anillo
    if int(muestra.sum()) < 12:
        return image
    marco = np.median(arr[:, :, :3][muestra].astype(np.int16), axis=0)
    distinto = solido & (np.max(np.abs(arr[:, :, :3].astype(np.int16) - marco), axis=2) > 36)
    etiquetas, total = _componentes(distinto)
    if total == 0:
        return image
    borde = np.zeros(distinto.shape, dtype=bool)
    borde[0, :] = borde[-1, :] = True
    borde[:, 0] = borde[:, -1] = True
    for indice in range(1, total + 1):
        mancha = etiquetas == indice
        if int(mancha.sum()) < 20 or np.any(mancha & borde):
            continue
        arr[mancha, 3] = 0
        arr[mancha, :3] = 0
    return Image.fromarray(arr, 'RGBA')


def _quitar_monto(image):
    """La palabra de arriba se queda. Las líneas de abajo se rellenan con el color de la placa."""
    arr = np.array(image.convert('RGBA'))
    solido = arr[:, :, 3] > 16
    if int(solido.sum()) < 40:
        return image
    color = arr[:, :, :3].astype(np.int16)
    placa = np.median(color[solido], axis=0)
    tinta = (np.max(np.abs(color - placa), axis=2) > 48) & solido
    filas = tinta.sum(axis=1)
    if int(filas.max()) < 4:
        return image
    activo = filas >= max(4, int(filas.max()) * 0.35)
    lineas = []
    inicio = None
    for y, si in enumerate(activo.tolist()):
        if si and inicio is None:
            inicio = y
        elif not si and inicio is not None:
            lineas.append((inicio, y))
            inicio = None
    if inicio is not None:
        lineas.append((inicio, len(activo)))
    lineas = [linea for linea in lineas if linea[1] - linea[0] >= 2]
    if len(lineas) < 2:
        return image
    for y0, y1 in lineas[1:]:
        pintar = tinta[y0:y1]
        arr[y0:y1, :, :3][pintar] = np.clip(placa, 0, 255).astype(np.uint8)
    return Image.fromarray(arr, 'RGBA')


def _recortar_vacio(image):
    arr = np.array(image.convert('RGBA'))
    ys, xs = np.nonzero(arr[:, :, 3] > 8)
    if len(xs) == 0:
        return image
    x0 = max(0, int(xs.min()) - 1)
    y0 = max(0, int(ys.min()) - 1)
    x1 = min(arr.shape[1], int(xs.max()) + 2)
    y1 = min(arr.shape[0], int(ys.max()) + 2)
    return Image.fromarray(arr[y0:y1, x0:x1], 'RGBA')
