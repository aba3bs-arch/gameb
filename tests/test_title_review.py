"""La revisión de títulos no llama al modelo: solo acepta o rechaza la caja."""
import unittest
from PIL import Image
import numpy as np

import server


class TitleReviewTest(unittest.TestCase):
    def test_acepta_una_caja_que_crece_y_sigue_cubriendo_la_propuesta(self):
        current = {'x': 200, 'y': 40, 'w': 180, 'h': 70}
        proposal = {'x': 80, 'y': 10, 'w': 360, 'h': 120, 'words': ['TIERRA', 'MEXICANA'], 'ornaments': ['sombrero']}
        updated = server.apply_title_review(current, proposal, 1000, 600)
        self.assertEqual(updated['x'], 80)
        self.assertEqual(updated['w'], 360)
        self.assertEqual(updated['titleWords'], ['TIERRA', 'MEXICANA'])
        self.assertTrue(updated['titleReviewed'])

    def test_rechaza_quedarse_solo_con_una_palabra(self):
        current = {'x': 80, 'y': 10, 'w': 360, 'h': 120}
        proposal = {'x': 250, 'y': 40, 'w': 140, 'h': 60, 'words': ['MEXICANA']}
        self.assertIsNone(server.apply_title_review(current, proposal, 1000, 600))

    def test_rechaza_una_caja_que_se_traga_la_escena(self):
        current = {'x': 200, 'y': 40, 'w': 180, 'h': 70}
        proposal = {'x': 0, 'y': 0, 'w': 980, 'h': 560, 'words': ['TIERRA']}
        self.assertIsNone(server.apply_title_review(current, proposal, 1000, 600))

    def test_recupera_la_palabra_que_el_recorte_borro(self):
        source = Image.new('RGBA', (220, 80), (20, 70, 160, 255))
        px = source.load()
        for y in range(18, 62):
            for x in range(16, 90):
                px[x, y] = (30, 190, 50, 255)
            for x in range(120, 200):
                px[x, y] = (220, 40, 40, 255)
        cut = np.zeros((80, 220, 4), np.uint8)
        cut[18:62, 120:200] = (220, 40, 40, 255)
        restored = server._restore_title_letters(source, Image.fromarray(cut, 'RGBA'), (8, 10, 200, 60))
        arr = np.array(restored)
        self.assertGreater(int(np.count_nonzero(arr[18:62, 16:90, 3] > 200)), 400)
        self.assertGreater(int(np.count_nonzero(arr[18:62, 120:200, 3] > 200)), 400)


if __name__ == '__main__':
    unittest.main()
