import test from 'node:test';
import assert from 'node:assert/strict';
import handler from '../netlify/functions/cursor.mts';

// Fake credentials and mocked network calls: no real account or paid tasks.
test('Cursor configuration and conversation lifecycle', async () => {
  const originalFetch = globalThis.fetch;
  let configured = false;
  globalThis.Netlify = { env: { get: () => configured ? 'test-only-placeholder' : undefined } };
  const request = (body, cookie, origin = 'https://example.test') => new Request('https://example.test/api/cursor', {
    method: 'POST', headers: { origin, 'Content-Type': 'application/json', ...(cookie ? { cookie } : {}) }, body: JSON.stringify(body),
  });
  try {
    let response = await handler(new Request('https://example.test/api/cursor?status=1'));
    assert.deepEqual(await response.json(), { configured: false, provider: 'Cursor' });
    assert.equal((await handler(request({ action: 'send', text: 'Hola' }))).status, 503);
    configured = true;
    assert.equal((await handler(request({ action: 'send', text: 'Hola' }, null, 'https://elsewhere.test'))).status, 403);
    assert.equal((await handler(request({ action: 'send', text: '' }))).status, 400);
    const calls = [];
    globalThis.fetch = async (url, options) => {
      calls.push({ url, options });
      if (url.endsWith('/cancel')) return Response.json({ id: 'run-demo' });
      if (url.endsWith('/agents') && options.method === 'POST') return Response.json({ agent: { id: 'bc-demo' }, run: { id: 'run-demo' } });
      if (url.endsWith('/runs') && options.method === 'POST') return Response.json({ id: 'run-followup' });
      return Response.json({ status: 'FINISHED', result: 'Respuesta de Cursor' });
    };
    response = await handler(request({ action: 'send', text: 'Hola' }));
    assert.equal(response.status, 200);
    const cookie = response.headers.get('set-cookie').split(';')[0];
    assert.match(response.headers.get('set-cookie'), /HttpOnly; SameSite=Strict/);
    assert.equal(JSON.parse(calls[0].options.body).repos, undefined);
    response = await handler(new Request('https://example.test/api/cursor', { headers: { cookie } }));
    assert.deepEqual(await response.json(), { status: 'FINISHED', text: 'Respuesta de Cursor' });
    response = await handler(request({ action: 'send', text: 'Continúa' }, cookie));
    assert.equal(response.status, 200);
    assert.equal(calls.at(-1).url, 'https://api.cursor.com/v1/agents/bc-demo/runs');
    response = await handler(request({ action: 'reset' }, cookie));
    assert.match(response.headers.get('set-cookie'), /Max-Age=0/);
    assert.equal(calls.at(-1).url, 'https://api.cursor.com/v1/agents/bc-demo/runs/run-demo/cancel');
    const before = calls.length;
    response = await handler(new Request('https://example.test/api/cursor', { headers: { cookie: cookie + 'tampered' } }));
    assert.equal(response.status, 404);
    assert.equal(calls.length, before);
    globalThis.fetch = async () => new Response('Private provider error body', { status: 401 });
    response = await handler(request({ action: 'send', text: 'Hola' }));
    assert.equal(response.status, 502);
    assert.doesNotMatch(await response.text(), /Private provider error body/);
  } finally {
    globalThis.fetch = originalFetch;
    delete globalThis.Netlify;
  }
});
