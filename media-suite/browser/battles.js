'use strict';
(() => {
  const parentOrigin = document.currentScript.dataset.parent;
  const root = () => document.getElementById('nai-media-host')?.shadowRoot;
  // The same component runs in Library and Battles, inside its own shadow root.
  const managed = new CSSStyleSheet();
  managed.replaceSync('#naiUpdateStatus{display:none!important}');
  function hideUpdateControls() {
    const library = root();
    if (library && !library.adoptedStyleSheets.includes(managed))
      library.adoptedStyleSheets = [...library.adoptedStyleSheets, managed];
  }
  hideUpdateControls();
  new MutationObserver(hideUpdateControls).observe(document.documentElement, {childList:true, subtree:true});
  let timer;
  window.addEventListener('message', event => {
    if (event.source !== parent || event.origin !== parentOrigin) return;
    if (event.data?.type === 'suite-owner') {
      event.ports[0]?.postMessage(root()?.getElementById('characterSelect')?.value || null);
      return;
    }
    if (event.data?.type !== 'suite-battles') return;
    const owner = event.data.owner;
    clearInterval(timer);
    let attempts = 0;
    timer = setInterval(() => {
      const library = root(), select = library?.getElementById('characterSelect');
      if (!library?.naiOpenBattles || !select?.options.length) { if (++attempts >= 240) clearInterval(timer); return; }
      clearInterval(timer);
      if (library.querySelector('.naiBattleWrap')) return;
      if (owner && select.value !== owner && Array.from(select.options).some(o => o.value === owner)) {
        select.value = owner; select.dispatchEvent(new Event('change', {bubbles: true}));
      }
      if (select.value) { library.naiOpenBattles(); return; }
      if (select.dataset.suiteChoice) return;
      select.dataset.suiteChoice = '1'; select.focus();
      select.addEventListener('change', function choose() {
        if (!select.value) return;
        delete select.dataset.suiteChoice; select.removeEventListener('change', choose); library.naiOpenBattles();
      });
    }, 125);
  });
})();
