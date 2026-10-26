import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { stripTypeScriptTypes } from 'node:module';

test('Library uploads, lists, serves and deletes files and rejects invalid requests', async () => {
  const files = new Map();
  const rows = new Map();
  const store = {
    set: async (key, value) => files.set(key, value),
    get: async key => files.get(key) ?? null,
    delete: async key => files.delete(key),
  };
  const sql = async (parts, ...values) => {
    const query = parts.join('?');
    if (query.startsWith('INSERT')) {
      const [filename, name, bytes, type] = values;
      rows.set(filename, { filename, name, bytes, type });
      return [];
    }
    if (query.startsWith('DELETE')) { rows.delete(values[0]); return []; }
    return values.length ? (rows.has(values[0]) ? [rows.get(values[0])] : []) : [...rows.values()];
  };
  globalThis.__libraryTest = { store, db: { sql } };
  try {
    let source = await readFile(new URL('../netlify/functions/assets.mts', import.meta.url), 'utf8');
    source = source.replace("import { getStore } from '@netlify/blobs';", 'const getStore = () => globalThis.__libraryTest.store;')
      .replace("import { getDatabase } from '@netlify/database';", 'const getDatabase = () => globalThis.__libraryTest.db;');
    const compiled = stripTypeScriptTypes(source);
    const { default: handler, config } = await import('data:text/javascript;base64,' + Buffer.from(compiled).toString('base64'));
    assert.ok(config.path.includes('/api/assets'));
    const request = (path, body, origin = 'https://example.test') => new Request('https://example.test' + path, body === undefined ? {} : {
      method: 'POST', headers: { origin, 'Content-Type': 'application/json' }, body: JSON.stringify(body),
    });
    assert.deepEqual(await (await handler(request('/api/assets'))).json(), { ok: true, assets: [] });
    const png = 'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII=';
    const body = { name: 'Mi símbolo', mimeType: 'image/png', data: png };
    assert.equal((await handler(request('/api/assets/import', body, 'https://other.test'))).status, 403);
    assert.equal((await handler(request('/api/assets/import', { ...body, data: 'data:image/png;base64,SG9sYQ==' }))).status, 400);
    assert.equal((await handler(request('/api/assets/import', { ...body, mimeType: 'image/svg+xml' }))).status, 400);
    assert.equal((await handler(request('/api/assets/import', null))).status, 400);
    assert.equal((await handler(request('/api/assets/delete', { filename: '../image.png' }))).status, 400);
    const imported = await (await handler(request('/api/assets/import', body))).json();
    assert.equal(imported.name, 'Mi símbolo');
    assert.equal(files.size, 1);
    const listed = await (await handler(request('/api/assets'))).json();
    assert.equal(listed.assets[0].filename, imported.filename);
    const served = await handler(request(imported.url));
    assert.equal(served.headers.get('content-type'), 'image/png');
    assert.deepEqual(Buffer.from(await served.arrayBuffer()), Buffer.from(png.split(',')[1], 'base64'));
    assert.equal((await handler(request('/api/assets/delete', { filename: imported.filename }))).status, 200);
    assert.equal(files.size, 0);
    assert.equal((await handler(request(imported.url))).status, 404);
    assert.equal((await handler(request('/api/assets/delete', { filename: imported.filename }))).status, 404);
    globalThis.__libraryTest.db.sql = async () => { throw Error('Internal detail'); };
    const failure = await handler(request('/api/assets'));
    assert.equal(failure.status, 503);
    assert.doesNotMatch(await failure.text(), /Internal detail/);
  } finally { delete globalThis.__libraryTest; }
});
