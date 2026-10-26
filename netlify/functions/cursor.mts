import { createHmac, timingSafeEqual } from 'node:crypto';

declare const Netlify: { env: { get(name: string): string | undefined } };

function reply(data: unknown, status = 200, cookie?: string) {
  return new Response(JSON.stringify(data), { status, headers: {
    'Content-Type': 'application/json', 'Cache-Control': 'no-store',
    ...(cookie ? { 'Set-Cookie': cookie } : {}),
  } });
}

export default async (req: Request) => {
  const key = Netlify.env.get('CURSOR_API_KEY');
  const url = new URL(req.url);
  if (req.method === 'GET' && url.searchParams.get('status') === '1') {
    return reply({ configured: Boolean(key), provider: 'Cursor' });
  }
  if (!['GET', 'POST'].includes(req.method)) return reply({ error: 'Método no permitido.' }, 405);
  if (!key) return reply({ error: 'Falta configurar CURSOR_API_KEY en Netlify con alcance Functions y volver a desplegar.' }, 503);
  if (req.method === 'POST' && req.headers.get('origin') !== url.origin) return reply({ error: 'Origen no permitido.' }, 403);
  const sign = (value: string) => createHmac('sha256', key).update(value).digest('base64url');
  const cookieValue = req.headers.get('cookie')?.split(';').map(s => s.trim()).find(s => s.startsWith('gameb_cursor='))?.slice(13);
  let session: { agent: string; run: string; expires: number } | null = null;
  if (cookieValue) {
    const [data, signature] = cookieValue.split('.');
    const expected = sign(data);
    if (signature && signature.length === expected.length && timingSafeEqual(Buffer.from(signature), Buffer.from(expected))) {
      try {
        const parsed = JSON.parse(Buffer.from(data, 'base64url').toString());
        if (/^bc-[\w-]+$/.test(parsed.agent) && /^run-[\w-]+$/.test(parsed.run) && parsed.expires > Date.now()) session = parsed;
      } catch { /* Ignore an expired or malformed session. */ }
    }
  }
  const cookie = (value: string, age = 86400) => `gameb_cursor=${value}; Path=/api/cursor; HttpOnly; SameSite=Strict; Max-Age=${age}${url.protocol === 'https:' ? '; Secure' : ''}`;
  const call = async (path: string, method = 'GET', body?: unknown) => {
    const response = await fetch(`https://api.cursor.com/v1${path}`, {
      method, headers: { Authorization: `Bearer ${key}`, 'Content-Type': 'application/json' },
      ...(body ? { body: JSON.stringify(body) } : {}), signal: AbortSignal.timeout(25000),
    });
    if (!response.ok) {
      const messages: Record<number, string> = {
        400: 'Cursor rechazó la solicitud. Revisa que tu cuenta permita Cloud Agents.',
        401: 'Cursor rechazó la clave de API. Revísala en Netlify.',
        403: 'Tu cuenta de Cursor no tiene permiso para esta operación.',
        404: 'Cursor no encontró esta conversación. Limpia la conversación para empezar otra.',
        409: 'Cursor todavía tiene una tarea activa. Espera o pulsa Detener.',
        429: 'Cursor alcanzó su límite de uso. Revisa los límites de tu cuenta e inténtalo después.',
      };
      const error = new Error(messages[response.status] || 'Cursor no está disponible en este momento. Inténtalo después.');
      error.name = 'CursorError';
      throw error;
    }
    return response.json();
  };
  try {
    if (req.method === 'GET') {
      if (!session) return reply({ error: 'No hay una tarea de Cursor activa.' }, 404);
      const run = await call(`/agents/${session.agent}/runs/${session.run}`);
      return reply({ status: run.status, text: typeof run.result === 'string' ? run.result : '' });
    }
    if (Number(req.headers.get('content-length')) > 24000) return reply({ error: 'La orden es demasiado larga.' }, 413);
    let body;
    try { body = JSON.parse(await req.text()); } catch { return reply({ error: 'Solicitud inválida.' }, 400); }
    if (body.action === 'cancel' || body.action === 'reset') {
      if (session) {
        try { await call(`/agents/${session.agent}/runs/${session.run}/cancel`, 'POST'); }
        catch (error) { if (!(error instanceof Error) || error.name !== 'CursorError' || !error.message.includes('tarea activa')) throw error; }
      }
      return reply({ ok: true }, 200, body.action === 'reset' ? cookie('', 0) : undefined);
    }
    if (body.action !== 'send' || typeof body.text !== 'string' || !body.text.trim() || body.text.length > 16000) {
      return reply({ error: 'Escribe una orden de hasta 16000 caracteres.' }, 400);
    }
    const prompt = { text: `Responde en español para GAMEB Studio. Ayuda a planear, diseñar y programar juegos.\n${body.text}` };
    let agent: string, run: string;
    if (session) {
      const result = await call(`/agents/${session.agent}/runs`, 'POST', { prompt });
      agent = session.agent;
      run = result.run?.id || result.id;
    } else {
      // A no-repository agent keeps conversation context without changing the site repository.
      const result = await call('/agents', 'POST', { prompt, name: 'GAMEB Studio', autoCreatePR: false });
      agent = result.agent?.id;
      run = result.run?.id;
    }
    if (!agent || !run) throw new Error('Cursor no devolvió una tarea válida.');
    const data = Buffer.from(JSON.stringify({ agent, run, expires: Date.now() + 86400000 })).toString('base64url');
    return reply({ status: 'CREATING' }, 200, cookie(`${data}.${sign(data)}`));
  } catch (error) {
    const message = error instanceof Error && error.name === 'CursorError'
      ? error.message : 'No se pudo contactar con Cursor. Inténtalo de nuevo.';
    return reply({ error: message }, 502);
  }
};

export const config = { path: '/api/cursor' };
