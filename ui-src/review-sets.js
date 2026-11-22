// Shared destination for Library actions that confirm shoot membership.
(() => {
  const root = document.getElementById('nai-media-host')?.shadowRoot;
  if (!root) return;
  root.naiSetDestination = (held = false) => {
    const select = document.createElement('select');
    select.className = 'naiSetDestination';
    select.setAttribute('aria-label', 'Set destination');
    for (const [value, text] of [['regular', 'Regular Set'], ['under_review', 'Set under review']]) {
      const option = document.createElement('option');
      option.value = value;
      option.textContent = text;
      select.append(option);
    }
    select.value = held ? 'under_review' : 'regular';
    return select;
  };
})();
