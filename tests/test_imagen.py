"""Una imagen por vez, sin llamar a ChatGPT."""
import base64
import io
import unittest
from pathlib import Path

import numpy as np
from PIL import Image

from studio.imagen import hacer_imagen


def _png(image):
    buf = io.BytesIO()
    image.save(buf, format='PNG')
    return 'data:image/png;base64,' + base64.b64encode(buf.getvalue()).decode('ascii')


def _abrir(body):
    return np.array(Image.open(io.BytesIO(base64.b64decode(body['image'].split(',', 1)[1]))).convert('RGBA'))


class HacerImagenTest(unittest.TestCase):
    def test_no_llama_a_chatgpt(self):
        texto = Path('studio/imagen.py').read_text(encoding='utf-8')
        self.assertNotIn('openai', texto.lower())
        self.assertNotIn('urllib', texto)

    def test_el_simbolo_sale_sin_el_paisaje(self):
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
        status, body = hacer_imagen({'image': _png(imagen), 'kind': 'Símbolo pieza'})
        self.assertEqual(status, 200, body)
        self.assertLess(body['width'], 120)
        self.assertLess(body['height'], 120)
        centro = _abrir(body)
        pixel = centro[centro.shape[0] // 2, centro.shape[1] // 2]
        self.assertEqual(pixel.tolist(), [180, 90, 30, 255])

    def test_la_figura_suelta_el_fondo(self):
        imagen = Image.new('RGBA', (140, 140), (20, 70, 160, 255))
        pixel = imagen.load()
        for y in range(140):
            for x in range(140):
                if (x - 70) ** 2 + (y - 70) ** 2 <= 36 ** 2:
                    pixel[x, y] = (210, 40, 40, 255)
        status, body = hacer_imagen({'image': _png(imagen), 'kind': 'Título logo'})
        self.assertEqual(status, 200, body)
        arr = _abrir(body)
        rojo = (arr[:, :, 0] > 180) & (arr[:, :, 1] < 80) & (arr[:, :, 3] > 200)
        azul = (arr[:, :, 2] > 120) & (arr[:, :, 0] < 80) & (arr[:, :, 3] > 16)
        self.assertGreater(int(rojo.sum()), 200)
        self.assertEqual(int(azul.sum()), 0)

    def test_el_fondo_queda_entero(self):
        imagen = Image.new('RGBA', (40, 30), (12, 40, 80, 255))
        status, body = hacer_imagen({'image': _png(imagen), 'kind': 'Fondo fondo principal'})
        self.assertEqual(status, 200, body)
        self.assertEqual((body['width'], body['height']), (40, 30))
        self.assertEqual(_abrir(body)[0, 0].tolist(), [12, 40, 80, 255])

    def test_la_placa_conserva_la_palabra_y_tapa_el_monto(self):
        imagen = Image.new('RGBA', (160, 80), (20, 50, 140, 255))
        pixel = imagen.load()
        for y in range(8, 72):
            for x in range(8, 152):
                pixel[x, y] = (20, 70, 170, 255)
        for y in range(18, 32):
            for x in range(40, 120):
                pixel[x, y] = (245, 245, 245, 255)
        for y in range(46, 64):
            for x in range(36, 124):
                pixel[x, y] = (245, 220, 80, 255)
        status, body = hacer_imagen({'image': _png(imagen), 'kind': 'Jackpot minor'})
        self.assertEqual(status, 200, body)
        arr = _abrir(body)
        blanco = (arr[:, :, 0] > 220) & (arr[:, :, 1] > 220) & (arr[:, :, 2] > 220) & (arr[:, :, 3] > 200)
        oro = (arr[:, :, 0] > 200) & (arr[:, :, 1] > 180) & (arr[:, :, 2] < 120) & (arr[:, :, 3] > 200)
        self.assertGreater(int(blanco.sum()), 80)
        self.assertEqual(int(oro.sum()), 0)

    def test_el_marco_deja_el_centro_vacio(self):
        imagen = Image.new('RGBA', (120, 100), (30, 140, 40, 255))
        pixel = imagen.load()
        for y in range(10, 90):
            for x in range(10, 110):
                pixel[x, y] = (40, 90, 200, 255)
        for y in range(10, 90):
            for x in range(10, 110):
                if x < 24 or x >= 96 or y < 22 or y >= 78:
                    pixel[x, y] = (210, 160, 40, 255)
        status, body = hacer_imagen({'image': _png(imagen), 'kind': 'Marco rodillos'})
        self.assertEqual(status, 200, body)
        arr = _abrir(body)
        oro = (arr[:, :, 0] > 180) & (arr[:, :, 1] > 120) & (arr[:, :, 2] < 80) & (arr[:, :, 3] > 200)
        azul = (arr[:, :, 2] > 150) & (arr[:, :, 0] < 80) & (arr[:, :, 3] > 16)
        verde = (arr[:, :, 1] > 110) & (arr[:, :, 0] < 80) & (arr[:, :, 3] > 16)
        self.assertGreater(int(oro.sum()), 200)
        self.assertEqual(int(azul.sum()), 0)
        self.assertEqual(int(verde.sum()), 0)
