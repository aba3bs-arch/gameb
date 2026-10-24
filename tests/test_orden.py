"""El orden de las imágenes, sin llamar a ChatGPT."""
import unittest

from studio.orden import PASOS, _instruccion, preparar


class OrdenTest(unittest.TestCase):
    def test_el_orden_empieza_por_el_fondo(self):
        self.assertTrue(PASOS[0].startswith('Primero'))
        self.assertIn('título', PASOS[1])
        self.assertIn('Al final', PASOS[-1])
        texto = _instruccion(1920, 1080)
        self.assertIn('Primero: el fondo', texto)
        self.assertIn('1920', texto)

    def test_las_piezas_salen_en_el_orden_fijo(self):
        piezas = [
            {'name': 'girar', 'type': 'Botón', 'x': 10, 'y': 10, 'w': 40, 'h': 40},
            {'name': 'logo', 'type': 'Título', 'x': 100, 'y': 8, 'w': 80, 'h': 30},
            {'name': 'minor', 'type': 'Jackpot', 'x': 20, 'y': 40, 'w': 50, 'h': 24},
            {'name': 'fondo', 'type': 'Fondo', 'x': 0, 'y': 0, 'w': 400, 'h': 300},
            {'name': 'nube', 'type': 'Símbolo', 'x': 1, 'y': 1, 'w': 20, 'h': 20},
            {'name': 'icono b', 'type': 'Símbolo', 'x': 80, 'y': 90, 'w': 30, 'h': 30},
            {'name': 'icono a', 'type': 'Símbolo', 'x': 40, 'y': 90, 'w': 30, 'h': 30},
            {'name': 'marco', 'type': 'Marco', 'x': 30, 'y': 70, 'w': 120, 'h': 80},
            {'name': 'lineas', 'type': 'Letrero', 'x': 5, 'y': 200, 'w': 30, 'h': 40},
        ]
        orden = [pieza['name'] for pieza in preparar(piezas, 400, 300)]
        self.assertEqual(orden, ['fondo', 'logo', 'minor', 'marco', 'icono a', 'icono b', 'girar', 'lineas'])

    def test_las_milesimas_se_miden_en_pixeles(self):
        piezas = [
            {'name': 'fondo', 'type': 'Fondo', 'x': 0, 'y': 0, 'w': 1000, 'h': 1000},
            {'name': 'logo', 'type': 'Título', 'x': 280, 'y': 20, 'w': 440, 'h': 130},
        ]
        lista = preparar(piezas, 1920, 1080)
        logo = next(pieza for pieza in lista if pieza['name'] == 'logo')
        self.assertGreater(logo['x'], 400)
        self.assertLess(logo['w'], 1000)

    def test_los_pixeles_correctos_no_se_mueven(self):
        piezas = [
            {'name': 'fondo', 'type': 'Fondo', 'x': 0, 'y': 0, 'w': 1920, 'h': 1080},
            {'name': 'logo', 'type': 'Título', 'x': 1400, 'y': 80, 'w': 400, 'h': 160},
        ]
        lista = preparar(piezas, 1920, 1080)
        logo = next(pieza for pieza in lista if pieza['name'] == 'logo')
        self.assertEqual(logo['x'], 1400)
        self.assertEqual(logo['w'], 400)
