"""Biblioteca local de PNG, JPG y WebP."""
import datetime
import re
import urllib.parse

from studio.datos import decode_data
from studio.paths import ASSET_DIR

_MIME = {'image/png': '.png', 'image/jpeg': '.jpg', 'image/webp': '.webp'}
_MIME_BY_SUFFIX = {'.png': 'image/png', '.jpg': 'image/jpeg', '.webp': 'image/webp'}


def importar(data):
    name = str(data.get('name', 'componente')).strip()[:100] or 'componente'
    mime = str(data.get('mimeType', ''))
    if mime not in _MIME:
        return 400, {'error': 'Formato no admitido. Usa PNG, JPG o WebP.'}
    head, raw = decode_data(data.get('data', ''))
    if len(raw) > 15 * 1024 * 1024:
        return 413, {'error': 'La imagen supera 15 MB.'}
    if not head.lower().startswith('data:' + mime):
        return 400, {'error': 'El tipo MIME no coincide con el archivo.'}
    slug = re.sub(r'[^a-zA-Z0-9_-]+', '_', name).strip('_')[:70] or 'componente'
    filename = slug + '_' + datetime.datetime.now().strftime('%Y%m%d_%H%M%S_%f') + _MIME[mime]
    target = (ASSET_DIR / filename).resolve()
    if ASSET_DIR.resolve() not in target.parents:
        return 400, {'error': 'Nombre de archivo no válido.'}
    target.write_bytes(raw)
    return 200, {
        'ok': True,
        'name': name,
        'filename': filename,
        'url': '/assets/imported/' + urllib.parse.quote(filename),
        'bytes': len(raw),
        'type': mime,
    }


def eliminar(data):
    filename = str(data.get('filename', ''))
    if not re.fullmatch(r'[A-Za-z0-9_-]+\.(?:png|jpg|webp)', filename, re.I):
        return 400, {'error': 'Nombre de archivo no válido.'}
    target = (ASSET_DIR / filename).resolve()
    if ASSET_DIR.resolve() not in target.parents:
        return 400, {'error': 'Ruta no válida.'}
    if not target.is_file():
        return 404, {'error': 'El componente no existe.'}
    target.unlink()
    return 200, {'ok': True}


def listar():
    assets = []
    for item in sorted(ASSET_DIR.iterdir(), key=lambda path: path.stat().st_mtime, reverse=True):
        if item.is_file() and item.suffix.lower() in _MIME_BY_SUFFIX:
            mime = _MIME_BY_SUFFIX[item.suffix.lower()]
            assets.append({
                'name': re.sub(r'_\d{8}_\d{6}_\d+\.(?:png|jpg|webp)$', '', item.name),
                'filename': item.name,
                'url': '/assets/imported/' + urllib.parse.quote(item.name),
                'bytes': item.stat().st_size,
                'type': mime,
            })
    return {'ok': True, 'assets': assets}
