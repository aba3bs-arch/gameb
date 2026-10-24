"""Lectura de imágenes enviadas como data URL."""
import base64


def decode_data(data):
    if not isinstance(data, str) or ',' not in data:
        raise ValueError('Imagen no válida')
    head, b64 = data.split(',', 1)
    return head, base64.b64decode(b64)
