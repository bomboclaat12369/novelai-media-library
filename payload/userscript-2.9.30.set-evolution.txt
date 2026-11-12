// Standalone Set curation. Only an explicit save sends a change to the companion.
(() => {
  'use strict';
  const root = document.getElementById('nai-media-host')?.shadowRoot;
  if (!root) return;
  const make = (tag, text) => {
    const node = document.createElement(tag);
    if (text !== undefined) node.textContent = text;
    return node;
  };
  function button(label, action) {
    const node = make('button', label);
    node.type = 'button';
    node.onclick = action;
    return node;
  }
  const style = make('style');
  style.textContent = `
    .naiEvolution .naiCollectionInner{width:min(960px,96vw);box-sizing:border-box}
    .naiEvolution h3{margin:16px 0 8px}
    .naiEvolutionForms,.naiEvolutionPreview{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(145px,100%),1fr));gap:12px}
    .naiEvolutionForms article,.naiEvolutionPreview article{min-width:0;display:flex;flex-direction:column;gap:6px}
    .naiEvolutionForms article[draggable=true]{cursor:grab}
    .naiEvolutionForms article[data-drop-target]{outline:2px solid #a89de6;outline-offset:3px}
    .naiEvolutionForms img{width:100%;height:110px;object-fit:contain;background:#101525;border-radius:6px}
    .naiEvolutionForms small,.naiEvolutionPicker span{overflow-wrap:anywhere}
    .naiEvolutionActions{display:flex;align-items:center;flex-wrap:wrap;gap:6px;margin:8px 0}
    .naiEvolutionPicker{display:grid;grid-template-columns:repeat(auto-fill,minmax(95px,1fr));gap:7px}
    .naiEvolutionPicker button{display:grid;grid-template-rows:75px auto;gap:4px;align-items:center;text-align:center;min-width:0}
    .naiEvolutionPicker img{width:100%;height:75px;object-fit:contain}
    .naiEvolutionPreview .naiTradingCard{width:100%;aspect-ratio:3/4}
    .naiEvolution .naiEvolutionState{display:block;margin:4px 0;font-weight:600}
  `;
  root.append(style);

  function previewForms(ids, photos, owner, request) {
    const urls = [];
    const cards = root.naiCards;
    const dialog = cards.modal('Evolution preview', () => urls.forEach(url => URL.revokeObjectURL(url)));
    dialog.wrap.classList.add('naiEvolution');
    dialog.body.className = 'naiEvolutionPreview';
    ids.forEach(async (id, index) => {
      const item = photos.get(id);
      const tile = make('article');
      tile.append(make('strong', index === ids.length - 1 ? 'Final form' : 'Form ' + (index + 1)));
      dialog.body.append(tile);
      if (!item) { tile.append(make('p', 'Photo unavailable')); return; }
      const image = make('img');
      image.alt = item.original_name || 'Set photo';
      const entry = {id, images:[id], count:1, name:image.alt, tier:'Unranked', titles:[]};
      const card = cards.lightCard(entry, [entry], owner.id, image, false, id);
      tile.append(card);
      cards.applyFrame(image, owner.collection?.frames?.['image:' + id]);
      try {
        const blob = await request({path:'/api/media/' + encodeURIComponent(id) + '/original', responseType:'blob'});
        if (!tile.isConnected) return;
        const url = URL.createObjectURL(blob);
        urls.push(url);
        image.src = url;
      } catch (_) {
        if (tile.isConnected) tile.append(make('p', 'Original photo unavailable'));
      }
    });
  }

  root.naiEditSetEvolution = function(group, library, request, onSave) {
    const owner = library.characters.find(character => character.id === group.character_id);
    if (!owner || (group.kind || 'set') !== 'set' || root.naiViewerOnly) return;
    const expected = group.after_hours_evolution ?? null;
    const dialog = root.naiCards.modal('After Hours evolution · ' + group.name);
    dialog.wrap.classList.add('naiEvolution');
    if (Number.isInteger(expected?.version) && expected.version > 1) {
      dialog.error.textContent = 'Update the Library to edit this evolution format.';
      return;
    }
    const members = new Set(group.media_ids || []);
    const photos = new Map(library.media.filter(item =>
      members.has(item.id) && item.character_id === owner.id && (item.media_type || 'image') === 'image'
      && !item.in_review && !item.in_purgatory && !item.flagged_for_removal
    ).map(item => [item.id, item]));
    const captain = owner.collection?.captain_schema === 2 && owner.collection.captains?.[group.id];
    // An existing candidate, including an explicitly empty one, keeps Walker's choices.
    const savedIds = Array.isArray(expected?.media_ids) ? expected.media_ids.filter(id => typeof id === 'string') : [];
    const ids = expected ? [...savedIds] : (photos.has(captain) ? [captain] : []);
    let replacing = null, page = 0, edited = false, dragged = null;
    const pageSize = 24;
    const state = make('span');
    state.className = 'naiEvolutionState';
    const forms = make('div');
    forms.className = 'naiEvolutionForms';
    const actions = make('div');
    actions.className = 'naiEvolutionActions';
    const pickerTitle = make('h3');
    const search = make('input');
    search.type = 'search';
    search.placeholder = 'Find a Set photo';
    search.setAttribute('aria-label', search.placeholder);
    const picker = make('div');
    picker.className = 'naiEvolutionPicker';
    const paging = make('div');
    paging.className = 'naiEvolutionActions';
    dialog.body.append(state, forms, actions, pickerTitle, search, picker, paging);

    async function save(status) {
      const evolution = status ? {version:1, status, media_ids:[...ids]} : null;
      let saved;
      await dialog.run(async () => {
        saved = await request({method:'POST', path:'/api/sets/' + encodeURIComponent(group.id) + '/evolution',
          headers:{'Content-Type':'application/json'}, data:JSON.stringify({expected, evolution})});
      });
      if (!saved) { render(); return; }
      dialog.close();
      try { await onSave(saved); }
      catch (error) { alert('Sequence saved. Refresh the Library to see it. ' + error.message); }
    }
    function changed() {
      edited = true;
      replacing = null;
      dialog.error.textContent = '';
      render();
    }
    function choose(id) {
      if (replacing !== null) {
        const old = ids.indexOf(id);
        if (old !== -1) ids[old] = ids[replacing];
        ids[replacing] = id;
      } else if (!ids.includes(id) && ids.length < 4) {
        // Keep the finale in its place as earlier forms are added.
        ids.splice(Math.max(0, ids.length - 1), 0, id);
      } else return;
      changed();
    }
    function move(index, to) {
      if (index < 0 || to < 0 || to >= ids.length || index === to) return;
      ids.splice(to, 0, ids.splice(index, 1)[0]);
      changed();
    }
    function renderPicker() {
      const query = search.value.trim().toLowerCase();
      const matches = [...photos.values()].filter(item => (item.original_name || item.id).toLowerCase().includes(query));
      const pages = Math.max(1, Math.ceil(matches.length / pageSize));
      page = Math.min(page, pages - 1);
      picker.replaceChildren();
      for (const item of matches.slice(page * pageSize, (page + 1) * pageSize)) {
        const name = item.original_name || item.id;
        const choice = button('', () => choose(item.id));
        choice.dataset.photoId = item.id;
        choice.setAttribute('aria-label', 'Choose ' + name);
        choice.disabled = replacing === null ? ids.includes(item.id) || ids.length >= 4 : ids[replacing] === item.id;
        const image = make('img');
        image.alt = '';
        choice.append(image, make('span', name));
        picker.append(choice);
        root.naiLoadThumbnail(item.id, image);
      }
      if (!matches.length) picker.textContent = 'No eligible photos match.';
      paging.replaceChildren();
      if (pages > 1) {
        const prev = button('Previous', () => { page--; renderPicker(); });
        const next = button('Next', () => { page++; renderPicker(); });
        prev.disabled = page === 0;
        next.disabled = page === pages - 1;
        paging.append(prev, make('span', (page + 1) + ' of ' + pages), next);
      }
    }
    function render() {
      state.textContent = edited ? 'Unsaved changes' : expected?.status === 'ready' ? 'Ready for After Hours'
        : expected ? 'Candidate' : 'New candidate';
      forms.replaceChildren();
      ids.forEach((id, index) => {
        const tile = make('article');
        tile.dataset.formId = id;
        tile.draggable = true;
        tile.ondragstart = event => {
          if (event.target.closest('button')) { event.preventDefault(); return; }
          dragged = id;
          event.dataTransfer.setData('application/x-nai-evolution-form', id);
          event.dataTransfer.effectAllowed = 'move';
        };
        tile.ondragover = event => {
          if (dragged === null || dragged === id) return;
          event.preventDefault();
          event.dataTransfer.dropEffect = 'move';
          tile.dataset.dropTarget = '';
        };
        tile.ondragleave = () => { delete tile.dataset.dropTarget; };
        tile.ondrop = event => {
          if (dragged === null) return;
          event.preventDefault();
          const from = ids.indexOf(dragged);
          dragged = null;
          move(from, index);
        };
        tile.ondragend = () => {
          dragged = null;
          forms.querySelectorAll('[data-drop-target]').forEach(node => { delete node.dataset.dropTarget; });
        };
        const final = index === ids.length - 1;
        tile.append(make('strong', 'Form ' + (index + 1) + (final ? ' · Final form' : '')));
        const item = photos.get(id);
        const image = make('img');
        image.draggable = false;
        image.alt = item?.original_name || 'Photo unavailable';
        const controls = make('div');
        controls.className = 'naiEvolutionActions';
        const earlier = button('←', () => move(index, index - 1));
        const later = button('→', () => move(index, index + 1));
        earlier.setAttribute('aria-label', 'Move form ' + (index + 1) + ' earlier');
        later.setAttribute('aria-label', 'Move form ' + (index + 1) + ' later');
        earlier.disabled = index === 0;
        later.disabled = final;
        controls.append(earlier, later, button('Change', () => { replacing = index; render(); search.focus(); }),
          button('Remove', () => { ids.splice(index, 1); changed(); }));
        tile.append(image, make('small', item?.original_name || 'Photo unavailable'), controls);
        forms.append(tile);
        if (item) root.naiLoadThumbnail(id, image);
      });
      actions.replaceChildren();
      const valid = new Set(ids).size === ids.length && ids.every(id => photos.has(id));
      const preview = button('Preview forms', () => previewForms(ids, photos, owner, request));
      preview.disabled = !ids.length;
      const candidate = button('Save candidate', () => save('candidate'));
      candidate.disabled = !valid || ids.length > 4;
      const ready = button('Mark ready', () => save('ready'));
      ready.disabled = !valid || ![3,4].includes(ids.length) || !!group.in_purgatory;
      actions.append(preview, candidate, ready);
      if (expected) actions.append(button('Unflag Set', () => save(null)));
      if (replacing !== null) {
        pickerTitle.textContent = replacing === ids.length - 1 ? 'Choose a new final photo' : 'Replace form ' + (replacing + 1);
        actions.append(button('Cancel replacement', () => { replacing = null; render(); }));
      } else {
        pickerTitle.textContent = !ids.length ? 'Choose the final photo' : ids.length < 4 ? 'Add an earlier form' : 'Set photos';
      }
      renderPicker();
    }
    search.oninput = () => { page = 0; renderPicker(); };
    render();
  };
})();
