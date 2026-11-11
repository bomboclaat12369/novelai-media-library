'use strict';
const byId = id => document.getElementById(id);
const pages = new Map();
const dialog = byId('settings');
let token, selected, remember = Promise.resolve();

async function session() {
  const response = await fetch('/api/session', {headers: {'X-Suite-Request': 'session'}});
  if (!response.ok) throw Error('Could not connect to the Media Suite launcher.');
  const data = await response.json();
  if (token && data.token !== token) {
    location.reload();
    throw Error('Reopening Media Suite after the launcher update.');
  }
  token = data.token;
  return data;
}
async function request(path, data) {
  const options = {method: 'POST', headers: {'X-Suite-Request': token}};
  if (data !== undefined) {
    options.headers['Content-Type'] = 'application/json';
    options.body = JSON.stringify(data);
  }
  const response = await fetch('/api/' + path, options);
  if (response.status === 403) await session();
  if (!response.ok) {
    const message = await response.json().catch(() => ({}));
    throw Error(message.error || 'The program could not connect. Check Locations and retry.');
  }
  if (response.status !== 204) return response.json();
}

function openBattles() {
  const battle = pages.get('Battles'), library = pages.get('Library');
  if (selected !== 'Battles' || !battle.loaded) return;
  function send(owner) {
    if (selected === 'Battles' && battle.loaded)
      battle.frame.contentWindow.postMessage({type: 'suite-battles', owner}, battle.origin);
  }
  if (!library.loaded) { send(null); return; }
  const channel = new MessageChannel();
  const timer = setTimeout(() => { channel.port1.close(); send(null); }, 750);
  channel.port1.onmessage = event => {
    clearTimeout(timer); channel.port1.close();
    send(typeof event.data === 'string' ? event.data : null);
  };
  library.frame.contentWindow.postMessage({type: 'suite-owner'}, library.origin, [channel.port2]);
}

async function connect(page) {
  if (page.busy) return;
  const attempt = Symbol();
  page.busy = attempt; page.loaded = false; page.retry.hidden = true;
  page.feedback.hidden = false; page.message.textContent = 'Opening ' + page.button.textContent + '…';
  try {
    const {url} = await request('open/' + page.button.id);
    if (page.busy !== attempt) return;
    page.origin = new URL(url).origin;
    const frame = document.createElement('iframe');
    frame.title = page.button.textContent;
    frame.name = 'suite-' + page.button.id;
    frame.referrerPolicy = 'origin';
    frame.allow = 'fullscreen; autoplay; clipboard-write';
    frame.setAttribute('allowfullscreen', '');
    frame.setAttribute('sandbox', 'allow-scripts allow-same-origin allow-forms allow-downloads allow-modals allow-popups allow-popups-to-escape-sandbox');
    frame.hidden = true;
    frame.addEventListener('load', () => {
      if (page.frame !== frame) return;
      page.loaded = true; page.feedback.hidden = true; frame.hidden = false;
      if (page.button.id === 'Battles') openBattles();
    });
    frame.src = url;
    page.frame?.remove(); page.frame = frame; page.panel.append(frame);
  } catch (error) {
    if (page.busy !== attempt) return;
    page.message.textContent = error.message; page.retry.hidden = false;
  } finally { if (page.busy === attempt) page.busy = false; }
}
function select(id) {
  const page = pages.get(id);
  selected = id;
  for (const other of pages.values()) {
    const active = page === other;
    other.button.setAttribute('aria-selected', String(active)); other.button.tabIndex = active ? 0 : -1;
    other.panel.hidden = !active;
  }
  remember = remember.catch(() => {}).then(() => request('select/' + id)).catch(error => {
    page.message.textContent = error.message; page.feedback.hidden = false;
  });
  if (!page.frame) connect(page);
  else if (id === 'Battles') openBattles();
}

for (const button of document.querySelectorAll('[role=tab]')) {
  const panel = document.createElement('section');
  panel.id = 'panel-' + button.id; panel.hidden = true;
  panel.setAttribute('role', 'tabpanel'); panel.setAttribute('aria-labelledby', button.id);
  button.setAttribute('aria-controls', panel.id);
  const feedback = document.createElement('div'), message = document.createElement('p'), retry = document.createElement('button');
  feedback.className = 'feedback'; message.setAttribute('role','status'); retry.textContent = 'Retry'; retry.hidden = true;
  const page = {button, panel, feedback, message, retry};
  retry.onclick = () => connect(page);
  feedback.append(message, retry); panel.append(feedback);
  document.querySelector('main').append(panel); pages.set(button.id, page);
  button.onclick = () => select(button.id);
  button.onkeydown = event => {
    const ids = Array.from(pages.keys()), index = ids.indexOf(button.id);
    const next = {ArrowLeft: (index + 3) % 4, ArrowRight: (index + 1) % 4, Home: 0, End: 3}[event.key];
    if (next !== undefined) { event.preventDefault(); byId(ids[next]).focus(); select(ids[next]); }
  };
}

const fields = Array.from(dialog.querySelectorAll('input'));
byId('locations').onclick = async () => {
  byId('settings-error').textContent = '';
  try {
    const current = await session();
    for (const field of fields) field.value = current.locations[field.id] || '';
    dialog.showModal();
  } catch (error) { dialog.showModal(); byId('settings-error').textContent = error.message; }
};
for (const button of dialog.querySelectorAll('[data-for]')) button.onclick = async () => {
  const input = byId(button.dataset.for);
  button.disabled = true;
  try { const result = await request('browse', input.value); if (result.path) input.value = result.path; }
  catch (error) { byId('settings-error').textContent = error.message; }
  finally { button.disabled = false; }
};
byId('cancel').onclick = () => dialog.close();
dialog.querySelector('form').onsubmit = async event => {
  event.preventDefault();
  try {
    const result = await request('locations', Object.fromEntries(fields.map(field => [field.id, field.value])));
    for (const id of result.changed) {
      const affected = pages.get(id);
      affected.frame?.remove(); affected.frame = null; affected.loaded = false; affected.busy = false;
    }
    dialog.close(); const page = pages.get(selected); if (!page.loaded) connect(page);
  } catch (error) { byId('settings-error').textContent = error.message; }
};
let checking = false;
document.addEventListener('visibilitychange', () => {
  if (!document.hidden && token) session().catch(() => {});
});
setInterval(async () => {
  const page = pages.get('Workbench');
  if (selected !== 'Workbench' || !page.loaded || checking || document.hidden) return;
  checking = true;
  try { if ((await request('workbench-changed')).changed) await connect(page); }
  catch { /* Recheck after the service or browser resumes. */ }
  finally { checking = false; }
}, 2500);
session().then(data => select(pages.has(data.lastSection) ? data.lastSection : 'Library')).catch(error => {
  const first = pages.get('Library'); first.panel.hidden = false; first.message.textContent = error.message;
  first.retry.hidden = false; first.retry.onclick = () => location.reload();
});
