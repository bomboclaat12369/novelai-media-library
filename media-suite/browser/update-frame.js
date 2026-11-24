'use strict';
(() => {
  const {parent: parentOrigin, mode} = document.currentScript.dataset;
  const root = () => document.getElementById('nai-media-host')?.shadowRoot;
  const visible = element => element.getClientRects().length > 0 && getComputedStyle(element).visibility !== 'hidden';
  const openEditor = container => container && Array.from(container.querySelectorAll(
    'dialog[open], .modalWrap, .naiMatchWrap, .naiWorkflowOverlay, .naiCollectionOverlay, .naiSetQueueWrap270, ' +
    '[role="dialog"]:not(.naiBattleWrap), [aria-modal="true"]:not(.naiBattleWrap), [aria-busy="true"], input[type=file]'
  )).some(element => element.type === 'file' ? element.files?.length : element.open || visible(element));

  async function prepare(plan) {
    if (mode === 'Library') {
      const interfaceChanged = Boolean(plan.libraryVersion && plan.libraryVersion !== document.documentElement.dataset.naiMediaPayloadVersion);
      const reload = plan.launcher || plan.companion || interfaceChanged;
      if (!reload) return {reload: false};
      const library = root();
      if (!library) throw Error('Media Library is still opening. Try the update again in a moment.');
      if (openEditor(library) || library.querySelector('.naiBattleWrap input[type=range]:focus'))
        throw Error('Finish or close the open Library or Battles review, then press Update Media Suite again.');
      return {reload, interfaceChanged, owner: library.getElementById('characterSelect')?.value};
    }
    if (mode === 'Workbench') {
      const reload = plan.launcher || plan.workbench;
      if (!reload && !plan.companion) return {reload: false};
      if ((typeof busy !== 'undefined' && busy) || openEditor(document))
        throw Error('Finish or close the open Workbench review or import, then press Update Media Suite again.');
      if (!reload) return {reload: false};
      if (location.pathname !== '/organizer')
        throw Error('Finish the current Workbench review and return to the organizer, then press Update Media Suite again.');
      if (typeof sessionReady === 'undefined' || !sessionReady || typeof saveDraft !== 'function')
        throw Error('Workbench is still opening. Try the update again in a moment.');
      if (data?.job) { await saveDraft(); await saveSession(); }
      return {reload};
    }
    if (!plan.launcher && !plan.game) return {reload: false};
    if (typeof actionQueue !== 'undefined') await actionQueue;
    if (typeof save === 'undefined' || openEditor(root()) || (typeof busy !== 'undefined' && busy) ||
        (save?.phase === 'night' && !save.night.paused) || (!save && typeof selected !== 'undefined' && selected.size))
      throw Error('Pause the After Hours night or finish the open decision, then press Update Media Suite again.');
    return {reload: true};
  }

  // Only the suite that embedded this page can prepare it or restore its owner.
  window.addEventListener('message', async event => {
    if (event.source !== parent || event.origin !== parentOrigin) return;
    const port = event.ports[0];
    if (!port) return;
    try {
      if (event.data?.type === 'suite-prepare-update') port.postMessage(await prepare(event.data.plan));
      if (event.data?.type === 'suite-restore-owner' && mode === 'Library') {
        const owner = event.data.owner;
        for (let i = 0; i < 120; i++) {
          const input = root()?.getElementById('characterSelect');
          if (input?.options.length && Array.from(input.options).some(o => o.value === owner)) {
            if (input.value !== owner) { input.value = owner; input.dispatchEvent(new Event('change', {bubbles:true})); }
            break;
          }
          await new Promise(resolve => setTimeout(resolve, 125));
        }
        port.postMessage({});
      }
    } catch (error) { port.postMessage({reason: error.message || 'The program could not save your place. Try again.'}); }
    finally { port.close(); }
  });
})();
