"""La lámina asigna un archivo por objeto, sin llamar al modelo."""
import unittest

from PIL import Image
import numpy as np

from studio.desarmar.catalogo import aplicar_lamina, borrar_cifras, preparar_catalogo, vaciar_hueco


def _pieza(**kwargs):
    base = {'x': 0, 'y': 0, 'w': 40, 'h': 40, 'confidence': 1}
    base.update(kwargs)
    return base


class CatalogoTest(unittest.TestCase):
    def test_nombra_la_lamina_y_quita_la_cifra_de_la_placa(self):
        comps = [
            _pieza(id='titulo', name='Letrero TIERRA MEXICANA', type='Título / logo', x=100, y=0, w=400, h=120, titleWords=['TIERRA', 'MEXICANA']),
            _pieza(id='logo_dragon', name='Dragón de fuego', type='Título / logo', x=100, y=140, w=200, h=80),
            _pieza(id='oro', name='Oro', type='Jackpot', x=500, y=20, w=140, h=70),
            _pieza(id='jackpot_grand', name='Jackpot GRAND', type='Jackpot', x=10, y=20, w=220, h=90, _parts=[
                {'text': '$100,000.00', 'role': 'cifra', 'x': 40, 'y': 60, 'w': 140, 'h': 28},
            ]),
            _pieza(id='monto', name='$10,000.00', type='Otro', x=280, y=70, w=120, h=24),
            _pieza(id='jackpot_major', name='Jackpot MAJOR', type='Jackpot', x=250, y=20, w=200, h=90),
            _pieza(id='marco', name='Marco de rodillos', type='Marco de rodillos', x=80, y=160, w=500, h=360, _hole={'x': 120, 'y': 200, 'w': 420, 'h': 280}),
            _pieza(id='charro', name='Charro', type='Símbolo', x=140, y=220, w=70, h=70),
            _pieza(id='charro_2', name='Charro', type='Símbolo', x=220, y=220, w=70, h=70),
            _pieza(id='boton_menos', name='Botón menos', type='Botón', x=700, y=40, w=40, h=40),
            _pieza(id='boton_mas', name='Botón más', type='Botón', x=760, y=40, w=40, h=40),
            _pieza(id='girar', name='Girar', type='Botón', x=700, y=100, w=90, h=90),
            _pieza(id='apuesta', name='Apuesta', type='Panel', x=20, y=500, w=120, h=50),
            _pieza(id='izq', name='20 LINEAS', type='Contador', x=20, y=560, w=70, h=40),
            _pieza(id='der', name='20 LINEAS', type='Contador', x=640, y=560, w=70, h=40),
            _pieza(id='fondo', name='Fondo principal', type='Fondo', x=0, y=0, w=800, h=600),
        ]
        quedaron, notes = preparar_catalogo(comps, 800, 600)
        nombres = [comp['fileName'] for comp in quedaron]
        self.assertIn('titulo_tierra_mexicana', nombres)
        self.assertIn('titulo_dragon_de_fuego', nombres)
        self.assertIn('jackpot_oro', nombres)
        self.assertIn('jackpot_grand', nombres)
        self.assertIn('jackpot_major', nombres)
        self.assertIn('marco_rodillos', nombres)
        self.assertIn('simbolo_charro', nombres)
        self.assertIn('simbolo_charro_2', nombres)
        self.assertIn('boton_menos', nombres)
        self.assertIn('boton_mas', nombres)
        self.assertIn('boton_girar', nombres)
        self.assertIn('panel_apuesta', nombres)
        self.assertIn('indicador_lineas_izq', nombres)
        self.assertIn('indicador_lineas_der', nombres)
        self.assertIn('fondo_principal', nombres)
        self.assertNotIn('monto', [comp['id'] for comp in quedaron])
        grand = next(comp for comp in quedaron if comp['fileName'] == 'jackpot_grand')
        self.assertEqual(len(grand['erase']), 1)
        self.assertEqual(grand['erase'][0]['x'], 40)
        major = next(comp for comp in quedaron if comp['fileName'] == 'jackpot_major')
        self.assertTrue(any(box['x'] == 280 for box in major['erase']))
        marco = next(comp for comp in quedaron if comp['fileName'] == 'marco_rodillos')
        self.assertEqual(marco['hole']['w'], 420)
        self.assertFalse(marco['holeEstimated'])
        self.assertTrue(any('cifra' in note for note in notes))

    def test_no_exporta_pedazos_del_fondo(self):
        comps = [
            _pieza(id='fondo', name='Fondo principal', type='Fondo', x=0, y=0, w=800, h=600),
            _pieza(id='cielo', name='Cielo', type='Fondo', x=0, y=0, w=800, h=180),
            _pieza(id='luna', name='Luna del paisaje', type='Decoración', x=40, y=20, w=60, h=60),
            _pieza(id='ciudad', name='Ciudad', type='Otro', x=0, y=200, w=400, h=200),
            _pieza(id='chispas', name='Chispas doradas', type='Efecto', x=10, y=10, w=30, h=30),
            _pieza(id='nube', name='Nube', type='Símbolo', x=200, y=220, w=70, h=70),
            _pieza(id='aguila', name='Águila del cielo', type='Símbolo', x=30, y=30, w=80, h=50),
            _pieza(id='bonus', name='Bonus', type='Bonus', x=300, y=300, w=70, h=70),
            _pieza(id='charro', name='Charro', type='Símbolo', x=140, y=220, w=70, h=70),
            _pieza(id='nave', name='Nave espacial', type='Símbolo', x=400, y=240, w=70, h=70),
            _pieza(id='estrella', name='Estrella', type='Símbolo', x=480, y=240, w=70, h=70),
            _pieza(id='boton', name='Girar', type='Botón', x=700, y=500, w=80, h=80),
            _pieza(id='grand', name='GRAND', type='Jackpot', x=10, y=20, w=180, h=70),
            _pieza(id='titulo', name='Titulo', type='Título / logo', x=250, y=0, w=300, h=80, titleWords=['TIERRA']),
            _pieza(id='marco', name='Marco de rodillos', type='Marco de rodillos', x=80, y=160, w=500, h=360),
            _pieza(id='apuesta', name='Apuesta', type='Panel', x=20, y=530, w=120, h=40),
            _pieza(id='lineas', name='20 LINEAS', type='Contador', x=620, y=540, w=80, h=30),
            _pieza(id='giros', name='Contador de giros', type='Contador', x=400, y=540, w=80, h=30),
        ]
        quedaron, notes = preparar_catalogo(comps, 800, 600)
        nombres = [comp['fileName'] for comp in quedaron]
        ids = [comp['id'] for comp in quedaron]
        self.assertEqual([nombre for nombre in nombres if nombre.startswith('fondo')], ['fondo_principal'])
        for ident in ('cielo', 'luna', 'ciudad', 'chispas', 'nube', 'aguila', 'giros'):
            self.assertNotIn(ident, ids)
        for nombre in (
            'titulo_tierra',
            'jackpot_grand',
            'marco_rodillos',
            'simbolo_charro',
            'simbolo_nave_espacial',
            'simbolo_estrella',
            'simbolo_bonus',
            'boton_girar',
            'panel_apuesta',
            'indicador_lineas_izq',
        ):
            self.assertIn(nombre, nombres)
        self.assertTrue(any('pedazos del fondo' in note for note in notes))

    def test_estima_el_centro_del_marco_cuando_no_viene_la_ventana(self):
        comps = [_pieza(id='marco', name='Marco de rodillos', type='Marco de rodillos', x=0, y=0, w=200, h=100)]
        quedaron, notes = preparar_catalogo(comps, 200, 100)
        hole = quedaron[0]['hole']
        self.assertGreater(hole['x'], 0)
        self.assertGreater(hole['y'], 0)
        self.assertLess(hole['x'] + hole['w'], 200)
        self.assertTrue(quedaron[0]['holeEstimated'])
        self.assertTrue(notes)

    def test_vacia_el_centro_y_conserva_el_marco(self):
        image = Image.new('RGBA', (100, 80), (220, 170, 40, 255))
        vacio = vaciar_hueco(image, {'x': 20, 'y': 16, 'w': 60, 'h': 48})
        arr = np.array(vacio)
        self.assertLess(int(arr[40, 50, 3]), 10)
        self.assertGreater(int(arr[2, 2, 3]), 200)
        self.assertGreater(int(arr[2, 2, 0]), 180)

    def test_vacia_el_monto_del_jackpot_y_conserva_la_palabra(self):
        imagen = Image.new('RGBA', (220, 110), (150, 24, 32, 255))
        draw = imagen.load()
        for index in range(5):
            x0 = 28 + index * 34
            for y in range(16, 40):
                for x in range(x0, x0 + 18):
                    draw[x, y] = (245, 220, 120, 255)
        for index in range(8):
            x0 = 24 + index * 22
            for y in range(62, 92):
                for x in range(x0, x0 + 12):
                    draw[x, y] = (245, 220, 120, 255)
        limpio = np.array(aplicar_lamina(imagen, kind='Jackpot'))
        self.assertGreater(int(limpio[28, 36, 0]), 200)
        self.assertGreater(int(limpio[28, 36, 1]), 160)
        self.assertGreater(int(limpio[76, 30, 0]), 120)
        self.assertLess(int(limpio[76, 30, 1]), 90)
        self.assertEqual(int(limpio[76, 30, 3]), 255)

    def test_los_jackpot_del_juego_quedan_sin_monto(self):
        for nombre, palabra, monto in (
            ('assets/ui/jackpot-grand.png', (15, 42, 70, 200), (55, 95, 20, 240)),
            ('assets/ui/jackpot-major.png', (15, 42, 70, 200), (55, 95, 20, 230)),
            ('assets/ui/jackpot-minor.png', (6, 32, 60, 190), (42, 78, 20, 220)),
        ):
            imagen = Image.open(nombre).convert('RGBA')
            salida = np.array(aplicar_lamina(imagen, kind='Jackpot').convert('RGB'))
            self.assertGreater(self._oro(salida, palabra), 200)
            self.assertLess(self._oro(salida, monto), 30)

    @staticmethod
    def _oro(arr, band):
        y0, y1, x0, x1 = band
        zona = arr[y0:y1, x0:x1]
        return int(((zona[:, :, 0] > 170) & (zona[:, :, 1] > 120) & (zona[:, :, 0] > zona[:, :, 2] + 40)).sum())

    def test_borra_la_cifra_y_deja_el_color_de_la_placa(self):
        arr = np.zeros((40, 80, 4), np.uint8)
        arr[:, :] = (180, 20, 30, 255)
        arr[14:26, 30:54] = (245, 245, 245, 255)
        limpio = borrar_cifras(Image.fromarray(arr, 'RGBA'), [{'x': 30, 'y': 14, 'w': 24, 'h': 12}])
        centro = np.array(limpio)[20, 40]
        self.assertGreater(int(centro[0]), 140)
        self.assertLess(int(centro[1]), 80)
        self.assertEqual(int(centro[3]), 255)

    def test_el_marco_recortado_queda_con_el_centro_vacio(self):
        image = Image.new('RGBA', (100, 80), (220, 170, 40, 255))
        salida = aplicar_lamina(image, kind='Marco de rodillos')
        arr = np.array(salida)
        self.assertLess(int(arr[40, 50, 3]), 10)
        self.assertGreater(int(arr[1, 1, 3]), 200)


if __name__ == '__main__':
    unittest.main()
