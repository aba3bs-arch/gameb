import { randomUUID } from 'node:crypto';
import { getStore } from '@netlify/blobs';
import { getDatabase } from '@netlify/database';
import type { Config } from '@netlify/functions';

function reply(data: unknown, status = 200) {
  return Response.json(data, { status, headers: { 'Cache-Control': 'no-store' } });
}

export default async (req: Request) => {
  const url = new URL(req.url);
  const path = url.pathname;
  if (!['GET', 'POST'].includes(req.method)) return reply({ error: 'Método no permitido.' }, 405);
  if (req.method === 'POST' && req.headers.get('origin') !== url.origin) return reply({ error: 'Origen no permitido.' }, 403);
  try {
    const db = getDatabase();
    const store = getStore({ name: 'library-images', consistency: 'strong' });
    if (req.method === 'GET' && path === '/api/assets') {
      const assets = await db.sql`SELECT filename, name, bytes, type FROM library_assets ORDER BY created_at DESC`;
      return reply({ ok: true, assets: assets.map(a => ({ ...a, url: '/assets/imported/' + a.filename })) });
    }
    if (req.method === 'GET' && path.startsWith('/assets/imported/')) {
      const filename = path.slice('/assets/imported/'.length);
      if (!/^[a-zA-Z0-9_-]+\.(png|jpg|webp)$/.test(filename)) return reply({ error: 'Nombre de archivo no válido.' }, 400);
      const [asset] = await db.sql`SELECT type FROM library_assets WHERE filename = ${filename}`;
      if (!asset) return reply({ error: 'El componente no existe.' }, 404);
      const image = await store.get(filename, { type: 'arrayBuffer' });
      if (!image) return reply({ error: 'La imagen no está disponible.' }, 404);
      return new Response(image, { headers: { 'Content-Type': String(asset.type), 'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff' } });
    }
    if (req.method !== 'POST' || !['/api/assets/import', '/api/assets/delete'].includes(path)) return reply({ error: 'Ruta no encontrada.' }, 404);
    // Base64 adds one third to the file size; stay below the function's 6 MB request limit.
    if (Number(req.headers.get('content-length')) > 5700000) return reply({ error: 'La imagen supera 4 MB.' }, 413);
    const text = await req.text();
    if (text.length > 5700000) return reply({ error: 'La imagen supera 4 MB.' }, 413);
    let body;
    try { body = JSON.parse(text); } catch { return reply({ error: 'Solicitud JSON inválida.' }, 400); }
    if (!body || typeof body !== 'object' || Array.isArray(body)) return reply({ error: 'Solicitud inválida.' }, 400);
    if (path === '/api/assets/delete') {
      if (typeof body.filename !== 'string' || !/^[a-zA-Z0-9_-]+\.(png|jpg|webp)$/.test(body.filename)) return reply({ error: 'Nombre de archivo no válido.' }, 400);
      const [asset] = await db.sql`SELECT filename FROM library_assets WHERE filename = ${body.filename}`;
      if (!asset) return reply({ error: 'El componente no existe.' }, 404);
      await store.delete(body.filename);
      await db.sql`DELETE FROM library_assets WHERE filename = ${body.filename}`;
      return reply({ ok: true });
    }
    const extensions: Record<string, string> = { 'image/png': 'png', 'image/jpeg': 'jpg', 'image/webp': 'webp' };
    const mime = typeof body.mimeType === 'string' ? body.mimeType : '';
    if (!Object.hasOwn(extensions, mime)) return reply({ error: 'Formato no admitido. Usa PNG, JPG o WebP.' }, 400);
    const match = typeof body.data === 'string' && body.data.match(/^data:(image\/(?:png|jpeg|webp));base64,([A-Za-z0-9+/]+={0,2})$/);
    if (!match || match[1] !== mime || match[2].length % 4 !== 0) return reply({ error: 'Los datos de la imagen no son válidos.' }, 400);
    const image = Buffer.from(match[2], 'base64');
    if (!image.length || image.length > 4 * 1024 * 1024) return reply({ error: 'La imagen debe ocupar entre 1 byte y 4 MB.' }, 413);
    const valid = mime === 'image/png' ? image.subarray(0, 8).equals(Buffer.from([137,80,78,71,13,10,26,10]))
      : mime === 'image/jpeg' ? image[0] === 255 && image[1] === 216 && image[2] === 255
      : image.toString('ascii', 0, 4) === 'RIFF' && image.toString('ascii', 8, 12) === 'WEBP';
    if (!valid) return reply({ error: 'El contenido no coincide con el formato de imagen.' }, 400);
    const name = typeof body.name === 'string' ? body.name.trim().slice(0, 100) || 'componente' : 'componente';
    const filename = randomUUID() + '.' + extensions[mime];
    await store.set(filename, new Uint8Array(image).buffer);
    try {
      await db.sql`INSERT INTO library_assets (filename, name, bytes, type) VALUES (${filename}, ${name}, ${image.length}, ${mime})`;
    } catch (error) {
      await store.delete(filename);
      throw error;
    }
    return reply({ ok: true, name, filename, url: '/assets/imported/' + filename, bytes: image.length, type: mime });
  } catch {
    return reply({ error: 'No se pudo acceder a la biblioteca. Inténtalo de nuevo en unos momentos.' }, 503);
  }
};

export const config: Config = { path: ['/api/assets', '/api/assets/import', '/api/assets/delete', '/assets/imported/:filename'] };
