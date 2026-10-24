const $ = id => document.getElementById(id);
const PASOS = [
  'Primero: el fondo, la escena completa.',
  'Después: el título o el logo.',
  'Después: cada placa, una por una.',
  'Después: el marco de los rodillos, si hay.',
  'Después: cada símbolo, de izquierda a derecha y de arriba abajo.',
  'Después: cada botón.',
  'Después: cada panel.',
  'Al final: los letreros de líneas.',
];
let img = null;
let ocupado = false;

function estado(texto, clase) {
  $('status').textContent = texto;
  $('status').className = clase || '';
}

function marcarPaso(indice) {
  [...$('pasos').children].forEach((item, i) => {
    item.classList.toggle('active', i === indice);
    item.classList.toggle('done', i < indice);
  });
}

PASOS.forEach(texto => {
  const item = document.createElement('li');
  item.textContent = texto;
  $('pasos').appendChild(item);
});

function rango(piece) {
  const texto = `${piece.type || ''} ${piece.name || ''}`.toLowerCase();
  if (texto.includes('fondo')) return 0;
  if (/t[ií]tulo|logo/.test(texto)) return 1;
  if (texto.includes('jackpot') || texto.includes('placa')) return 2;
  if (texto.includes('marco')) return 3;
  if (/s[ií]mbolo/.test(texto)) return 4;
  if (/bot[oó]n/.test(texto)) return 5;
  if (texto.includes('panel')) return 6;
  return 7;
}

function margen(piece) {
  const puesto = rango(piece);
  if (puesto === 1) return [0.22, 0.32];
  if (puesto === 2) return [0.16, 0.2];
  if (puesto === 4) return [0.14, 0.16];
  if (puesto === 3) return [0.08, 0.08];
  return [0.12, 0.14];
}

function recorte(piece) {
  const [fx, fy] = margen(piece);
  const padX = Math.max(8, Math.round(piece.w * fx));
  const padY = Math.max(8, Math.round(piece.h * fy));
  const x = Math.max(0, Math.floor(piece.x - padX));
  const y = Math.max(0, Math.floor(piece.y - padY));
  const w = Math.max(1, Math.min(img.naturalWidth - x, Math.round(piece.w + padX * 2)));
  const h = Math.max(1, Math.min(img.naturalHeight - y, Math.round(piece.h + padY * 2)));
  const lienzo = document.createElement('canvas');
  lienzo.width = w;
  lienzo.height = h;
  lienzo.getContext('2d').drawImage(img, x, y, w, h, 0, 0, w, h);
  return lienzo.toDataURL('image/png');
}

function mostrar(datos, nombre) {
  $('resultado').innerHTML = '';
  const foto = document.createElement('img');
  foto.src = datos.image;
  foto.alt = nombre;
  $('resultado').appendChild(foto);
  const nota = document.createElement('p');
  nota.className = 'hint';
  nota.textContent = datos.nota || nombre;
  $('resultado').appendChild(nota);
}

async function guardar(nombre, imagen, tipo) {
  const respuesta = await fetch('/api/assets/import', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({name: nombre, filename: nombre + '.png', mimeType: 'image/png', data: imagen}),
  });
  const datos = await respuesta.json();
  if (!respuesta.ok) throw new Error(datos.error || 'No se pudo guardar ' + nombre);
  const item = document.createElement('div');
  item.className = 'piece';
  const foto = document.createElement('img');
  foto.src = imagen;
  foto.alt = nombre;
  const texto = document.createElement('div');
  const titulo = document.createElement('strong');
  titulo.textContent = nombre;
  const meta = document.createElement('small');
  meta.textContent = tipo;
  texto.append(titulo, meta);
  item.append(foto, texto);
  $('lista').appendChild(item);
}

function siguienteNombre(piezas, indice) {
  const proxima = piezas[indice + 1];
  return proxima ? ' La siguiente es: ' + proxima.name + '.' : ' Esta es la última.';
}

$('file').onchange = () => {
  const archivo = $('file').files[0];
  if (!archivo) return;
  const lector = new FileReader();
  lector.onload = () => {
    img = new Image();
    img.onload = () => {
      $('sketch').src = img.src;
      $('sketch').hidden = false;
      $('empezar').disabled = false;
      estado('Boceto listo. Pulsa el botón. El estudio sigue el orden de arriba, sin que marques nada.', 'ok');
    };
    img.onerror = () => estado('No se pudo abrir esa imagen.', 'err');
    img.src = lector.result;
  };
  lector.readAsDataURL(archivo);
};

$('empezar').onclick = async () => {
  if (!img || ocupado) return;
  ocupado = true;
  $('empezar').disabled = true;
  $('lista').innerHTML = '';
  let hechas = 0;
  try {
    const boceto = document.createElement('canvas');
    boceto.width = img.naturalWidth;
    boceto.height = img.naturalHeight;
    boceto.getContext('2d').drawImage(img, 0, 0);
    const bocetoPng = boceto.toDataURL('image/png');
    marcarPaso(0);
    estado('Imagen 1. Primero el fondo, la escena completa.', '');
    const fondo = {image: bocetoPng, nota: 'El fondo es el boceto completo.'};
    mostrar(fondo, 'fondo principal');
    await guardar('fondo principal', fondo.image, 'Fondo');
    hechas += 1;
    $('cuenta').textContent = 'Imagen 1 guardada. Sigue el título.';
    estado('Fondo listo. Ahora se buscan las demás piezas, en el orden de arriba.', '');
    const controlador = new AbortController();
    const reloj = setTimeout(() => controlador.abort(), 150000);
    let respuesta;
    try {
      respuesta = await fetch('/api/orden', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({image: bocetoPng}),
        signal: controlador.signal,
      });
    } finally {
      clearTimeout(reloj);
    }
    let datos;
    try { datos = await respuesta.json(); } catch (error) { throw new Error('El estudio no respondió.'); }
    if (!respuesta.ok || !datos.ok) throw new Error(datos.error || 'No se pudo leer el orden.');
    const piezas = (datos.pieces || []).filter(piece => rango(piece) !== 0);
    for (let i = 0; i < piezas.length; i++) {
      const piece = piezas[i];
      marcarPaso(rango(piece));
      estado('Imagen ' + (hechas + 1) + '. Ahora: ' + piece.name + '.' + siguienteNombre(piezas, i), '');
      const hecha = await fetch('/api/hacer-imagen', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({image: recorte(piece), kind: [piece.type, piece.name].filter(Boolean).join(' ')}),
      });
      const cuerpo = await hecha.json();
      if (!hecha.ok || !cuerpo.ok) throw new Error(cuerpo.error || 'No se pudo hacer ' + piece.name);
      mostrar(cuerpo, piece.name);
      await guardar(piece.name, cuerpo.image, piece.type || 'Pieza');
      hechas += 1;
      $('cuenta').textContent = 'Van ' + hechas + ' imágenes.';
    }
    marcarPaso(PASOS.length);
    estado('Listo. Se hicieron ' + hechas + ' imágenes, una por una, en el orden de arriba.', 'ok');
  } catch (error) {
    const mensaje = error.name === 'AbortError' ? 'Tardó demasiado en encontrar las piezas. Vuelve a pulsar el botón.' : error.message;
    estado(mensaje, 'err');
  } finally {
    ocupado = false;
    $('empezar').disabled = false;
  }
};
