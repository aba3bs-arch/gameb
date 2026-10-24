"""Empaquetado de varios bocetos en un solo ZIP."""
import base64
import io
import unittest
import zipfile
from PIL import Image

import server


def _svg(label, color):
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1000 600">'
        f'<rect width="1000" height="600" fill="{color}"/>'
        f'<text x="40" y="80">{label}</text></svg>'
    )


class SketchZipTest(unittest.TestCase):
    def test_conserva_los_tres_bocetos_en_un_zip(self):
        blob, filename = server.build_sketches_zip('Mi tragamonedas', [
            {'concept': 'desierto', 'style': 'Moderno', 'theme': 'Arena', 'svg': _svg('Boceto uno', '#123456')},
            {'concept': 'mar', 'style': 'Retro', 'theme': 'Azul', 'svg': _svg('Boceto dos', '#204060')},
            {'concept': 'selva', 'style': 'Fantasía', 'theme': 'Verde', 'svg': '```svg\n' + _svg('Boceto tres', '#206040') + '\n```'},
        ])
        self.assertEqual(filename, 'Mi_tragamonedas_bocetos.zip')
        archive = zipfile.ZipFile(io.BytesIO(blob))
        names = archive.namelist()
        for number in (1, 2, 3):
            self.assertIn(f'Mi_tragamonedas/boceto-{number:02d}.svg', names)
        self.assertIn('Mi_tragamonedas/index.html', names)
        page = archive.read('Mi_tragamonedas/index.html').decode('utf-8')
        self.assertIn('Boceto 1', page)
        self.assertIn('Boceto 2', page)
        self.assertIn('Boceto 3', page)
        self.assertIn('desierto', page)
        self.assertIn('selva', page)
        self.assertIn('Boceto uno', archive.read('Mi_tragamonedas/boceto-01.svg').decode('utf-8'))
        self.assertIn('Boceto tres', archive.read('Mi_tragamonedas/boceto-03.svg').decode('utf-8'))

    def test_incluye_png_y_escapa_la_descripcion(self):
        image = Image.new('RGBA', (4, 4), (10, 20, 30, 255))
        buffer = io.BytesIO()
        image.save(buffer, format='PNG')
        data = 'data:image/png;base64,' + base64.b64encode(buffer.getvalue()).decode('ascii')
        blob, _filename = server.build_sketches_zip('Juego', [{
            'svg': _svg('Seguro', '#111111'),
            'png': data,
            'concept': '<script>alert(1)</script>',
        }])
        archive = zipfile.ZipFile(io.BytesIO(blob))
        self.assertTrue(archive.read('Juego/boceto-01.png').startswith(b'\x89PNG'))
        page = archive.read('Juego/index.html').decode('utf-8')
        self.assertIn('&lt;script&gt;', page)
        self.assertNotIn('<script>alert', page)

    def test_rechaza_un_svg_con_script(self):
        with self.assertRaises(ValueError):
            server.build_sketches_zip('Juego', [{'svg': '<svg><script>alert(1)</script></svg>'}])


if __name__ == '__main__':
    unittest.main()
