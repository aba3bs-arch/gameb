"""La lámina manda: un PNG por objeto, placas sin cifra y marco con el centro vacío."""
import re

from studio.desarmar.fondo import _pyramid_fill
from studio.desarmar.recortar import Image, _dilate_bool, _need_numpy

CATALOGO = '''Lámina de salida, para cualquier boceto:
- Un objeto, un PNG. No agrupes botones, símbolos ni placas.
- Fondo: un solo componente, id fondo_principal, tipo Fondo. Es la escena completa, sin título, placas, símbolos, marco ni botones.
- Título: id titulo_ y el nombre del juego. Las palabras y adornos siguen en parts.
- Marco de rodillos: un solo componente, id marco_rodillos. El campo hole es la ventana interior, sin el marco. El centro del PNG queda transparente. hole usa x, y, w, h en píxeles de la imagen.
- Jackpots: cuatro placas si se ven, id jackpot_grand, jackpot_major, jackpot_minor, jackpot_mini. La caja es la placa con su palabra. El monto no es un componente: va en parts con role cifra y el programa lo borra.
- Paneles de apuesta, créditos y ganancia: id panel_apuesta, panel_creditos, panel_ganancia. La cifra también va en parts con role cifra.
- Símbolos: uno por dibujo, id simbolo_ y el nombre (simbolo_charro, simbolo_calavera).
- Botones: uno por control, id boton_info, boton_menos, boton_mas, boton_turbo, boton_girar.
- Los letreros de líneas sí llevan su texto. Son tipo Contador, id indicador_lineas_izq e indicador_lineas_der. No uses role cifra en ellos.
- role cifra solo marca montos como $100,000 o 500.00. Nunca la palabra GRAND, MAJOR, MINOR, MINI, APUESTA, CREDITOS o GANANCIA.'''

_FOLDS = str.maketrans('áéíóúüñÁÉÍÓÚÜÑ', 'aeiouunAEIOUUN')
_ROLES_CIFRA = {'cifra', 'numero', 'número', 'monto', 'cantidad'}
_BOTONES = (
    ('menos', 'boton_menos'),
    ('minus', 'boton_menos'),
    ('mas', 'boton_mas'),
    ('plus', 'boton_mas'),
    ('turbo', 'boton_turbo'),
    ('girar', 'boton_girar'),
    ('spin', 'boton_girar'),
    ('info', 'boton_info'),
)


def _slug(text):
    folded = str(text or '').translate(_FOLDS).lower()
    return re.sub(r'[^a-z0-9]+', '_', folded).strip('_')[:48]


def _tiene(blob, word):
    return re.search(rf'(^|_){re.escape(word)}(s|es)?(_|$)', blob or '') is not None


def _blob(comp):
    return _slug(' '.join(str(comp.get(key) or '') for key in ('id', 'name', 'type')))


def _texto(comp):
    nombre = _sin_repetidos(_slug(comp.get('name') or ''))
    if nombre:
        return nombre
    return _sin_repetidos(_slug(comp.get('id') or ''))


def _sin_repetidos(slug):
    tokens = []
    for token in str(slug or '').split('_'):
        if token and (not tokens or tokens[-1] != token):
            tokens.append(token)
    return '_'.join(tokens)


def es_fondo(comp):
    if str(comp.get('type') or '') == 'Fondo':
        return True
    texto = _texto(comp)
    return texto in ('fondo', 'fondo_principal', 'fondo_base', 'escena') or texto.startswith('fondo_')


def es_marco(comp):
    return _tiene(_blob(comp), 'marco')


def es_placa(comp):
    tipo = str(comp.get('type') or '')
    if tipo in ('Jackpot', 'Panel'):
        return True
    blob = _blob(comp)
    return any(_tiene(blob, word) for word in ('jackpot', 'apuesta', 'credito', 'ganancia'))


def es_solo_cifra(comp):
    """Un monto suelto no es un PNG. El letrero de líneas sí lo es."""
    if es_placa(comp) or es_marco(comp) or es_fondo(comp):
        return False
    if str(comp.get('type') or '') in ('Símbolo', 'Botón', 'Título / logo'):
        return False
    if _tiene(_blob(comp), 'linea'):
        return False
    visible = str(comp.get('name') or comp.get('id') or '')
    digits = len(re.findall(r'\d', visible))
    letters = len(re.findall(r'[A-Za-zÁÉÍÓÚÜÑáéíóúüñ]', visible))
    if '$' in visible or '€' in visible or '£' in visible:
        return digits >= 1 and letters <= 4
    return digits >= 2 and letters <= 1


def _caja(raw, width, height):
    if not isinstance(raw, dict):
        return None
    try:
        x = int(float(raw.get('x')))
        y = int(float(raw.get('y')))
        w = int(float(raw.get('w')))
        h = int(float(raw.get('h')))
    except (TypeError, ValueError):
        return None
    if w < 2 or h < 2 or width < 2 or height < 2:
        return None
    x = max(0, min(width - 1, x))
    y = max(0, min(height - 1, y))
    w = max(1, min(width - x, w))
    h = max(1, min(height - y, h))
    if w < 2 or h < 2:
        return None
    return {'x': x, 'y': y, 'w': w, 'h': h}


def _area(box):
    return max(0, int(box['w'])) * max(0, int(box['h']))


def _interseccion(a, b):
    x0 = max(a['x'], b['x'])
    y0 = max(a['y'], b['y'])
    x1 = min(a['x'] + a['w'], b['x'] + b['w'])
    y1 = min(a['y'] + a['h'], b['y'] + b['h'])
    if x1 <= x0 or y1 <= y0:
        return 0
    return (x1 - x0) * (y1 - y0)


def _dentro(inner, outer):
    if inner['x'] < outer['x'] - 2 or inner['y'] < outer['y'] - 2:
        return False
    if inner['x'] + inner['w'] > outer['x'] + outer['w'] + 2:
        return False
    if inner['y'] + inner['h'] > outer['y'] + outer['h'] + 2:
        return False
    exterior = _area(outer)
    if exterior < 1:
        return False
    ratio = _area(inner) / exterior
    return 0.15 <= ratio <= 0.92


def _hueco_estimado(frame):
    mx = max(2, int(round(frame['w'] * 0.08)))
    my = max(2, int(round(frame['h'] * 0.08)))
    hole = {'x': frame['x'] + mx, 'y': frame['y'] + my, 'w': frame['w'] - 2 * mx, 'h': frame['h'] - 2 * my}
    if hole['w'] < 4 or hole['h'] < 4:
        return None
    return hole


def _nombre(comp):
    blob = _blob(comp)
    texto = _texto(comp)
    if es_fondo(comp):
        return 'fondo_principal'
    if es_marco(comp):
        return 'marco_rodillos'
    if str(comp.get('type') or '') == 'Jackpot' or _tiene(blob, 'jackpot'):
        for tier, filename in (
            ('grand', 'jackpot_grand'),
            ('major', 'jackpot_major'),
            ('mayor', 'jackpot_major'),
            ('minor', 'jackpot_minor'),
            ('menor', 'jackpot_minor'),
            ('mini', 'jackpot_mini'),
        ):
            if _tiene(blob, tier):
                return filename
    for word, filename in (('apuesta', 'panel_apuesta'), ('credito', 'panel_creditos'), ('ganancia', 'panel_ganancia')):
        if _tiene(blob, word) and (str(comp.get('type') or '') in ('Panel', 'Contador', 'Jackpot') or _tiene(blob, 'panel') or _tiene(blob, 'contador')):
            return filename
    if _tiene(blob, 'linea'):
        return 'indicador_lineas'
    if str(comp.get('type') or '') == 'Botón' or _tiene(blob, 'boton'):
        for token, filename in _BOTONES:
            if _tiene(blob, token):
                return filename
        rest = re.sub(r'(^|_)boton(_|$)', '_', texto).strip('_')
        return 'boton_' + (rest or 'control')
    if str(comp.get('type') or '') == 'Símbolo' or _tiene(blob, 'simbolo'):
        rest = re.sub(r'(^|_)simbolo(_|$)', '_', texto).strip('_')
        return 'simbolo_' + (_sin_repetidos(rest) or 'pieza')
    if any(_tiene(blob, word) for word in ('titulo', 'logo', 'letrero')):
        words = [str(word) for word in comp.get('titleWords') or [] if str(word).strip()]
        if words:
            return 'titulo_' + _slug('_'.join(words))
        rest = texto
        for stop in ('letrero', 'titulo', 'logotipo', 'logo', 'con', 'sombrero', 'adorno', 'adornos', 'y'):
            rest = re.sub(rf'(^|_){stop}(_|$)', '_', '_' + rest + '_')
        rest = _sin_repetidos(re.sub(r'_+', '_', rest).strip('_'))
        return 'titulo_' + (rest or 'logo')
    return texto or 'componente'


def _cifras_en_partes(comp, width, height):
    boxes = []
    parts = comp.get('_parts')
    if not isinstance(parts, list):
        return boxes
    for part in parts[:16]:
        if not isinstance(part, dict):
            continue
        role = str(part.get('role') or '').strip().lower()
        if role not in _ROLES_CIFRA:
            continue
        box = _caja(part, width, height)
        if box:
            boxes.append(box)
    return boxes


def _placa_para(cifra, placas):
    mejor = None
    mejor_cruze = 0
    area = _area(cifra)
    for placa in placas:
        cruze = _interseccion(cifra, placa)
        if area and cruze / area >= 0.35 and cruze > mejor_cruze:
            mejor = placa
            mejor_cruze = cruze
    if mejor:
        return mejor
    for placa in placas:
        solape = max(0, min(cifra['x'] + cifra['w'], placa['x'] + placa['w']) - max(cifra['x'], placa['x']))
        if cifra['w'] < 1 or solape / cifra['w'] < 0.4:
            continue
        arriba = cifra['y'] + cifra['h']
        abajo = placa['y'] + placa['h']
        separacion = max(cifra['y'] - abajo, placa['y'] - arriba, 0)
        if separacion <= max(8, int(placa['h'] * 0.12)):
            return placa
    return None


def _lados_de_lineas(comps):
    lineas = [comp for comp in comps if comp.get('fileName') == 'indicador_lineas']
    lineas.sort(key=lambda comp: (comp.get('x', 0), comp.get('y', 0)))
    if len(lineas) == 1:
        blob = _blob(lineas[0])
        if 'der' in blob or 'derecha' in blob or 'right' in blob:
            lineas[0]['fileName'] = 'indicador_lineas_der'
        else:
            lineas[0]['fileName'] = 'indicador_lineas_izq'
        return
    if len(lineas) >= 1:
        lineas[0]['fileName'] = 'indicador_lineas_izq'
    if len(lineas) >= 2:
        lineas[1]['fileName'] = 'indicador_lineas_der'


def _unicos(comps):
    usados = {}
    for comp in comps:
        base = comp.get('fileName') or 'componente'
        cuenta = usados.get(base, 0) + 1
        usados[base] = cuenta
        comp['fileName'] = base if cuenta == 1 else f'{base}_{cuenta}'


def preparar_catalogo(comps, width, height):
    """Asigna el archivo de la lámina, vacía el marco y aparta las cifras."""
    notes = []
    for comp in comps:
        comp['fileName'] = _nombre(comp)
        if es_marco(comp):
            hole = _caja(comp.get('_hole'), width, height)
            frame = {'x': comp['x'], 'y': comp['y'], 'w': comp['w'], 'h': comp['h']}
            if hole and _dentro(hole, frame):
                comp['hole'] = hole
                comp['holeEstimated'] = False
            else:
                estimado = _hueco_estimado(frame)
                if estimado:
                    comp['hole'] = estimado
                    comp['holeEstimated'] = True
                    notes.append('Marco de rodillos: el centro se estimó porque no vino la ventana interior.')
        if es_placa(comp):
            comp['erase'] = _cifras_en_partes(comp, width, height)
        comp.pop('_parts', None)
        comp.pop('_hole', None)
    placas = [comp for comp in comps if es_placa(comp)]
    quedaron = []
    for comp in comps:
        if not es_solo_cifra(comp):
            quedaron.append(comp)
            continue
        caja = {'x': comp['x'], 'y': comp['y'], 'w': comp['w'], 'h': comp['h']}
        placa = _placa_para(caja, placas)
        if placa is not None:
            placa.setdefault('erase', []).append(caja)
            notes.append('La cifra «' + comp['name'] + '» se quita de ' + placa['name'] + '.')
        else:
            notes.append('La cifra «' + comp['name'] + '» no se guarda como PNG.')
    _lados_de_lineas(quedaron)
    _unicos(quedaron)
    return quedaron, notes


def _desplazar(box, trim_x, trim_y, width, height):
    if not isinstance(box, dict):
        return None
    try:
        x = int(float(box.get('x'))) - int(trim_x)
        y = int(float(box.get('y'))) - int(trim_y)
        w = int(float(box.get('w')))
        h = int(float(box.get('h')))
    except (TypeError, ValueError):
        return None
    if w < 2 or h < 2:
        return None
    x0 = max(0, x)
    y0 = max(0, y)
    x1 = min(width, x + w)
    y1 = min(height, y + h)
    if x1 - x0 < 2 or y1 - y0 < 2:
        return None
    return {'x': x0, 'y': y0, 'w': x1 - x0, 'h': y1 - y0}


def vaciar_hueco(image, hole):
    """Deja transparente la ventana interior del marco."""
    np = _need_numpy()
    if Image is None or hole is None:
        return image
    arr = np.array(image.convert('RGBA'))
    local = _desplazar(hole, 0, 0, arr.shape[1], arr.shape[0])
    if local is None:
        return image
    if _area(local) > arr.shape[0] * arr.shape[1] * 0.92:
        return image
    y0, x0 = local['y'], local['x']
    y1, x1 = y0 + local['h'], x0 + local['w']
    arr[y0:y1, x0:x1, 3] = 0
    arr[y0:y1, x0:x1, :3] = 0
    return Image.fromarray(arr, 'RGBA')


def borrar_cifras(image, boxes):
    """Rellena el monto con el color de la placa. La placa sigue opaca."""
    np = _need_numpy()
    if Image is None or not boxes:
        return image
    arr = np.array(image.convert('RGBA'))
    hole = np.zeros(arr.shape[:2], dtype=bool)
    for box in boxes:
        local = _desplazar(box, 0, 0, arr.shape[1], arr.shape[0])
        if local is None:
            continue
        hole[local['y']:local['y'] + local['h'], local['x']:local['x'] + local['w']] = True
    if not np.any(hole):
        return image
    hole = _dilate_bool(hole, 1)
    if float(hole.mean()) > 0.72:
        return image
    filled = _pyramid_fill(arr[:, :, :3].astype(np.float32), hole)
    arr[:, :, :3][hole] = np.clip(filled[hole], 0, 255).astype(np.uint8)
    arr[:, :, 3][hole] = 255
    return Image.fromarray(arr, 'RGBA')


def aplicar_lamina(image, trim_x=0, trim_y=0, hole=None, erase=None, kind=''):
    """Después del recorte: centro del marco vacío y cifras fuera de la placa."""
    width, height = image.size
    if es_marco({'type': kind, 'name': kind, 'id': kind}):
        local = _desplazar(hole, trim_x, trim_y, width, height) if hole else _hueco_estimado({'x': 0, 'y': 0, 'w': width, 'h': height})
        image = vaciar_hueco(image, local)
    boxes = []
    for box in erase or []:
        local = _desplazar(box, trim_x, trim_y, width, height)
        if local:
            boxes.append(local)
    if boxes:
        image = borrar_cifras(image, boxes)
    return image
