"""El programa arma el título. El modelo no decide el rectángulo final."""

TITLE_LAWS = '''Leyes del título, para cualquier boceto:
1. Un título es un solo letrero. Lee todas las palabras del nombre. Si hay más de una, la misma caja las cubre todas. Está prohibido encerrar solo la palabra más grande o la de más contraste.
2. La caja empieza antes de la primera letra y termina después de la última, de izquierda a derecha y de arriba a abajo.
3. Incluye lo que forma parte del mismo letrero aunque no sea letra: sombrero, corona, marco, cinta, flores, resplandor, sombra y adornos de arriba o de los lados.
4. No incluyas jackpots, cifras de premio, símbolos, personajes ni el paisaje. Si un adorno toca un jackpot, la caja llega hasta el adorno y no se traga el jackpot.
5. Si la caja corta una palabra o deja fuera un adorno del mismo letrero, hay que ampliarla. No la reduzcas a una sola palabra.'''

LEER_TITULO = '''Cómo devolver un título:
- No calcules el rectángulo final del letrero. El programa une las partes.
- En cada componente de tipo "Título / logo" el campo parts es obligatorio.
- Cada palabra es {"text":"PALABRA","role":"palabra","x":0,"y":0,"w":0,"h":0,"missing":false}.
- Cada adorno del mismo letrero es {"text":"sombrero","role":"adorno","x":0,"y":0,"w":0,"h":0,"missing":false}.
- x, y, w y h son píxeles de la imagen original y cubren solo esa palabra o ese adorno.
- Si una palabra se ve y no puedes fijar su caja, inclúyela con missing true. No la omitas y no inventes la caja.
- Los campos x, y, w y h del componente título no se usan como letrero.'''


def _is_title_kind(value):
    text = str(value or '').lower()
    return 'título' in text or 'titulo' in text or 'logo' in text or 'letrero' in text


def apply_title_review(current, proposal, width, height):
    """Acepta una caja de título solo si crece alrededor de la propuesta y no se traga la escena."""
    try:
        x = int(float(proposal.get('x')))
        y = int(float(proposal.get('y')))
        w = int(float(proposal.get('w')))
        h = int(float(proposal.get('h')))
    except (TypeError, ValueError, AttributeError):
        return None
    if width < 2 or height < 2 or w < 2 or h < 2:
        return None
    x = max(0, min(width - 1, x))
    y = max(0, min(height - 1, y))
    w = max(1, min(width - x, w))
    h = max(1, min(height - y, h))
    cx, cy, cw, ch = int(current['x']), int(current['y']), int(current['w']), int(current['h'])
    if w * h > 0.72 * width * height:
        return None
    if w < cw * 0.98 or h < ch * 0.85:
        return None
    ix = max(0, min(x + w, cx + cw) - max(x, cx))
    iy = max(0, min(y + h, cy + ch) - max(y, cy))
    if cw * ch <= 0 or (ix * iy) / float(cw * ch) < 0.8:
        return None
    words = proposal.get('words') if isinstance(proposal.get('words'), list) else []
    ornaments = proposal.get('ornaments') if isinstance(proposal.get('ornaments'), list) else []
    return {
        'x': x, 'y': y, 'w': w, 'h': h,
        'titleWords': [str(v)[:40] for v in words[:8] if str(v).strip()],
        'titleOrnaments': [str(v)[:40] for v in ornaments[:8] if str(v).strip()],
        'titleReviewed': True,
    }


def _missing_flag(part):
    value = part.get('missing')
    return value in (True, 1, '1', 'true', 'True', 'si', 'sí')


def _part_box(part, width, height):
    if not isinstance(part, dict) or _missing_flag(part):
        return None
    try:
        x = int(float(part.get('x')))
        y = int(float(part.get('y')))
        w = int(float(part.get('w')))
        h = int(float(part.get('h')))
    except (TypeError, ValueError):
        return None
    if width < 2 or height < 2 or w < 2 or h < 2:
        return None
    x = max(0, min(width - 1, x))
    y = max(0, min(height - 1, y))
    w = max(1, min(width - x, w))
    h = max(1, min(height - y, h))
    if w < 2 or h < 2:
        return None
    return x, y, w, h


def _union(boxes):
    x0 = min(box[0] for box in boxes)
    y0 = min(box[1] for box in boxes)
    x1 = max(box[0] + box[2] for box in boxes)
    y1 = max(box[1] + box[3] for box in boxes)
    return x0, y0, x1 - x0, y1 - y0


def _parts_of(component):
    parts = component.get('parts') if isinstance(component, dict) else None
    if isinstance(parts, list) and parts:
        return parts
    collected = []
    if not isinstance(component, dict):
        return collected
    for role, key in (('palabra', 'words'), ('adorno', 'ornaments')):
        values = component.get(key)
        if not isinstance(values, list):
            continue
        for value in values:
            if isinstance(value, dict):
                item = dict(value)
                item.setdefault('role', role)
                collected.append(item)
            elif role == 'palabra' and str(value).strip():
                collected.append({'text': str(value), 'role': role, 'missing': True})
    return collected


def unir_titulo(component, width, height):
    """Une la caja de cada palabra. Si falta una palabra, el título no se registra."""
    words = []
    ornaments = []
    boxes = []
    missing_words = []
    missing_ornaments = []
    for part in _parts_of(component)[:16]:
        if not isinstance(part, dict):
            continue
        role = str(part.get('role') or 'palabra').strip().lower()
        text = str(part.get('text') or part.get('name') or '').strip()[:40]
        if not text:
            continue
        box = _part_box(part, width, height)
        ornament = role in ('adorno', 'ornament', 'ornamento')
        if ornament:
            ornaments.append(text)
            if box:
                boxes.append(box)
            else:
                missing_ornaments.append(text)
        else:
            words.append(text)
            if box:
                boxes.append(box)
            else:
                missing_words.append(text)
    result = {
        'titleWords': words[:8],
        'titleOrnaments': ornaments[:8],
        'titleReviewed': True,
        'titleFailed': False,
        'skipSave': False,
        'titleReason': '',
    }
    if not words:
        result['titleFailed'] = True
        result['skipSave'] = True
        result['titleReason'] = 'El título no trajo la lista de palabras. No se armó el letrero ni se registró.'
        return result
    if missing_words:
        result['titleFailed'] = True
        result['skipSave'] = True
        result['titleReason'] = 'Falta la caja de: ' + ', '.join(missing_words[:8]) + '. El título no se registró.'
        if boxes:
            x, y, w, h = _union(boxes)
            result.update({'x': x, 'y': y, 'w': w, 'h': h})
        return result
    x, y, w, h = _union(boxes)
    if w * h > 0.72 * width * height:
        result['titleFailed'] = True
        result['skipSave'] = True
        result['titleReason'] = 'La unión del título cubre casi toda la escena. No se registró.'
        return result
    result.update({'x': x, 'y': y, 'w': w, 'h': h})
    detail = ' '.join(words)
    if ornaments:
        detail += '. Adornos: ' + ', '.join(ornaments)
    if missing_ornaments:
        detail += '. Sin caja para el adorno: ' + ', '.join(missing_ornaments[:6])
    result['titleReason'] = 'Título unido: ' + detail + '.'
    return result
