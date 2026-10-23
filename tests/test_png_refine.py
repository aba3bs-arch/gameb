"""Pruebas del recorte de PNG del desarmador, sin modelo remoto."""
import unittest
from PIL import Image, ImageDraw
import numpy as np

from studio.desarmar.fondo import clean_background
from studio.desarmar.recortar import refine_cutout


def _circle(draw, box, color):
    draw.ellipse(box, fill=color)


class RefineCutoutTest(unittest.TestCase):
    def test_quita_vecino_halo_y_recorta_al_objeto(self):
        w, h = 220, 140
        source = Image.new('RGBA', (w, h), (20, 90, 210, 255))
        draw = ImageDraw.Draw(source)
        _circle(draw, (40, 30, 120, 110), (220, 30, 40, 255))
        draw.rectangle((160, 40, 200, 90), fill=(140, 40, 200, 255))
        cut = np.zeros((h, w, 4), np.uint8)
        yy, xx = np.ogrid[:h, :w]
        circle = (xx - 80) ** 2 + (yy - 70) ** 2 <= 40 ** 2
        ring = ((xx - 80) ** 2 + (yy - 70) ** 2 <= 46 ** 2) & ~circle
        cut[circle, 0] = 220
        cut[circle, 1] = 30
        cut[circle, 2] = 40
        cut[circle, 3] = 255
        # Halo: color mezclado con el fondo azul y alfa parcial.
        alpha = 0.45
        bg = np.array([20, 90, 210], np.float32)
        fg = np.array([220, 30, 40], np.float32)
        cut[ring, :3] = np.clip(fg * alpha + bg * (1 - alpha), 0, 255).astype(np.uint8)
        cut[ring, 3] = int(alpha * 255)
        cut[40:90, 160:200] = (140, 40, 200, 255)
        inner = {'x': 30, 'y': 20, 'w': 100, 'h': 100}
        refined, info = refine_cutout(source, Image.fromarray(cut, 'RGBA'), inner)
        arr = np.array(refined)
        self.assertGreater(info['removedFragments'], 0)
        self.assertLess(refined.width, w - 20)
        purple = np.all(np.abs(arr[:, :, :3].astype(int) - np.array([140, 40, 200])) < 30, axis=2) & (arr[:, :, 3] > 16)
        self.assertEqual(int(purple.sum()), 0)
        cy, cx = arr.shape[0] // 2, arr.shape[1] // 2
        self.assertGreater(int(arr[cy, cx, 3]), 240)
        self.assertGreater(int(arr[cy, cx, 0]), int(arr[cy, cx, 2]) + 40)
        edge = (arr[:, :, 3] > 16) & (arr[:, :, 3] < 250)
        self.assertGreater(int(edge.sum()), 20)
        blue_fringe = (arr[:, :, 2] > 150) & (arr[:, :, 0] < 80) & (arr[:, :, 3] > 16)
        self.assertLess(int(blue_fringe.sum()), 15)

    def test_conserva_el_hueco_interior(self):
        source = Image.new('RGBA', (80, 80), (10, 120, 40, 255))
        cut = np.zeros((80, 80, 4), np.uint8)
        yy, xx = np.ogrid[:80, :80]
        ring = ((xx - 40) ** 2 + (yy - 40) ** 2 <= 30 ** 2) & ((xx - 40) ** 2 + (yy - 40) ** 2 >= 12 ** 2)
        cut[ring] = (240, 210, 40, 255)
        refined, _info = refine_cutout(source, Image.fromarray(cut, 'RGBA'), {'x': 8, 'y': 8, 'w': 64, 'h': 64})
        arr = np.array(refined)
        cy, cx = arr.shape[0] // 2, arr.shape[1] // 2
        self.assertLess(int(arr[cy, cx, 3]), 10)
        self.assertGreater(int(np.count_nonzero(arr[:, :, 3] > 200)), 40)

    def test_fondo_rellena_el_hueco_sin_el_color_de_la_pieza(self):
        w, h = 180, 100
        src = np.zeros((h, w, 4), np.uint8)
        for x in range(w):
            src[:, x, 0] = 20
            src[:, x, 1] = int(40 + 140 * x / w)
            src[:, x, 2] = int(180 - 100 * x / w)
            src[:, x, 3] = 255
        src[30:70, 70:120, :3] = (230, 20, 20)
        source = Image.fromarray(src, 'RGBA')
        mask = Image.new('RGBA', (w, h), (0, 0, 0, 0))
        ImageDraw.Draw(mask).rectangle((70, 30, 119, 69), fill=(255, 255, 255, 255))
        cleaned = clean_background(source, mask)
        out = np.array(cleaned)
        center = out[50, 95, :3].astype(int)
        self.assertLess(center[0], 120)
        self.assertGreater(center[1], 70)
        # Fuera del hueco, el degradado original se conserva.
        self.assertEqual(int(out[10, 10, 0]), 20)


if __name__ == '__main__':
    unittest.main()
