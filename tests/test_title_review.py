"""La revisión de títulos no llama al modelo: solo acepta o rechaza la caja."""
import unittest
from PIL import Image
import numpy as np

from studio.desarmar.inspeccionar import listo_para_registrar
from studio.desarmar.recortar import _restore_title_letters
from studio.desarmar.unir import apply_title_review, unir_titulo
from studio.http import asset_path


class TitleReviewTest(unittest.TestCase):
    def test_acepta_una_caja_que_crece_y_sigue_cubriendo_la_propuesta(self):
        current = {'x': 200, 'y': 40, 'w': 180, 'h': 70}
        proposal = {'x': 80, 'y': 10, 'w': 360, 'h': 120, 'words': ['TIERRA', 'MEXICANA'], 'ornaments': ['sombrero']}
        updated = apply_title_review(current, proposal, 1000, 600)
        self.assertEqual(updated['x'], 80)
        self.assertEqual(updated['w'], 360)
        self.assertEqual(updated['titleWords'], ['TIERRA', 'MEXICANA'])
        self.assertTrue(updated['titleReviewed'])

    def test_rechaza_quedarse_solo_con_una_palabra(self):
        current = {'x': 80, 'y': 10, 'w': 360, 'h': 120}
        proposal = {'x': 250, 'y': 40, 'w': 140, 'h': 60, 'words': ['MEXICANA']}
        self.assertIsNone(apply_title_review(current, proposal, 1000, 600))

    def test_rechaza_una_caja_que_se_traga_la_escena(self):
        current = {'x': 200, 'y': 40, 'w': 180, 'h': 70}
        proposal = {'x': 0, 'y': 0, 'w': 980, 'h': 560, 'words': ['TIERRA']}
        self.assertIsNone(apply_title_review(current, proposal, 1000, 600))

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
        restored = _restore_title_letters(source, Image.fromarray(cut, 'RGBA'), (8, 10, 200, 60))
        arr = np.array(restored)
        self.assertGreater(int(np.count_nonzero(arr[18:62, 16:90, 3] > 200)), 400)
        self.assertGreater(int(np.count_nonzero(arr[18:62, 120:200, 3] > 200)), 400)

    def test_une_cada_palabra_y_el_adorno(self):
        component = {'parts': [
            {'text': 'TIERRA', 'role': 'palabra', 'x': 40, 'y': 20, 'w': 90, 'h': 40},
            {'text': 'MEXICANA', 'role': 'palabra', 'x': 150, 'y': 18, 'w': 140, 'h': 48},
            {'text': 'sombrero', 'role': 'adorno', 'x': 70, 'y': 2, 'w': 60, 'h': 24},
        ]}
        united = unir_titulo(component, 1000, 600)
        self.assertFalse(united['titleFailed'])
        self.assertEqual((united['x'], united['y'], united['w'], united['h']), (40, 2, 250, 64))
        self.assertEqual(united['titleWords'], ['TIERRA', 'MEXICANA'])
        self.assertFalse(united['skipSave'])

    def test_una_palabra_sin_caja_bloquea_el_registro(self):
        component = {'x': 400, 'y': 0, 'w': 180, 'h': 70, 'parts': [
            {'text': 'TIERRA', 'role': 'palabra', 'missing': True},
            {'text': 'MEXICANA', 'role': 'palabra', 'x': 150, 'y': 18, 'w': 140, 'h': 48},
        ]}
        united = unir_titulo(component, 1000, 600)
        self.assertTrue(united['titleFailed'])
        self.assertTrue(united['skipSave'])
        self.assertIn('TIERRA', united['titleReason'])
        self.assertEqual(united['x'], 150)
        self.assertNotEqual(united['w'], 180)

    def test_sin_palabras_no_adopta_el_rectangulo_del_modelo(self):
        united = unir_titulo({'x': 400, 'y': 0, 'w': 180, 'h': 70, 'parts': []}, 1000, 600)
        self.assertTrue(united['titleFailed'])
        self.assertTrue(united['skipSave'])
        self.assertNotIn('x', united)

    def test_la_union_no_puede_tragarse_la_escena(self):
        united = unir_titulo({'parts': [
            {'text': 'TIERRA', 'role': 'palabra', 'x': 0, 'y': 0, 'w': 900, 'h': 500},
            {'text': 'MEXICANA', 'role': 'palabra', 'x': 20, 'y': 20, 'w': 800, 'h': 400},
        ]}, 1000, 600)
        self.assertTrue(united['titleFailed'])
        self.assertNotIn('x', united)

    def test_defecto_alto_impide_el_registro_automatico(self):
        self.assertFalse(listo_para_registrar(True, [{'severity': 'Alta', 'title': 'Falta TIERRA'}]))
        self.assertTrue(listo_para_registrar(True, [{'severity': 'Baja'}]))
        self.assertFalse(listo_para_registrar(False, []))

    def test_los_png_no_salen_de_assets(self):
        manifest = asset_path('/assets/manifest.json')
        self.assertTrue(str(manifest).endswith('/assets/manifest.json'))
        self.assertIsNone(asset_path('/assets/../../server.py'))


if __name__ == '__main__':
    unittest.main()
