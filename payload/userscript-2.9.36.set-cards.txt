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
    .naiCollectionOverlay:is(.naiDuoEditor,.naiDuoViewer){padding:clamp(8px,1.25vmin,20px);font-size:clamp(15px,1vw,19px)}
    :is(.naiDuoEditor,.naiDuoViewer) .naiCollectionInner{width:100%;height:100%;display:flex;flex-direction:column;gap:clamp(6px,1vmin,14px)}
    :is(.naiDuoEditor,.naiDuoViewer) .naiCollectionHeader{flex:none;margin:0}
    :is(.naiDuoEditor,.naiDuoViewer) .naiCollectionHeader h2{min-width:0;font-size:clamp(18px,2.5vmin,30px);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
    :is(.naiDuoEditor,.naiDuoViewer) .naiCollectionError:empty,.naiDuoLibrary .naiEvolutionActions:empty{display:none}
    :is(.naiDuoEditor,.naiDuoViewer) button,.naiDuoEditor input{min-height:44px}
    .naiDuoWorkspace{flex:1;min-height:0;display:grid;grid-template-columns:minmax(0,3fr) minmax(0,2fr);gap:clamp(12px,1.6vw,32px)}
    .naiDuoSelection,.naiDuoLibrary{min-width:0;min-height:0;display:flex;flex-direction:column;gap:clamp(6px,1vmin,14px)}
    .naiDuoSides{flex:1;min-height:0;display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:clamp(6px,1vw,18px)}
    .naiDuoEditor .naiDuoSides button{display:grid;grid-template-rows:minmax(0,1fr) auto;min-width:0;min-height:0;padding:0;text-align:left;overflow:hidden;background:#101927}
    .naiDuoSides button[aria-pressed=true]{border-color:#d9ba7a;box-shadow:inset 0 0 0 1px #d9ba7a}
    .naiDuoSlotPhoto{display:grid;place-items:center;min-height:0;margin:3px;background:#0a101b}
    .naiDuoSlotPhoto:empty::before{content:'+';color:#a9b7cb;font-size:clamp(26px,4vmin,46px);font-weight:300}
    .naiDuoSlotPhoto img{display:block;width:100%;height:100%;min-height:0;object-fit:contain}
    .naiDuoSlotCaption{display:grid;padding:6px clamp(8px,1vw,16px)}
    .naiDuoSlotCaption strong{font-size:clamp(16px,1.35vw,23px)}
    .naiDuoSlotCaption small,.naiDuoLibrary .naiEvolutionPicker span,.naiDuoSideLabel{overflow:hidden;white-space:nowrap;text-overflow:ellipsis}
    .naiDuoSlotCaption small{font:inherit;font-size:.9em;color:#b6c3d4}
    .naiDuoWorkspace .naiEvolutionActions{flex:none;margin:0}
    .naiDuoLibrary h3{font-size:1.1em;margin:0}
    .naiDuoLibrary>.naiSearchField{flex:none!important}
    .naiDuoEditor .naiDuoLibrary input{width:100%}
    .naiDuoLibrary .naiEvolutionPicker{flex:1;min-height:0;overflow-y:auto;overscroll-behavior:contain;align-content:start;grid-auto-rows:max-content;
      grid-template-columns:repeat(auto-fill,minmax(min(100%,clamp(174px,14vw,280px)),1fr));gap:clamp(6px,1vmin,14px);padding:3px}
    .naiDuoLibrary .naiEvolutionPicker button{grid-template-rows:auto auto;padding:4px;gap:4px;align-self:start}
    .naiDuoLibrary .naiEvolutionPicker img{display:block;width:100%;height:auto;aspect-ratio:4/5;background:#0a101b}
    .naiDuoLibrary .naiEvolutionPicker span{font-size:.92em;padding:0 4px 3px}
    .naiDuoViewer .naiCollectionHeader{display:grid;grid-template-columns:auto minmax(0,1fr) auto auto;gap:8px}
    .naiDuoSideLabel{min-width:0;color:#b6c3d4}
    .naiDuoPreview{flex:1;min-height:0;display:grid;place-items:center;container-type:size;perspective:1200px}
    .naiDuoTurn{position:relative;width:min(100cqw,70cqh);aspect-ratio:7/10;transform-style:preserve-3d;transition:transform .36s ease-in-out;cursor:pointer}
    .naiDuoTurn[data-side=back]{transform:rotateY(180deg)}
    .naiDuoFace{position:absolute;inset:0;backface-visibility:hidden}
    .naiDuoFace:nth-child(2){transform:rotateY(180deg)}
    .naiDuoFace .naiTradingCard{width:100%;height:100%;aspect-ratio:7/10}
    .naiDuoFace p{position:absolute;inset:38% 0 auto;text-align:center;background:#151a29}
    @media(prefers-reduced-motion:reduce){.naiDuoTurn{transition:none}}
    @media(orientation:portrait),(max-width:800px) and (min-height:500px){
      .naiDuoWorkspace{display:flex;flex-direction:column;gap:10px}
      .naiDuoSides{flex:none;height:clamp(148px,34dvh,350px)}
      .naiDuoLibrary{flex:1}
      .naiDuoLibrary .naiEvolutionPicker{grid-template-columns:repeat(auto-fill,minmax(min(42%,190px),1fr))}
    }
    @media(max-width:600px){
      .naiDuoViewer .naiCollectionHeader{grid-template-columns:minmax(0,1fr) auto auto;gap:2px 6px}
      .naiDuoSideLabel{grid-column:1/-1;grid-row:2;font-size:.9em}
      .naiDuoEditor .naiCollectionHeader{flex-wrap:nowrap}
      .naiDuoEditor .naiEvolutionActions button{padding:6px 9px}
    }
  `;
  root.append(style);

  function setPhotos(group, library) {
    const members = new Set(group.media_ids || []);
    return new Map(library.media.filter(item =>
      members.has(item.id) && item.character_id === group.character_id && (item.media_type || 'image') === 'image'
      && !item.in_review && !item.in_purgatory && !item.flagged_for_removal
    ).map(item => [item.id, item]));
  }

  async function showOriginal(tile, item, owner, request, urls, duo) {
    if (!item) { tile.append(make('p', 'Photo unavailable')); return; }
    const image = make('img');
    image.alt = item.original_name || 'Set photo';
    const id = item.id;
    const entry = {id, images:[id], count:1, name:image.alt, tier:'Unranked', titles:[]};
    if (duo) Object.assign(entry, {name:duo.setName, duo_side:duo.side, preview_ovr:duo.overall});
    tile.append(root.naiCards.lightCard(entry, [entry], owner.id, image, !!duo, id));
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
  function previewDuo(ids, photos, owner, request, setName, overall) {
    const urls = [];
    const dialog = root.naiCards.modal('Duo preview', () => urls.forEach(url => URL.revokeObjectURL(url)));
    dialog.wrap.classList.add('naiDuoViewer');
    dialog.body.className = 'naiDuoPreview';
    const label = make('strong');
    label.className = 'naiDuoSideLabel';
    label.setAttribute('aria-live', 'polite');
    const turn = make('div');
    turn.className = 'naiDuoTurn';
    turn.setAttribute('role', 'button');
    turn.tabIndex = 0;
    let side = 0;
    function turnOver() { side = 1 - side; display(); }
    const flip = button('', turnOver);
    turn.onclick = turnOver;
    turn.onkeydown = event => {
      if (event.key === 'Enter' || event.key === ' ') {
        event.preventDefault();
        if (!event.repeat) turnOver();
      }
    };
    dialog.head.lastElementChild.before(label, flip);
    dialog.body.append(turn);
    const faces = ids.map((id, index) => {
      const face = make('div');
      face.className = 'naiDuoFace';
      turn.append(face);
      showOriginal(face, photos.get(id), owner, request, urls, {setName, overall, side:sides[index].toLowerCase()});
      return face;
    });
    function display() {
      label.textContent = sides[side] + ' · ' + (photos.get(ids[side]).original_name || 'Set photo');
      turn.dataset.side = sides[side].toLowerCase();
      faces.forEach((face, index) => face.setAttribute('aria-hidden', String(index !== side)));
      flip.textContent = 'Flip to ' + sides[1 - side].toLowerCase();
      turn.setAttribute('aria-label', flip.textContent + ' photo');
    }
    display();
    flip.focus();
  }

  root.naiEditSetDuo = function(group, library, request, onSave) {
    const owner = library.characters.find(character => character.id === group.character_id);
    if (!owner || (group.kind || 'set') !== 'set' || root.naiViewerOnly) return;
    const expected = group.after_hours_duo ?? null;
    const dialog = root.naiCards.modal('Duo · ' + group.name);
    dialog.wrap.classList.add('naiDuoEditor');
    if (expected !== null && expected.version !== 1) {
      dialog.error.textContent = 'Update the Library to edit this Duo format.';
      return;
    }
    const photos = setPhotos(group, library);
    const ids = sides.map((_, i) => expected?.media_ids?.[i] || null);
    let side = 0;
    const slots = make('div');
    slots.className = 'naiDuoSides';
    const sideSlots = sides.map((name, i) => {
      const slot = button('', () => { side = i; render(); });
      slot.setAttribute('aria-label', 'Choose ' + name.toLowerCase() + ' photo');
      const photo = make('span');
      photo.className = 'naiDuoSlotPhoto';
      const caption = make('span');
      caption.className = 'naiDuoSlotCaption';
      const filename = make('small');
      caption.append(make('strong', name), filename);
      slot.append(photo, caption);
      slots.append(slot);
      return {slot, photo, filename};
    });
    const actions = make('div');
    actions.className = 'naiEvolutionActions';
    const swap = button('Swap sides', () => { ids.reverse(); render(); });
    const preview = button('Preview flip', async () => {
      const pair = [...ids];
      let overall = null;
      if (expected?.media_ids?.length === 2 && pair.every(id => expected.media_ids.includes(id))) {
        await dialog.run(async () => {
          const board = await request({method:'POST', path:'/api/battles/summary',
            headers:{'Content-Type':'application/json'}, data:JSON.stringify({character_id:owner.id, kind:'images'})});
          const entry = board.entries.find(row => row.duo_side && pair.every(id => row.images.includes(id)));
          if (entry) overall = root.naiCards.ovr(entry, board.entries);
        });
      }
      if (dialog.wrap.isConnected) previewDuo(pair, photos, owner, request, group.name, overall);
    });
    const save = button('Save Duo', () => persist({version:1, media_ids:[...ids]}));
    save.dataset.primary = 'true';
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
      sideSlots[side].slot.focus({preventScroll:true});
    }, id => ids.includes(id));
    const selection = make('div');
    selection.className = 'naiDuoSelection';
    selection.append(slots, actions);
    const choices = make('div');
    choices.className = 'naiDuoLibrary';
    choices.append(heading, ...picker.nodes);
    dialog.body.className = 'naiDuoWorkspace';
    dialog.body.append(selection, choices);
    if (group.in_purgatory) dialog.error.textContent = 'Restore this Set from Purgatory before saving its Duo.';

    async function persist(duo) {
      let saved;
      await dialog.run(async () => {
        try {
          saved = await request({method:'POST', path:'/api/sets/' + encodeURIComponent(group.id) + '/duo',
            headers:{'Content-Type':'application/json'}, data:JSON.stringify({expected, duo})});
        } catch (error) {
          // Older companions serve the updated editor but have no Duo endpoint.
          if (error.message === 'Not found' || error.message === 'Request failed (404)') {
            throw new Error('Duo saves need Media Library companion 2.7.82 or later. Update and restart the companion, then try again.');
          }
          throw error;
        }
      });
      if (!saved) { render(); return; }
      dialog.close();
      try { await onSave(saved); }
      catch (error) { alert('Duo saved. Refresh the Library to see the change. ' + error.message); }
    }

    function render() {
      sideSlots.forEach(({slot, photo, filename}, i) => {
        const item = photos.get(ids[i]);
        slot.setAttribute('aria-pressed', String(i === side));
        if (item && photo.dataset.selectedId !== item.id) {
          const image = make('img');
          image.alt = '';
          const url = new URL('/api/media/' + encodeURIComponent(item.id) + '/original', location.href);
          image.src = root.naiVersionMediaUrl(url);
          photo.replaceChildren(image);
          photo.dataset.selectedId = item.id;
        }
        filename.textContent = item ? item.original_name || 'Set photo'
          : ids[i] ? 'Photo unavailable · choose a replacement' : 'Choose a photo';
        filename.title = filename.textContent;
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
