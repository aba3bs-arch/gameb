"""Pruebas del recorte de PNG del desarmador, sin modelo remoto."""
import base64
import io
import unittest
from PIL import Image, ImageDraw
import numpy as np

from studio.desarmar.catalogo import aplicar_lamina
from studio.desarmar.fondo import clean_background
from studio.desarmar.recortar import (
    _clase_de_pieza,
    _drawing_disappeared,
    _recortar_desde_el_borde,
    _restore_title_letters,
    _should_restore,
    quitar_fondo,
    refine_cutout,
)


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

    def test_quita_el_halo_opaco_del_color_del_fondo(self):
        w, h = 180, 140
        src = np.zeros((h, w, 4), np.uint8)
        src[:, :] = (20, 90, 210, 255)
        yy, xx = np.ogrid[:h, :w]
        red = (xx - 90) ** 2 + (yy - 70) ** 2 <= 32 ** 2
        src[red] = (220, 30, 40, 255)
        source = Image.fromarray(src, 'RGBA')
        cut = np.zeros((h, w, 4), np.uint8)
        blue_ring = ((xx - 90) ** 2 + (yy - 70) ** 2 <= 46 ** 2) & ~red
        cut[red] = (220, 30, 40, 255)
        cut[blue_ring] = (20, 90, 210, 255)
        refined, _info = refine_cutout(source, Image.fromarray(cut, 'RGBA'), {'x': 40, 'y': 20, 'w': 100, 'h': 100})
        arr = np.array(refined)
        blue = (arr[:, :, 2] > 150) & (arr[:, :, 0] < 80) & (arr[:, :, 3] > 16)
        self.assertLess(int(blue.sum()), 15)
        cy, cx = arr.shape[0] // 2, arr.shape[1] // 2
        self.assertGreater(int(arr[cy, cx, 0]), 180)
        self.assertGreater(int(arr[cy, cx, 3]), 240)

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

    def test_recupera_el_panel_cuando_la_mascara_es_una_mancha(self):
        source = Image.new('RGBA', (240, 120), (20, 40, 120, 255))
        px = source.load()
        for y in range(30, 90):
            for x in range(40, 200):
                px[x, y] = (230, 160, 30, 255)
        cut = np.zeros((120, 240, 4), np.uint8)
        cut[55:62, 70:78] = (230, 160, 30, 255)
        restored = _restore_title_letters(source, Image.fromarray(cut, 'RGBA'), (30, 20, 180, 80))
        arr = np.array(restored)
        self.assertGreater(int(np.count_nonzero(arr[30:90, 40:200, 3] > 200)), 8000)

    def test_una_mancha_no_cuenta_como_pieza(self):
        self.assertTrue(_should_restore('Jackpot', 0.05, 0.01))
        self.assertTrue(_should_restore('Título / logo', 0.4, 0.35))
        self.assertFalse(_should_restore('Símbolo', 0.9, 0.5))
        self.assertTrue(_drawing_disappeared(0.01, (0, 0, 280, 120)))
        self.assertFalse(_drawing_disappeared(0.4, (0, 0, 280, 120)))


def _placa_con_margen(margen=16, tocar_arriba=False):
    """Placa roja, palabra arriba y monto abajo, sobre un paisaje azul."""
    ancho, alto = 220 + margen * 2, 110 + margen * 2
    imagen = Image.new('RGBA', (ancho, alto), (30, 90, 200, 255))
    pixel = imagen.load()
    y0 = 0 if tocar_arriba else margen
    for y in range(y0, y0 + 110):
        for x in range(margen, margen + 220):
            pixel[x, y] = (150, 24, 32, 255)
    for index in range(5):
        x0 = margen + 28 + index * 34
        for y in range(y0 + 16, y0 + 40):
            for x in range(x0, x0 + 18):
                pixel[x, y] = (245, 220, 120, 255)
    for index in range(8):
        x0 = margen + 24 + index * 22
        for y in range(y0 + 62, y0 + 92):
            for x in range(x0, x0 + 12):
                pixel[x, y] = (245, 220, 120, 255)
    return imagen


class RecortePorTipoTest(unittest.TestCase):
    def test_cada_tipo_elige_su_corte(self):
        self.assertEqual(_clase_de_pieza('Fondo fondo_principal'), 'fondo')
        self.assertEqual(_clase_de_pieza('Marco de rodillos marco_rodillos'), 'marco')
        self.assertEqual(_clase_de_pieza('Jackpot jackpot_grand'), 'placa')
        self.assertEqual(_clase_de_pieza('Panel panel_apuesta'), 'placa')
        self.assertEqual(_clase_de_pieza('Símbolo simbolo_charro'), 'silueta')
        self.assertEqual(_clase_de_pieza('Título titulo_dragon'), 'silueta')

    def test_la_placa_suelta_el_margen_y_vacia_el_monto(self):
        imagen = _placa_con_margen()
        recorte, info = _recortar_desde_el_borde(imagen, 'placa')
        self.assertEqual(info['engine'], 'borde-placa')
        arr = np.array(recorte)
        self.assertLess(int(arr[0, 0, 3]), 16)
        self.assertEqual(int(arr[arr.shape[0] // 2, arr.shape[1] // 2, 3]), 255)
        salida = np.array(aplicar_lamina(recorte, kind='Jackpot jackpot_grand'))
        arriba = salida[:salida.shape[0] // 2]
        abajo = salida[salida.shape[0] // 2:]
        self.assertGreater(int(((arriba[:, :, 0] > 200) & (arriba[:, :, 1] > 160)).sum()), 1000)
        self.assertEqual(int(((abajo[:, :, 0] > 200) & (abajo[:, :, 1] > 160)).sum()), 0)
        self.assertGreater(int(((abajo[:, :, 0] > 120) & (abajo[:, :, 1] < 90) & (abajo[:, :, 3] == 255)).sum()), 400)

    def test_una_placa_sin_margen_sigue_opaca_y_sin_monto(self):
        imagen = _placa_con_margen(margen=0)
        recorte, info = _recortar_desde_el_borde(imagen, 'placa')
        arr = np.array(recorte)
        self.assertEqual(float((arr[:, :, 3] < 16).mean()), 0.0)
        self.assertEqual(int(arr[0, 0, 3]), 255)
        salida = np.array(aplicar_lamina(recorte, kind='Jackpot'))
        self.assertEqual(int(((salida[60:, :, 0] > 200) & (salida[60:, :, 1] > 160)).sum()), 0)
        self.assertGreater(int(((salida[:40, :, 0] > 200) & (salida[:40, :, 1] > 160)).sum()), 1000)

    def test_un_adorno_que_toca_el_borde_no_abre_la_placa(self):
        imagen = _placa_con_margen(tocar_arriba=True)
        recorte, info = _recortar_desde_el_borde(imagen, 'placa')
        arr = np.array(recorte)
        self.assertLess(int(arr[0, -1, 3]), 16)
        self.assertEqual(int(arr[arr.shape[0] // 2, arr.shape[1] // 2, 3]), 255)
        self.assertGreater(float((arr[:, :, 3] > 200).mean()), 0.7)

    def test_el_marco_suelta_el_paisaje_y_vacia_la_ventana(self):
        ancho, alto = 160, 120
        imagen = Image.new('RGBA', (ancho, alto), (30, 90, 200, 255))
        pixel = imagen.load()
        for y in range(10, alto - 10):
            for x in range(10, ancho - 10):
                pixel[x, y] = (210, 160, 40, 255)
        for y in range(28, alto - 28):
            for x in range(28, ancho - 28):
                pixel[x, y] = (20, 140, 40, 255)
        recorte, info = _recortar_desde_el_borde(imagen, 'marco')
        self.assertEqual(info['engine'], 'borde-marco')
        salida = np.array(aplicar_lamina(recorte, info['trimX'], info['trimY'], kind='Marco de rodillos marco_rodillos'))
        self.assertLess(int(salida[0, 0, 3]), 16)
        self.assertGreater(int(salida[4, salida.shape[1] // 2, 3]), 200)
        self.assertLess(int(salida[salida.shape[0] // 2, salida.shape[1] // 2, 3]), 16)

    def test_el_panel_conserva_los_botones_si_nadie_marco_la_cifra(self):
        imagen = Image.new('RGBA', (180, 70), (40, 18, 16, 255))
        pixel = imagen.load()
        for index, x0 in enumerate((16, 78, 140)):
            for y in range(22, 48):
                for x in range(x0, x0 + 16):
                    pixel[x, y] = (245, 220, 120, 255)
        intacto = np.array(aplicar_lamina(imagen, kind='Panel panel_apuesta'))
        self.assertGreater(int(((intacto[:, :, 0] > 200) & (intacto[:, :, 1] > 160)).sum()), 900)
        vacio = np.array(aplicar_lamina(imagen, erase=[{'x': 78, 'y': 22, 'w': 16, 'h': 26}], kind='Panel panel_apuesta'))
        self.assertLess(int(vacio[34, 86, 1]), 80)
        self.assertGreater(int(vacio[34, 24, 1]), 160)

    def test_el_fondo_no_pasa_por_el_recorte_de_silueta(self):
        imagen = Image.new('RGBA', (24, 16), (12, 40, 90, 255))
        buf = io.BytesIO()
        imagen.save(buf, format='PNG')
        data = 'data:image/png;base64,' + base64.b64encode(buf.getvalue()).decode('ascii')
        status, body = quitar_fondo({'image': data, 'kind': 'Fondo fondo_principal'})
        self.assertEqual(status, 200)
        self.assertEqual(body['engine'], 'fondo')
        self.assertEqual(body['width'], 24)
        status, body = quitar_fondo({'image': data, 'kind': 'Jackpot jackpot_grand'})
        self.assertEqual(status, 200)
        self.assertEqual(body['engine'], 'borde-placa')


if __name__ == '__main__':
    unittest.main()
