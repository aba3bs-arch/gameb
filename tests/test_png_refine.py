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
    _cuadrado_de_simbolo,
    _drawing_disappeared,
    _label_components,
    _recortar_desde_el_borde,
    _recortar_silueta,
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

    def test_la_placa_llega_al_adorno_y_no_se_trae_la_vecina(self):
        imagen = Image.new('RGBA', (260, 130), (30, 90, 200, 255))
        pixel = imagen.load()
        for y in range(48, 88):
            for x in range(12, 28):
                pixel[x, y] = (245, 200, 40, 255)
        for y in range(12, 118):
            for x in range(28, 200):
                pixel[x, y] = (150, 24, 32, 255)
        for y in range(40, 90):
            for x in range(210, 248):
                pixel[x, y] = (20, 140, 40, 255)
        recorte, info = _recortar_desde_el_borde(imagen, 'placa', {'x': 36, 'y': 20, 'w': 150, 'h': 90})
        self.assertEqual(info['engine'], 'borde-placa')
        arr = np.array(recorte)
        oro = (arr[:, :, 0] > 200) & (arr[:, :, 1] > 160) & (arr[:, :, 3] > 200)
        verde = (arr[:, :, 1] > 100) & (arr[:, :, 0] < 80) & (arr[:, :, 3] > 200)
        rojo = (arr[:, :, 0] > 120) & (arr[:, :, 1] < 60) & (arr[:, :, 3] > 200)
        self.assertGreater(int(oro.sum()), 200)
        self.assertEqual(int(verde.sum()), 0)
        self.assertGreater(int(rojo.sum()), 2000)

    def test_la_placa_no_se_queda_con_chispas_sueltas(self):
        imagen = _placa_con_margen()
        pixel = imagen.load()
        for y in range(6, 16):
            for x in range(6, 16):
                pixel[x, y] = (245, 220, 80, 255)
        recorte, info = _recortar_desde_el_borde(imagen, 'placa')
        arr = np.array(recorte)
        _labels, count = _label_components(arr[:, :, 3] >= 16)
        self.assertEqual(count, 1)
        self.assertEqual(info['engine'], 'borde-placa')
        self.assertGreater(int(((arr[:, :, 0] > 200) & (arr[:, :, 1] > 160) & (arr[:, :, 3] > 200)).sum()), 1000)

    def test_el_titulo_conserva_cada_letra_y_suelta_el_cielo(self):
        imagen = Image.new('RGBA', (180, 80), (20, 70, 160, 255))
        pixel = imagen.load()
        for index in range(4):
            x0 = 24 + index * 36
            for y in range(22, 54):
                for x in range(x0, x0 + 16):
                    pixel[x, y] = (240, 190, 40, 255)
        recorte, info = _recortar_silueta(imagen, {'x': 8, 'y': 8, 'w': 164, 'h': 64})
        self.assertTrue(info.get('usable'))
        self.assertEqual(info['engine'], 'contraste')
        arr = np.array(recorte)
        cielo = (arr[:, :, 2] > 120) & (arr[:, :, 0] < 80) & (arr[:, :, 3] > 16)
        self.assertEqual(int(cielo.sum()), 0)
        self.assertGreater(float((arr[:, :, 3] < 16).mean()), 0.05)
        letras = (arr[:, :, 0] > 200) & (arr[:, :, 1] > 150) & (arr[:, :, 3] > 200)
        _labels, count = _label_components(letras)
        self.assertGreaterEqual(count, 4)
        self.assertGreater(int(letras.sum()), 1500)

    def test_el_adorno_que_se_sale_de_la_caja_se_queda(self):
        imagen = Image.new('RGBA', (160, 100), (20, 70, 160, 255))
        pixel = imagen.load()
        for y in range(28, 56):
            for x in range(40, 110):
                pixel[x, y] = (240, 190, 40, 255)
        for y in range(56, 88):
            for x in range(62, 84):
                pixel[x, y] = (30, 160, 70, 255)
        for y in range(2, 8):
            for x in range(2, 8):
                pixel[x, y] = (240, 210, 40, 255)
        recorte, info = _recortar_silueta(imagen, {'x': 24, 'y': 16, 'w': 110, 'h': 46})
        self.assertTrue(info.get('usable'))
        arr = np.array(recorte)
        verde = (arr[:, :, 1] > 120) & (arr[:, :, 0] < 80) & (arr[:, :, 3] > 200)
        self.assertGreater(int(verde.sum()), 200)
        self.assertGreater(int(((arr[:, :, 0] > 200) & (arr[:, :, 1] > 150) & (arr[:, :, 3] > 200)).sum()), 800)

    def _png(self, image):
        buf = io.BytesIO()
        image.save(buf, format='PNG')
        return 'data:image/png;base64,' + base64.b64encode(buf.getvalue()).decode('ascii')

    def test_un_simbolo_cuadrado_conserva_el_marco_y_el_dibujo(self):
        imagen = Image.new('RGBA', (160, 160), (20, 60, 140, 255))
        pixel = imagen.load()
        for y in range(30, 130):
            for x in range(30, 130):
                pixel[x, y] = (180, 90, 30, 255)
        for y in range(30, 130):
            for x in range(30, 130):
                if x < 38 or x >= 122 or y < 38 or y >= 122:
                    pixel[x, y] = (230, 180, 40, 255)
        for y in range(70, 90):
            for x in range(70, 90):
                pixel[x, y] = (220, 30, 40, 255)
        for y in range(4, 16):
            for x in range(4, 16):
                pixel[x, y] = (20, 160, 40, 255)
        caja = {'x': 18, 'y': 18, 'w': 124, 'h': 124}
        self.assertIsNotNone(_cuadrado_de_simbolo(np.array(imagen.convert('RGB')), caja))
        status, body = quitar_fondo({'image': self._png(imagen), 'kind': 'Símbolo simbolo_charro', 'inner': caja})
        self.assertEqual(status, 200)
        self.assertEqual(body['engine'], 'cuadrado')
        arr = np.array(Image.open(io.BytesIO(base64.b64decode(body['image'].split(',', 1)[1]))).convert('RGBA'))
        self.assertGreater(int(arr[arr.shape[0] // 2, arr.shape[1] // 2, 0]), 180)
        self.assertEqual(int(arr[arr.shape[0] // 2, arr.shape[1] // 2, 3]), 255)
        oro = (arr[:, :, 0] > 200) & (arr[:, :, 1] > 150) & (arr[:, :, 2] < 80) & (arr[:, :, 3] > 200)
        self.assertGreater(int(oro.sum()), 400)
        verde = (arr[:, :, 1] > 120) & (arr[:, :, 0] < 80) & (arr[:, :, 3] > 16)
        self.assertEqual(int(verde.sum()), 0)
        self.assertLess(abs(arr.shape[0] - arr.shape[1]), 8)

    def test_el_cuadrado_no_incluye_el_paisaje_de_alrededor(self):
        ruido = np.zeros((180, 180, 3), np.uint8)
        for y in range(180):
            tono = 20 + (y * 3) % 50
            ruido[y, :, 0] = tono
            ruido[y, :, 1] = 30 + (y % 17)
            ruido[y, :, 2] = 90 + (y % 29)
        ruido[40:140, 40:140] = (180, 90, 30)
        ruido[40:48, 40:140] = (230, 180, 40)
        ruido[132:140, 40:140] = (230, 180, 40)
        ruido[40:140, 40:48] = (230, 180, 40)
        ruido[40:140, 132:140] = (230, 180, 40)
        imagen = Image.fromarray(np.dstack([ruido, np.full((180, 180), 255, np.uint8)]), 'RGBA')
        caja = {'x': 22, 'y': 22, 'w': 136, 'h': 136}
        rect = _cuadrado_de_simbolo(np.array(imagen.convert('RGB')), caja)
        self.assertIsNotNone(rect)
        self.assertGreaterEqual(rect['x'], 36)
        self.assertLessEqual(rect['x'], 44)
        self.assertGreaterEqual(rect['w'], 96)
        self.assertLessEqual(rect['w'], 104)
        status, body = quitar_fondo({'image': self._png(imagen), 'kind': 'Símbolo simbolo_pieza', 'inner': caja})
        self.assertEqual(status, 200)
        self.assertEqual(body['engine'], 'cuadrado')
        self.assertLess(body['width'], 120)
        self.assertLess(body['height'], 120)

    def test_una_figura_redonda_no_se_trata_como_cuadrado(self):
        imagen = Image.new('RGBA', (140, 140), (20, 60, 140, 255))
        pixel = imagen.load()
        for y in range(140):
            for x in range(140):
                if (x - 70) ** 2 + (y - 70) ** 2 <= 40 ** 2:
                    pixel[x, y] = (210, 40, 40, 255)
        caja = {'x': 16, 'y': 16, 'w': 108, 'h': 108}
        self.assertIsNone(_cuadrado_de_simbolo(np.array(imagen.convert('RGB')), caja))

    def test_el_degradado_del_contorno_se_queda_con_su_color(self):
        escena = np.array([20, 70, 160], np.float32)
        rojo = np.array([210, 40, 40], np.float32)
        lienzo = np.zeros((140, 140, 4), np.uint8)
        lienzo[:, :] = (20, 70, 160, 255)
        for y in range(140):
            for x in range(140):
                dist = ((x - 70) ** 2 + (y - 70) ** 2) ** 0.5
                if dist <= 26:
                    lienzo[y, x, :3] = (210, 40, 40)
                elif dist < 40:
                    t = (40 - dist) / 14.0
                    lienzo[y, x, :3] = np.clip(escena + t * (rojo - escena), 0, 255).astype(np.uint8)
        recorte, info = _recortar_silueta(Image.fromarray(lienzo, 'RGBA'), {'x': 20, 'y': 20, 'w': 100, 'h': 100})
        self.assertTrue(info.get('usable'))
        arr = np.array(recorte)
        self.assertGreater(int(arr[arr.shape[0] // 2, arr.shape[1] // 2, 0]), 180)
        self.assertEqual(int(arr[arr.shape[0] // 2, arr.shape[1] // 2, 3]), 255)
        # A mitad del degradado el rojo sigue presente y no queda el azul del fondo.
        mezcla = (arr[:, :, 0] > 90) & (arr[:, :, 0] < 180) & (arr[:, :, 3] > 200)
        self.assertGreater(int(mezcla.sum()), 40)
        azul = (arr[:, :, 2] > 140) & (arr[:, :, 0] < 50) & (arr[:, :, 3] > 16)
        self.assertEqual(int(azul.sum()), 0)

    def test_el_simbolo_queda_solo_dentro_de_su_caja(self):
        imagen = Image.new('RGBA', (120, 100), (12, 40, 30, 255))
        pixel = imagen.load()
        for y in range(28, 72):
            for x in range(34, 86):
                pixel[x, y] = (220, 40, 50, 255)
        for y in range(8, 18):
            for x in range(8, 22):
                pixel[x, y] = (240, 210, 40, 255)
        recorte, info = _recortar_silueta(imagen, {'x': 16, 'y': 14, 'w': 88, 'h': 72})
        self.assertTrue(info.get('usable'))
        arr = np.array(recorte)
        rojo = (arr[:, :, 0] > 180) & (arr[:, :, 1] < 80) & (arr[:, :, 3] > 200)
        oro = (arr[:, :, 0] > 200) & (arr[:, :, 1] > 160) & (arr[:, :, 3] > 200)
        self.assertGreater(int(rojo.sum()), 800)
        self.assertEqual(int(oro.sum()), 0)

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
