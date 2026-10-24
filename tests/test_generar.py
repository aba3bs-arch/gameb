"""La pieza se genera en el estudio, sin llamar a ChatGPT."""
import base64
import io
import unittest
from pathlib import Path

from PIL import Image
import numpy as np

from studio.desarmar.generar import generar_pieza


def _png(image):
    buf = io.BytesIO()
    image.save(buf, format='PNG')
    return 'data:image/png;base64,' + base64.b64encode(buf.getvalue()).decode('ascii')


def _abrir(body):
    return np.array(Image.open(io.BytesIO(base64.b64decode(body['image'].split(',', 1)[1]))).convert('RGBA'))


class GenerarPiezaTest(unittest.TestCase):
    def test_no_pide_el_dibujo_a_chatgpt(self):
        texto = Path('studio/desarmar/generar.py').read_text(encoding='utf-8')
        self.assertNotIn('openai', texto.lower())
        self.assertNotIn('urllib', texto)
        self.assertNotIn('api.openai', texto)

    def test_el_simbolo_sale_igual_al_boceto(self):
        ruido = np.zeros((180, 180, 3), np.uint8)
        for y in range(180):
            ruido[y, :, 0] = 20 + (y * 3) % 50
            ruido[y, :, 1] = 30 + (y % 17)
            ruido[y, :, 2] = 90 + (y % 29)
        ruido[40:140, 40:140] = (180, 90, 30)
        ruido[40:48, 40:140] = (230, 180, 40)
        ruido[132:140, 40:140] = (230, 180, 40)
        ruido[40:140, 40:48] = (230, 180, 40)
        ruido[40:140, 132:140] = (230, 180, 40)
        imagen = Image.fromarray(np.dstack([ruido, np.full((180, 180), 255, np.uint8)]), 'RGBA')
        status, body = generar_pieza({
            'image': _png(imagen),
            'kind': 'Símbolo simbolo_pieza',
            'inner': {'x': 22, 'y': 22, 'w': 136, 'h': 136},
        })
        self.assertEqual(status, 200, body)
        self.assertEqual(body['engine'], 'generado')
        self.assertIn('boceto', body['nota'])
        self.assertLess(body['width'], 120)
        self.assertLess(body['height'], 120)
        arr = _abrir(body)
        centro = arr[arr.shape[0] // 2, arr.shape[1] // 2]
        self.assertEqual(centro.tolist(), [180, 90, 30, 255])
        paisaje = (arr[:, :, 2] > 80) & (arr[:, :, 0] < 80) & (arr[:, :, 3] > 16)
        self.assertEqual(int(paisaje.sum()), 0)

    def test_la_escena_no_se_redibuja(self):
        imagen = Image.new('RGBA', (40, 30), (12, 40, 80, 255))
        status, body = generar_pieza({'image': _png(imagen), 'kind': 'Fondo fondo_principal'})
        self.assertEqual(status, 200, body)
        self.assertEqual(body['engine'], 'fondo')
        self.assertEqual(body['width'], 40)
        self.assertEqual(body['height'], 30)
        self.assertEqual(_abrir(body)[0, 0].tolist(), [12, 40, 80, 255])
