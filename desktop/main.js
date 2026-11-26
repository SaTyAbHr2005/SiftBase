// SiftBase desktop: starts the local API (python -m scripts.serve) on a free port with a fresh key, and gives the
// window a small IPC surface. Model keys stay in this process, encrypted per OS user; the page only sees the last 4.
const { app, BrowserWindow, ipcMain, dialog, safeStorage, shell } = require('electron');
const { spawn } = require('node:child_process');
const crypto = require('node:crypto');
const fs = require('node:fs');
const path = require('node:path');
const { toRun } = require('./lib/run');

const ROOT = path.resolve(__dirname, '..'); // the SiftBase repo: kb/, scripts/, .env
// The env file the API loads, as kb/config.py reads it: KB_ENV_FILE, else the repo's .env.
const ENV_FILE = process.env.KB_ENV_FILE || path.join(ROOT, '.env');
const PYTHON = process.env.SIFTBASE_PYTHON || (process.platform === 'win32' ? 'python' : 'python3');
const USER = () => app.getPath('userData');
const file = (name) => path.join(USER(), name);
const COLLECTION_RE = /^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$/;

// ------------------------------------------------------------------ small JSON stores in the user's app folder
function readJson(name, fallback) {
  try { return JSON.parse(fs.readFileSync(file(name), 'utf8')); } catch { return fallback; }
}
function writeJson(name, value) {
  fs.mkdirSync(USER(), { recursive: true });
  const tmp = file(name + '.tmp');
  fs.writeFileSync(tmp, JSON.stringify(value));
  fs.renameSync(tmp, file(name));
}

// ------------------------------------------------------------------ model keys
// Free providers first; a paid model, if the user has one, goes first in the writer or judge chain.
const FREE = ['CLOUDFLARE_ACCOUNT_ID', 'CLOUDFLARE_API_TOKEN', 'GROQ_API_KEY'];
const PROVIDERS = { // provider -> key variable (kb/model_api.py CATALOG)
  cloudflare: 'CLOUDFLARE_API_TOKEN', groq: 'GROQ_API_KEY', openrouter: 'OPENROUTER_API_KEY',
  mistral: 'MISTRAL_API_KEY', gemini: 'GEMINI_API_KEY',
};
const PRIVATE_SAFE = new Set(['cloudflare', 'groq']);
// Fallbacks after a paid model: kb/model_api.py WRITER_CHAIN and DEFAULT_CHAIN, limited to private-safe providers
// unless the user allowed others (an explicit chain naming one in private mode is refused by build_providers).
const CHAINS = {
  writer: { private: 'cloudflare,groq:qwen/qwen3.8-27b,groq:openai/gpt-oss-20b',
    open: 'cloudflare,groq:qwen/qwen3.8-27b,openrouter,mistral,gemini,mistral:ministral-8b-latest,groq:openai/gpt-oss-20b' },
  judge: { private: 'cloudflare,groq:openai/gpt-oss-20b',
    open: 'cloudflare,groq:openai/gpt-oss-20b,openrouter,mistral,mistral:ministral-8b-latest,gemini' },
};

const seal = (s) => (safeStorage.isEncryptionAvailable() ? safeStorage.encryptString(s).toString('base64') : null);
const unseal = (b) => { try { return safeStorage.decryptString(Buffer.from(b, 'base64')); } catch { return ''; } };
function loadKeys() {
  const raw = readJson('keys.json', {});
  const out = { values: {}, paid: raw.paid || {}, allowShare: !!raw.allowShare };
  for (const [k, v] of Object.entries(raw.values || {})) out.values[k] = unseal(v);
  for (const role of ['writer', 'judge']) if (out.paid[role]) out.paid[role] = { ...out.paid[role], key: unseal(out.paid[role].key || '') };
  return out;
}
const mask = (v) => (v ? '••••' + v.slice(-4) : '');
function keysForPage() {
  const k = loadKeys();
  const paid = {};
  for (const role of ['writer', 'judge']) if (k.paid[role]) paid[role] = { provider: k.paid[role].provider, model: k.paid[role].model, key: mask(k.paid[role].key) };
  const fromEnv = envFileKeys();
  return { values: Object.fromEntries(FREE.map((n) => [n, mask(k.values[n])])), paid, allowShare: k.allowShare, fromEnv,
    ready: hasProvider({ ...Object.fromEntries(fromEnv.map((n) => [n, '1'])), ...k.values }), encryption: safeStorage.isEncryptionAvailable() };
}
// Names (never values) of free keys already set in the env file the API also loads.
function envFileKeys() {
  try {
    const set = fs.readFileSync(ENV_FILE, 'utf8').split(/\r?\n/)
      .map((l) => l.match(/^\s*([A-Z_]+)\s*=\s*["']?(.+?)["']?\s*$/)).filter(Boolean).map((m) => m[1]);
    return FREE.filter((n) => set.includes(n) || process.env[n]);
  } catch { return FREE.filter((n) => process.env[n]); }
}
const hasProvider = (v) => !!((v.CLOUDFLARE_ACCOUNT_ID && v.CLOUDFLARE_API_TOKEN) || v.GROQ_API_KEY);

function saveKeys(input) {
  if (!safeStorage.isEncryptionAvailable() || (process.platform === 'linux' && safeStorage.getSelectedStorageBackend() === 'basic_text')) throw new Error('This system cannot encrypt saved keys, so none were saved.');
  const cur = loadKeys();
  const values = { ...cur.values };
  for (const n of FREE) {
    const v = typeof input.values?.[n] === 'string' ? input.values[n].trim() : undefined;
    if (v && /[\0\r\n\s]/.test(v)) throw new Error('A key contains spaces or line breaks. Paste it again.');
    if (v !== undefined && v !== '' && !v.startsWith('••••')) values[n] = v; // a masked value means "unchanged"
    if (v === '') delete values[n];
  }
  if (!hasProvider(values)) throw new Error('Add a Cloudflare account ID and token, or a Groq key.');
  const paid = {};
  for (const role of ['writer', 'judge']) {
    const p = input.paid?.[role];
    if (!p || !p.provider) continue;
    if (typeof p.provider !== 'string' || !Object.hasOwn(PROVIDERS, p.provider)) throw new Error('Unknown provider.');
    const model = String(p.model || '').trim();
    if (!/^[\w@./:-]{1,120}$/.test(model)) throw new Error(`Enter the ${role} model's name as the provider lists it.`);
    let key = String(p.key || '').trim();
    if (key.startsWith('••••')) key = cur.paid[role]?.key || '';
    if (!key) throw new Error(`Add the API key for the ${role} model.`);
    if (/[\0\r\n\s]/.test(key)) throw new Error(`The ${role} key contains spaces or line breaks. Paste it again.`);
    if (!PRIVATE_SAFE.has(p.provider) && !input.allowShare) throw new Error(`${p.provider} may keep or train on document text. Tick "Allow" to use it.`);
    paid[role] = { provider: p.provider, model, key: seal(key) };
  }
  writeJson('keys.json', { values: Object.fromEntries(Object.entries(values).map(([k, v]) => [k, seal(v)])), paid, allowShare: !!input.allowShare });
}

function modelEnv() {
  const k = loadKeys(), env = { ...k.values };
  env.KB_PRIVATE = k.allowShare ? '0' : '1'; // set either way, so a KB_PRIVATE=0 in .env cannot override the UI
  for (const [role, variable] of [['writer', 'KB_WRITER_PROVIDERS'], ['judge', 'KB_LLM_PROVIDERS']]) {
    const p = k.paid[role];
    if (!p) continue;
    env[PROVIDERS[p.provider]] = p.key;
    env[variable] = `${p.provider}:${p.model},${CHAINS[role][k.allowShare ? 'open' : 'private']}`;
  }
  // Naming a judge chain alone would move the writer onto it too (kb/config.py), so keep the writer's default.
  if (env.KB_LLM_PROVIDERS && !env.KB_WRITER_PROVIDERS) env.KB_WRITER_PROVIDERS = CHAINS.writer[k.allowShare ? 'open' : 'private'];
  return env;
}

// One request to each provider's key or model list: checks the key without spending any model allowance.
async function testKey(provider, values) {
  const checks = {
    cloudflare: () => ['https://api.cloudflare.com/client/v4/user/tokens/verify', { Authorization: `Bearer ${values.CLOUDFLARE_API_TOKEN}` }],
    groq: () => ['https://api.groq.com/openai/v1/models', { Authorization: `Bearer ${values.key}` }],
    openrouter: () => ['https://openrouter.ai/api/v1/key', { Authorization: `Bearer ${values.key}` }],
    mistral: () => ['https://api.mistral.ai/v1/models', { Authorization: `Bearer ${values.key}` }],
    gemini: () => ['https://generativelanguage.googleapis.com/v1beta/models', { 'x-goog-api-key': values.key }],
  };
  if (!Object.hasOwn(checks, provider)) return { ok: false, message: 'Unknown provider.' };
  const saved = loadKeys();
  if (provider === 'cloudflare' && (!values.CLOUDFLARE_API_TOKEN || values.CLOUDFLARE_API_TOKEN.startsWith('••••'))) values.CLOUDFLARE_API_TOKEN = saved.values.CLOUDFLARE_API_TOKEN;
  if (provider !== 'cloudflare' && (!values.key || values.key.startsWith('••••'))) values.key = values.role ? saved.paid[values.role]?.key : saved.values[PROVIDERS[provider]];
  if (!(values.key || values.CLOUDFLARE_API_TOKEN)) return { ok: false, message: 'No key to test.' };
  const [url, headers] = checks[provider]();
  try {
    const r = await fetch(url, { headers, signal: AbortSignal.timeout(15000) });
    return r.ok ? { ok: true, message: 'Key works.' } : { ok: false, message: r.status === 401 || r.status === 403 ? 'The provider refused this key.' : `The provider answered ${r.status}.` };
  } catch {
    return { ok: false, message: 'No answer from the provider. Check the internet connection.' };
  }
}

// ------------------------------------------------------------------ the local API
const api = { proc: null, port: 0, key: '', state: 'stopped', error: '', log: [] };
let win = null;
const send = (ch, data) => win && !win.isDestroyed() && win.webContents.send(ch, data);

const settings = () => readJson('settings.json', {});
function childEnv() {
  const env = { ...process.env, ...modelEnv(), PYTHONIOENCODING: 'utf-8', PYTHONUNBUFFERED: '1', KB_DESKTOP: '1',
    // This PC's own API: the provider quota is the only limit that matters.
    KB_QUERY_PER_HOUR: '0', KB_QUERIES_PER_DAY: '0', KB_INDEX_PER_DAY: '0' };
  if (settings().dataDir) env.KB_DATA_DIR = settings().dataDir;
  return env;
}
function setApi(state, error = '') { api.state = state; api.error = error; send('api', { state, error }); }

async function startApi() {
  stopApi();
  // The API binds port 0 itself and prints the port it got, so no other program can take the port between our
  // choosing it and Python binding it, and the key is only ever sent to our own child.
  api.port = 0;
  api.key = crypto.randomBytes(24).toString('base64url');
  api.log = [];
  setApi('starting');
  const proc = spawn(PYTHON, ['-m', 'scripts.serve', '--host', '127.0.0.1', '--port', '0', '--env-file', ENV_FILE],
    { cwd: ROOT, env: { ...childEnv(), KB_API_KEYS: api.key }, windowsHide: true });
  api.proc = proc;
  const keep = (d) => {
    const lines = String(d).split(/\r?\n/).filter(Boolean);
    for (const l of lines) {
      const m = l.match(/Uvicorn running on http:\/\/127\.0\.0\.1:(\d+)/);
      if (m && api.proc === proc) api.port = Number(m[1]);
    }
    api.log.push(...lines); api.log = api.log.slice(-40);
  };
  proc.stdout.on('data', keep); proc.stderr.on('data', keep);
  proc.on('error', (e) => { if (api.proc === proc) setApi('failed', `Could not start Python (${PYTHON}): ${e.message}`); });
  proc.on('exit', (code) => { if (api.proc === proc) { api.proc = null; setApi('failed', `The local API stopped (exit ${code}). ${api.log.slice(-3).join(' ')}`); } });
  for (let i = 0; i < 180 && api.proc === proc; i++) {
    // Re-check after the await: a restart may have replaced this process while the request was in flight.
    try { if (api.port && (await call('GET', '/collections', null, 3000)).status === 200 && api.proc === proc) return setApi('running'); } catch { /* not up yet */ }
    await new Promise((r) => setTimeout(r, 500));
  }
  if (api.proc === proc) setApi('failed', 'The local API did not start within 90 s.');
}
function stopApi() { const p = api.proc; api.proc = null; if (p) p.kill(); }

async function call(method, route, body, timeoutMs) {
  const r = await fetch(`http://127.0.0.1:${api.port}${route}`, {
    method, headers: { 'X-API-Key': api.key, ...(body ? { 'Content-Type': 'application/json' } : {}) },
    body: body ? JSON.stringify(body) : undefined, signal: AbortSignal.timeout(timeoutMs), redirect: 'error',
  });
  let json = null;
  try { json = await r.json(); } catch { /* error pages are not JSON */ }
  return { status: r.status, json, retryAfter: Number(r.headers.get('retry-after')) || 0 };
}

let names = {}; // doc_id -> file name, per collection, from the last listing
async function collections() {
  if (api.state !== 'running') return { ok: false, code: 'API_' + api.state.toUpperCase(), message: api.error };
  try {
    const r = await call('GET', '/collections', null, 20000);
    if (r.status !== 200) return { ok: false, code: r.json?.error?.code || 'HTTP_' + r.status, message: r.json?.error?.message || '' };
    names = Object.fromEntries(r.json.collections.map((c) => [c.name, Object.fromEntries(c.docs.map((d) => [d.doc_id, d.name]))]));
    return { ok: true, collections: r.json.collections };
  } catch (e) {
    return { ok: false, code: 'API_UNREACHABLE', message: e.message };
  }
}

// ------------------------------------------------------------------ history
const HISTORY_MAX = 200;
function addHistory(entry) {
  const h = readJson('history.json', []);
  h.unshift(entry);
  writeJson('history.json', h.slice(0, HISTORY_MAX));
}

async function query({ collection, question }) {
  if (!COLLECTION_RE.test(String(collection)) || typeof question !== 'string' || !question.trim() || question.length > 32000) return { ok: false, code: 'INVALID_REQUEST', message: 'Pick a collection and type a question.' };
  if (api.state !== 'running') return { ok: false, code: 'API_' + api.state.toUpperCase(), message: api.error };
  const when = new Date().toISOString();
  try {
    const r = await call('POST', '/query', { collection_name: collection, query: question }, 300000);
    if (r.status !== 200) {
      const out = { ok: false, code: r.json?.error?.code || 'HTTP_' + r.status, message: r.json?.error?.message || '', retryAfter: r.retryAfter };
      addHistory({ when, collection, question, failed: out.code });
      return out;
    }
    if (!names[collection]) await collections();
    const run = toRun(r.json, question, names[collection] || {});
    addHistory({ when, collection, question, run });
    return { ok: true, run };
  } catch (e) {
    const out = { ok: false, code: e.name === 'TimeoutError' ? 'TIMEOUT' : 'API_UNREACHABLE', message: e.message };
    addHistory({ when, collection, question, failed: out.code });
    return out;
  }
}

// ------------------------------------------------------------------ indexing: scripts/index_local.py, one at a time
let indexing = null;
let picked = ''; // the folder the user chose in the main process's own dialog
async function startIndex({ folder, collection }) {
  if (indexing) return { ok: false, message: 'Another folder is being indexed.' };
  if (!COLLECTION_RE.test(String(collection))) return { ok: false, message: 'Use letters, digits, - and _ for the collection name.' };
  try { if (!fs.statSync(folder).isDirectory() && !/\.zip$/i.test(folder)) throw new Error(); } catch { return { ok: false, message: 'Pick a folder or a ZIP file.' }; }
  // A dropped path comes from the page, so the user confirms it here, outside the page.
  if (folder !== picked && (await dialog.showMessageBox(win, { type: 'question', buttons: ['Index', 'Cancel'], defaultId: 0, cancelId: 1, message: `Index ${folder} as ${collection}?` })).response !== 0) return { ok: false, message: 'Cancelled.' };
  if (indexing) return { ok: false, message: 'Another folder is being indexed.' };
  const proc = spawn(PYTHON, [path.join(ROOT, 'scripts', 'index_local.py'), '--src', folder, '--collection', collection],
    { cwd: ROOT, env: { ...childEnv(), KB_ENV_FILE: ENV_FILE }, windowsHide: true });
  const job = (indexing = { proc, collection, tail: [] }); // output can arrive after exit: keep writing to this job
  let buf = '';
  // ProgressBar (kb/ingest/progress.py) prints "<step> [###---] 45% 100/220 | ..." every 5% when not on a terminal.
  const onData = (d) => {
    buf += String(d);
    const lines = buf.split(/\r?\n|\r/); buf = lines.pop();
    for (const line of lines) {
      const m = line.match(/^(.+?) \[[#-]+\]\s+(\d+)% ([\d,]+)\/([\d,]+)/);
      if (m) send('index:progress', { collection, step: m[1], pct: +m[2], done: +m[3].replace(/,/g, ''), total: +m[4].replace(/,/g, '') });
      else if (line.trim()) job.tail = [...job.tail, line].slice(-5);
    }
  };
  proc.stdout.on('data', onData); proc.stderr.on('data', onData);
  proc.on('error', (e) => { if (indexing === job) indexing = null; send('index:done', { collection, ok: false, message: `Could not start Python: ${e.message}` }); });
  proc.on('exit', (code) => {
    const tail = job.tail;
    if (indexing === job) indexing = null;
    send('index:done', { collection, ok: code === 0, message: code === 0 ? '' : tail.filter((l) => !/^\d{4}-\d\d-\d\d /.test(l)).slice(-2).join(' ') || `Indexing stopped (exit ${code}).` });
  });
  return { ok: true };
}

// ------------------------------------------------------------------ window and IPC
function createWindow() {
  win = new BrowserWindow({
    width: 1440, height: 900, minWidth: 1100, minHeight: 700, backgroundColor: '#0B0D12', show: false,
    titleBarStyle: 'hidden', titleBarOverlay: { color: '#11141B', symbolColor: '#A3AAB7', height: 40 },
    webPreferences: { preload: path.join(__dirname, 'preload.js'), contextIsolation: true, sandbox: true, nodeIntegration: false },
  });
  win.once('ready-to-show', () => win.show());
  win.webContents.setWindowOpenHandler(() => ({ action: 'deny' }));
  win.webContents.on('will-navigate', (e) => e.preventDefault());
  win.loadFile(path.join(__dirname, 'renderer', 'index.html'));
}

const handle = (ch, fn) => ipcMain.handle(ch, (e, arg) => {
  if (!win || e.sender !== win.webContents) throw new Error('Unknown sender');
  return fn(arg || {});
});
handle('status', () => ({ api: { state: api.state, error: api.error }, keys: keysForPage(), dataDir: settings().dataDir || path.join(ROOT, 'data'), indexing: indexing && indexing.collection }));
handle('collections', collections);
handle('query', query);
handle('history', () => readJson('history.json', []));
handle('keys:save', async (input) => {
  try { saveKeys(input); } catch (e) { return { ok: false, message: e.message }; }
  startApi().catch((e) => setApi('failed', e.message));
  return { ok: true, keys: keysForPage() };
});
handle('keys:test', ({ provider, values }) => testKey(String(provider), { ...(values || {}) }));
handle('index:start', startIndex);
handle('pick:folder', async () => {
  const r = await dialog.showOpenDialog(win, { properties: ['openDirectory'] });
  picked = r.canceled ? '' : r.filePaths[0];
  return picked || null;
});
handle('data:pick', async () => {
  const r = await dialog.showOpenDialog(win, { properties: ['openDirectory', 'createDirectory'] });
  if (r.canceled) return null;
  writeJson('settings.json', { ...settings(), dataDir: r.filePaths[0] });
  startApi().catch((e) => setApi('failed', e.message));
  return r.filePaths[0];
});
handle('open:data', () => shell.openPath(settings().dataDir || path.join(ROOT, 'data')));

app.whenReady().then(() => { createWindow(); startApi().catch((e) => setApi('failed', e.message)); });
app.on('window-all-closed', () => app.quit());
app.on('before-quit', () => { stopApi(); if (indexing) indexing.proc.kill(); });
