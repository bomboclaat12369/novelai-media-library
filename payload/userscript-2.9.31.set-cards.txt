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
    .naiDuoSides{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}
    .naiDuoSides button{display:grid;grid-template-columns:minmax(40px,74px) minmax(0,1fr);grid-template-rows:auto auto;column-gap:10px;align-items:center;text-align:left;min-height:90px}
    .naiDuoSides button[aria-pressed=true]{outline:2px solid #ae9ff1;outline-offset:-2px}
    .naiDuoSides img{grid-row:1/3;width:100%;height:72px;object-fit:contain}
    .naiDuoSides strong,.naiDuoSides small{grid-column:2;overflow-wrap:anywhere}
    .naiDuoSides strong{align-self:end}.naiDuoSides small{align-self:start}
    .naiDuoPreview{display:grid;justify-items:center;gap:12px;perspective:1200px}
    .naiDuoTurn{position:relative;width:min(286px,80vw);aspect-ratio:3/4;transform-style:preserve-3d;transition:transform .36s ease-in-out}
    .naiDuoTurn[data-side=back]{transform:rotateY(180deg)}
    .naiDuoFace{position:absolute;inset:0;backface-visibility:hidden}
    .naiDuoFace:nth-child(2){transform:rotateY(180deg)}
    .naiDuoFace .naiTradingCard{width:100%;height:100%;aspect-ratio:3/4}
    .naiDuoFace p{position:absolute;inset:38% 0 auto;text-align:center;background:#151a29}
    @media(prefers-reduced-motion:reduce){.naiDuoTurn{transition:none}}
    @media(max-width:520px){.naiDuoSides button{display:flex;flex-direction:column;align-items:stretch}.naiDuoSides strong,.naiDuoSides small{align-self:auto}}
  `;
  root.append(style);

  function setPhotos(group, library) {
    const members = new Set(group.media_ids || []);
    return new Map(library.media.filter(item =>
      members.has(item.id) && item.character_id === group.character_id && (item.media_type || 'image') === 'image'
      && !item.in_review && !item.in_purgatory && !item.flagged_for_removal
    ).map(item => [item.id, item]));
  }

  async function showOriginal(tile, item, owner, request, urls) {
    if (!item) { tile.append(make('p', 'Photo unavailable')); return; }
    const image = make('img');
    image.alt = item.original_name || 'Set photo';
    const id = item.id;
    const entry = {id, images:[id], count:1, name:image.alt, tier:'Unranked', titles:[]};
    tile.append(root.naiCards.lightCard(entry, [entry], owner.id, image, false, id));
    root.naiCards.applyFrame(image, owner.collection?.frames?.['image:' + id]);
    try {
      const blob = await request({path:'/api/media/' + encodeURIComponent(id) + '/original', responseType:'blob'});
      if (!tile.isConnected) return;
      const url = URL.createObjectURL(blob);
      urls.push(url);
      image.src = url;
    } catch (_) {
      if (tile.isConnected) tile.append(make('p', 'Original photo unavailable'));
    }
  }

  function previewForms(ids, photos, owner, request) {
    const urls = [];
    const cards = root.naiCards;
    const dialog = cards.modal('Evolution preview', () => urls.forEach(url => URL.revokeObjectURL(url)));
    dialog.wrap.classList.add('naiEvolution');
    dialog.body.className = 'naiEvolutionPreview';
    ids.forEach((id, index) => {
      const tile = make('article');
      tile.append(make('strong', index === ids.length - 1 ? 'Final form' : 'Form ' + (index + 1)));
      dialog.body.append(tile);
      showOriginal(tile, photos.get(id), owner, request, urls);
    });
  }

  function photoPicker(photos, choose, disabled) {
    const search = make('input');
    search.type = 'search';
    search.placeholder = 'Find a Set photo';
    search.setAttribute('aria-label', search.placeholder);
    const picker = make('div');
    picker.className = 'naiEvolutionPicker';
    const paging = make('div');
    paging.className = 'naiEvolutionActions';
    let page = 0;
    function render() {
      const query = search.value.trim().toLowerCase();
      const matches = [...photos.values()].filter(item => (item.original_name || item.id).toLowerCase().includes(query));
      const pages = Math.max(1, Math.ceil(matches.length / 24));
      page = Math.min(page, pages - 1);
      picker.replaceChildren();
      for (const item of matches.slice(page * 24, (page + 1) * 24)) {
        const name = item.original_name || item.id;
        const choice = button('', () => choose(item.id));
        choice.dataset.photoId = item.id;
        choice.setAttribute('aria-label', 'Choose ' + name);
        choice.disabled = disabled(item.id);
        const image = make('img');
        image.alt = '';
        choice.append(image, make('span', name));
        picker.append(choice);
        root.naiLoadThumbnail(item.id, image);
      }
      if (!matches.length) picker.textContent = 'No eligible photos match.';
      paging.replaceChildren();
      if (pages > 1) {
        const prev = button('Previous', () => { page--; render(); });
        const next = button('Next', () => { page++; render(); });
        prev.disabled = page === 0;
        next.disabled = page === pages - 1;
        paging.append(prev, make('span', (page + 1) + ' of ' + pages), next);
      }
    }
    search.oninput = () => { page = 0; render(); };
    return {nodes:[search, picker, paging], render, focusSearch:() => search.focus()};
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
    const photos = setPhotos(group, library);
    const captain = owner.collection?.captain_schema === 2 && owner.collection.captains?.[group.id];
    // An existing candidate, including an explicitly empty one, keeps Walker's choices.
    const savedIds = Array.isArray(expected?.media_ids) ? expected.media_ids.filter(id => typeof id === 'string') : [];
    const ids = expected ? [...savedIds] : (photos.has(captain) ? [captain] : []);
    let replacing = null, edited = false, dragged = null;
    const state = make('span');
    state.className = 'naiEvolutionState';
    const forms = make('div');
    forms.className = 'naiEvolutionForms';
    const actions = make('div');
    actions.className = 'naiEvolutionActions';
    const pickerTitle = make('h3');
    const picker = photoPicker(photos, choose, id => replacing === null
      ? ids.includes(id) || ids.length >= 4 : ids[replacing] === id);
    dialog.body.append(state, forms, actions, pickerTitle, ...picker.nodes);

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
        controls.append(earlier, later, button('Change', () => { replacing = index; render(); picker.focusSearch(); }),
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
      picker.render();
    }
    render();
  };

  const sides = ['Front', 'Back'];
  function previewDuo(ids, photos, owner, request) {
    const urls = [];
    const dialog = root.naiCards.modal('Duo preview', () => urls.forEach(url => URL.revokeObjectURL(url)));
    dialog.wrap.classList.add('naiEvolution');
    dialog.body.className = 'naiDuoPreview';
    const label = make('strong');
    label.setAttribute('aria-live', 'polite');
    const turn = make('div');
    turn.className = 'naiDuoTurn';
    let side = 0;
    const flip = button('', () => { side = 1 - side; display(); });
    dialog.body.append(label, turn, flip);
    const faces = ids.map(id => {
      const face = make('div');
      face.className = 'naiDuoFace';
      turn.append(face);
      showOriginal(face, photos.get(id), owner, request, urls);
      return face;
    });
    function display() {
      label.textContent = sides[side] + ' · ' + (photos.get(ids[side]).original_name || 'Set photo');
      turn.dataset.side = sides[side].toLowerCase();
      faces.forEach((face, index) => face.setAttribute('aria-hidden', String(index !== side)));
      flip.textContent = 'Flip to ' + sides[1 - side].toLowerCase();
    }
    display();
    flip.focus();
  }

  root.naiEditSetDuo = function(group, library, request, onSave) {
    const owner = library.characters.find(character => character.id === group.character_id);
    if (!owner || (group.kind || 'set') !== 'set' || root.naiViewerOnly) return;
    const expected = group.after_hours_duo ?? null;
    const dialog = root.naiCards.modal('Duo · ' + group.name);
    dialog.wrap.classList.add('naiEvolution', 'naiDuoEditor');
    if (expected !== null && expected.version !== 1) {
      dialog.error.textContent = 'Update the Library to edit this Duo format.';
      return;
    }
    const photos = setPhotos(group, library);
    const ids = sides.map((_, i) => expected?.media_ids?.[i] || null);
    let side = 0;
    const slots = make('div');
    slots.className = 'naiDuoSides';
    const slotButtons = sides.map((name, i) => {
      const slot = button('', () => { side = i; render(); });
      slot.setAttribute('aria-label', 'Choose ' + name.toLowerCase() + ' photo');
      slots.append(slot);
      return slot;
    });
    const actions = make('div');
    actions.className = 'naiEvolutionActions';
    const swap = button('Swap sides', () => { ids.reverse(); render(); });
    const preview = button('Preview flip', () => previewDuo(ids, photos, owner, request));
    const save = button('Save Duo', () => persist({version:1, media_ids:[...ids]}));
    actions.append(swap, preview, save);
    if (expected !== null) {
      actions.append(button('Remove Duo', () => {
        if (confirm('Remove this Duo from the Set?')) persist(null);
      }));
    }
    const heading = make('h3');
    heading.setAttribute('aria-live', 'polite');
    const picker = photoPicker(photos, id => {
      ids[side] = id;
      if (!photos.has(ids[1 - side])) side = 1 - side;
      dialog.error.textContent = '';
      render();
      slotButtons[side].focus();
    }, id => ids.includes(id));
    dialog.body.append(slots, actions, heading, ...picker.nodes);
    if (group.in_purgatory) dialog.error.textContent = 'Restore this Set from Purgatory before saving its Duo.';

    async function persist(duo) {
      let saved;
      await dialog.run(async () => {
        saved = await request({method:'POST', path:'/api/sets/' + encodeURIComponent(group.id) + '/duo',
          headers:{'Content-Type':'application/json'}, data:JSON.stringify({expected, duo})});
      });
      if (!saved) { render(); return; }
      dialog.close();
      try { await onSave(saved); }
      catch (error) { alert('Duo saved. Refresh the Library to see the change. ' + error.message); }
    }

    function render() {
      slotButtons.forEach((slot, i) => {
        const item = photos.get(ids[i]);
        slot.setAttribute('aria-pressed', String(i === side));
        slot.replaceChildren();
        if (item) {
          const image = make('img');
          image.alt = '';
          slot.append(image);
          root.naiLoadThumbnail(item.id, image);
        }
        slot.append(make('strong', sides[i]), make('small', item ? item.original_name || 'Set photo'
          : ids[i] ? 'Photo unavailable · choose a replacement' : 'Choose a photo'));
      });
      const complete = ids[0] !== ids[1] && ids.every(id => photos.has(id));
      swap.disabled = !complete;
      preview.disabled = !complete;
      save.disabled = !complete || !!group.in_purgatory;
      heading.textContent = 'Choose the ' + sides[side].toLowerCase() + ' photo';
      picker.render();
    }
    render();
  };
})();
