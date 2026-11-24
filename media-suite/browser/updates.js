'use strict';
const tabId = crypto.randomUUID();
const updateDialog = byId('update-dialog'), installButton = byId('check-updates'), statusLine = byId('update-message');
const resumeKey = 'media-suite-update-return';
let updateTimer, reconnectTimer, tabPreparation, requested = false, lastRun;

function connectPresence() {
  presence = new EventSource('/api/presence?tab=' + tabId);
  presence.addEventListener('suite-update', event => handleUpdate(JSON.parse(event.data)));
  presence.onerror = () => { if (tabPreparation?.plan.launcher) watchLauncher(); };
}

function frameMessage(page, message) {
  return new Promise((resolve, reject) => {
    const channel = new MessageChannel();
    const timer = setTimeout(() => {
      channel.port1.close();
      reject(Error(page.button.textContent + ' is still busy. Try the update again in a moment.'));
    }, 18000);
    channel.port1.onmessage = event => {
      clearTimeout(timer); channel.port1.close();
      if (event.data.reason) reject(Error(event.data.reason));
      else resolve(event.data);
    };
    page.frame.contentWindow.postMessage(message, page.origin, [channel.port2]);
  });
}

function watchLauncher() {
  if (reconnectTimer || !tabPreparation?.plan.launcher) return;
  async function poll() {
    if (!tabPreparation?.plan.launcher) { reconnectTimer = null; return; }
    // session() reloads this exact tab only after the replacement is listening.
    try { await session(); } catch { }
    reconnectTimer = setTimeout(poll, 650);
  }
  reconnectTimer = setTimeout(poll, 250);
}

function rememberReturn(work) {
  sessionStorage.setItem(resumeKey, JSON.stringify({
    token, mode:selected, show:requested, owners:Object.fromEntries(Array.from(work.reload, ([id, result]) => [id, result.owner]))
  }));
}

function restoreUpdatedTab(data) {
  let saved;
  try { saved = JSON.parse(sessionStorage.getItem(resumeKey)); } catch { }
  sessionStorage.removeItem(resumeKey);
  if (!saved || saved.token === data.token || !pages.has(saved.mode)) return;
  for (const [id, owner] of Object.entries(saved.owners || {})) {
    if (owner && pages.has(id)) pages.get(id).restoreOwner = owner;
  }
  if (saved.show) {
    statusLine.textContent = 'Media Suite ' + data.version + ' is running in this tab.';
    updateDialog.showModal();
    showUpdates();
  }
  return saved.mode;
}

function lockTab(locked) {
  document.querySelector('main').inert = locked;
  modeToggle.disabled = locked;
}

async function prepareTab(state) {
  const work = {id:state.id, plan:state.plan, reload:new Map()};
  tabPreparation = work;
  lockTab(true);
  if (picker.open) picker.close();
  let reason;
  try {
    if (dialog.open) throw Error('Finish editing Suite locations, then press Update Media Suite again.');
    await remember;
    const replies = await Promise.allSettled(Array.from(pages, async ([id, page]) => {
      const plan = state.plan;
      const relevant = plan.launcher || (id === 'Workbench' ? plan.workbench || plan.companion
        : id === 'AfterHours' ? plan.game : plan.companion || plan.libraryVersion);
      if (!relevant) return;
      if (page.busy || (page.frame && !page.loaded)) throw Error(page.button.textContent + ' is still opening. Try the update again in a moment.');
      if (!page.frame) return;
      const result = await frameMessage(page, {type:'suite-prepare-update', plan});
      if (result.reload) work.reload.set(id, result);
    }));
    const failed = replies.find(reply => reply.status === 'rejected');
    if (failed) throw failed.reason;
    if (tabPreparation !== work) return;
    if (state.plan.launcher) { rememberReturn(work); watchLauncher(); }
  } catch (error) { reason = error.message; }
  if (tabPreparation !== work) return;
  try { await request('updates/respond', {tab:tabId, id:state.id, reason}); }
  catch { if (state.plan.launcher) watchLauncher(); }
}

function finishTab(state) {
  const work = tabPreparation;
  tabPreparation = null;
  clearTimeout(reconnectTimer); reconnectTimer = null;
  sessionStorage.removeItem(resumeKey);
  lockTab(false);
  // Keep the original documents mounted until every tab has agreed and the
  // backend has finished. A refusal in another profile loses no selections.
  if (work && state.phase === 'done') {
    for (const [id, result] of work.reload) {
      const changed = id === 'Workbench' ? state.plan.workbench : id === 'AfterHours' ? state.plan.game
        : state.plan.companion || result.interfaceChanged;
      if (!changed) continue;
      const page = pages.get(id);
      page.restoreOwner = result.owner;
      page.frame?.remove(); page.frame = null; page.busy = false; page.loaded = false;
    }
    const page = pages.get(selected);
    if (page && !page.frame) connect(page);
  }
  requested = false;
}

function handleUpdate(state) {
  if (!state?.id || (lastRun?.id === state.id && lastRun.phase === state.phase)) return;
  lastRun = state;
  statusLine.textContent = state.message;
  const active = ['checking','preparing','applying','restarting'].includes(state.phase);
  installButton.disabled = active;
  if (state.phase === 'preparing') prepareTab(state);
  else if (state.phase === 'restarting') watchLauncher();
  else if (!active) {
    finishTab(state);
    if (updateDialog.open) showUpdates();
  }
}

function showPrograms(apps) {
  byId('update-list').replaceChildren(...Object.entries(apps).flatMap(([name, status]) => {
    const label = document.createElement('dt'), value = document.createElement('dd');
    label.textContent = name; value.textContent = status;
    return [label, value];
  }));
}

async function showUpdates() {
  clearTimeout(updateTimer);
  try {
    const state = await request('updates');
    if (!updateDialog.open) return;
    showPrograms(state.apps);
    // Presence delivers phase transitions in order. Poll only the program list.
    if (state.checking || tabPreparation || requested) updateTimer = setTimeout(showUpdates, 1250);
  } catch (error) { if (!tabPreparation) statusLine.textContent = error.message; }
}
byId('updates').onclick = () => { picker.close(); updateDialog.showModal(); showUpdates(); };
installButton.onclick = async () => {
  installButton.disabled = true; requested = true;
  try { const state = await request('updates/install', {tab:tabId}); showPrograms(state.apps); showUpdates(); }
  catch (error) { requested = false; installButton.disabled = false; statusLine.textContent = error.message; }
};
byId('close-updates').onclick = () => updateDialog.close();
updateDialog.onclose = () => { clearTimeout(updateTimer); modeToggle.focus(); };
