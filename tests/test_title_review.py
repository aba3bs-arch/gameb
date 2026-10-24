"""La revisión de títulos no llama al modelo: solo acepta o rechaza la caja."""
import unittest
from PIL import Image
import numpy as np

from studio.desarmar.inspeccionar import listo_para_registrar
from studio.desarmar.leer import _escala_del_boceto, _escalar_caja
from studio.desarmar.recortar import _restore_title_letters
from studio.desarmar.unir import apply_title_review, unir_titulo
from studio.http import asset_path


def _medir(comps, width, height):
    import copy
    comps = copy.deepcopy(comps)
    sx, sy = _escala_del_boceto(comps, width, height)
    for comp in comps:
        _escalar_caja(comp, sx, sy)
    return comps, sx, sy


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

    def test_un_logo_sin_palabras_usa_su_caja(self):
        united = unir_titulo({'x': 400, 'y': 0, 'w': 180, 'h': 70, 'parts': []}, 1000, 600)
        self.assertFalse(united['titleFailed'])
        self.assertFalse(united['skipSave'])
        self.assertEqual(united['titleWords'], [])
        self.assertEqual((united['x'], united['y'], united['w'], united['h']), (400, 0, 180, 70))

    def test_un_dibujo_sin_palabras_une_sus_partes(self):
        united = unir_titulo({'x': 10, 'y': 10, 'w': 400, 'h': 200, 'parts': [
            {'text': 'escudo', 'role': 'imagen', 'x': 80, 'y': 12, 'w': 140, 'h': 90},
            {'text': 'corona', 'role': 'adorno', 'x': 110, 'y': 2, 'w': 70, 'h': 28},
        ]}, 1000, 600)
        self.assertFalse(united['titleFailed'])
        self.assertEqual(united['titleWords'], [])
        self.assertEqual((united['x'], united['y'], united['w'], united['h']), (80, 2, 140, 100))

    def test_un_logo_sin_caja_usable_no_se_registra(self):
        united = unir_titulo({'x': 0, 'y': 0, 'w': 900, 'h': 560, 'parts': []}, 1000, 600)
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


class EscalaDelBocetoTest(unittest.TestCase):
    def test_las_milesimas_pasan_al_tamano_real(self):
        comps = [
            {'id': 'fondo', 'x': 0, 'y': 0, 'w': 1000, 'h': 1000},
            {'id': 'minor', 'x': 100, 'y': 80, 'w': 220, 'h': 90},
            {'id': 'grand', 'x': 400, 'y': 40, 'w': 280, 'h': 120},
            {'id': 'charro', 'x': 300, 'y': 400, 'w': 80, 'h': 80, 'parts': [
                {'text': 'A', 'role': 'adorno', 'x': 300, 'y': 400, 'w': 80, 'h': 80},
            ]},
            {'id': 'marco', 'x': 200, 'y': 200, 'w': 600, 'h': 500, 'hole': {'x': 240, 'y': 240, 'w': 520, 'h': 420}},
        ]
        salida, sx, sy = _medir(comps, 1920, 1080)
        self.assertAlmostEqual(sx, 1.92)
        self.assertAlmostEqual(sy, 1.08)
        minor = next(comp for comp in salida if comp['id'] == 'minor')
        grand = next(comp for comp in salida if comp['id'] == 'grand')
        fondo = next(comp for comp in salida if comp['id'] == 'fondo')
        marco = next(comp for comp in salida if comp['id'] == 'marco')
        charro = next(comp for comp in salida if comp['id'] == 'charro')
        self.assertEqual(minor['x'], round(100 * 1.92))
        self.assertEqual(minor['w'], round(220 * 1.92))
        self.assertEqual(minor['h'], round(90 * 1.08))
        self.assertEqual(grand['w'], round(280 * 1.92))
        self.assertEqual(fondo['w'], 1920)
        self.assertEqual(fondo['h'], 1080)
        self.assertEqual(marco['hole']['w'], round(520 * 1.92))
        self.assertEqual(charro['parts'][0]['x'], round(300 * 1.92))

    def test_los_pixeles_correctos_no_se_mueven(self):
        comps = [
            {'x': 0, 'y': 0, 'w': 1920, 'h': 1080},
            {'x': 1400, 'y': 80, 'w': 400, 'h': 160},
        ]
        salida, sx, sy = _medir(comps, 1920, 1080)
        self.assertEqual(sx, 1)
        self.assertEqual(sy, 1)
        self.assertEqual(salida[1]['x'], 1400)
        self.assertEqual(salida[1]['w'], 400)

    def test_un_boceto_chico_en_pixeles_no_se_encoge(self):
        comps = [
            {'x': 0, 'y': 0, 'w': 800, 'h': 600},
            {'x': 40, 'y': 20, 'w': 180, 'h': 70},
        ]
        salida, sx, sy = _medir(comps, 800, 600)
        self.assertEqual(sx, 1)
        self.assertEqual(sy, 1)
        self.assertEqual(salida[1]['w'], 180)

    def test_las_milesimas_tambien_entran_en_un_boceto_chico(self):
        comps = [
            {'x': 0, 'y': 0, 'w': 1000, 'h': 1000},
            {'x': 100, 'y': 50, 'w': 200, 'h': 80},
        ]
        salida, sx, sy = _medir(comps, 800, 600)
        self.assertAlmostEqual(sx, 0.8)
        self.assertAlmostEqual(sy, 0.6)
        self.assertEqual(salida[1]['x'], 80)
        self.assertEqual(salida[1]['h'], 48)

    def test_una_foto_mas_chica_se_estira_en_todas_las_piezas(self):
        comps = [
            {'x': 0, 'y': 0, 'w': 1366, 'h': 768},
            {'x': 80, 'y': 40, 'w': 200, 'h': 70},
            {'x': 400, 'y': 500, 'w': 90, 'h': 90},
        ]
        salida, sx, sy = _medir(comps, 1920, 1080)
        self.assertAlmostEqual(sx, 1920 / 1366)
        self.assertAlmostEqual(sy, 1080 / 768)
        self.assertEqual(salida[1]['w'], round(200 * sx))
        self.assertEqual(salida[2]['x'], round(400 * sx))
        self.assertEqual(salida[0]['w'], 1920)
        self.assertEqual(salida[0]['h'], 1080)

    def test_de_cero_a_uno_cubre_el_archivo_entero(self):
        comps = [
            {'x': 0, 'y': 0, 'w': 1, 'h': 1},
            {'x': 0.25, 'y': 0.1, 'w': 0.2, 'h': 0.15},
        ]
        salida, _sx, _sy = _medir(comps, 1600, 900)
        self.assertEqual(salida[1]['x'], 400)
        self.assertEqual(salida[1]['y'], 90)
        self.assertEqual(salida[1]['w'], 320)
        self.assertEqual(salida[1]['h'], 135)


if __name__ == '__main__':
    unittest.main()
