// Original post history for the standalone Library photo viewer.
(() => {
  'use strict';
  const root = document.getElementById('nai-media-host')?.shadowRoot;
  if (!root) return;
  function el(tag, text, className) {
    const node = document.createElement(tag);
    if (text) node.textContent = text;
    if (className) node.className = className;
    return node;
  }
  function button(text, action) {
    const node = el('button', text);
    node.type = 'button';
    node.onclick = action;
    return node;
  }
  function organizerLink(base, post, item, text) {
    if (!base || !item || !/^http:\/\/127\.0\.0\.1:[1-9][0-9]{0,4}\/organizer$/.test(base)) return null;
    const url = new URL(base);
    url.searchParams.set('sourceCollection', item.collection);
    url.searchParams.set('sourcePost', post);
    url.searchParams.set('sourcePhoto', item.photo);
    const link = el('a', text);
    link.href = url.href;
    link.target = '_blank';
    link.rel = 'noopener noreferrer';
    return link;
  }
  const style = el('style');
  style.textContent = [
    '.naiPostDialog{width:min(1100px,96vw)!important;max-height:94dvh!important;display:flex;flex-direction:column}',
    '.naiPostBody{overflow:auto;min-height:0;overscroll-behavior:contain;padding:12px 16px 18px}',
    '.naiPostBar{display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin:0 0 10px}',
    '.naiPostBar select{max-width:100%}.naiPostDialog a{color:#c5beff;text-underline-offset:3px;overflow-wrap:anywhere}',
    '.naiPostGrid{display:grid;grid-template-columns:repeat(auto-fill,minmax(min(145px,100%),1fr));gap:10px}',
    '.naiPostCell{display:flex;flex-direction:column;gap:4px;border:1px solid #434562;border-radius:8px;padding:6px;min-width:0;overflow-wrap:anywhere}',
    '.naiPostCell[aria-current=true]{border:2px solid #ffda82;padding:5px}.naiPostCell small{color:#c4c4d4}',
    '.naiPostImage{width:100%;height:auto;aspect-ratio:4/5;object-fit:contain;background:#171825;border-radius:3px;display:block}',
    '.naiPostPic{border:0!important;padding:0!important;background:none!important;width:100%;color:inherit}',
    '.naiPostEmptyPic{display:grid;place-content:center;text-align:center;color:#c4c4d4;font-size:12px}',
    '.naiPostBody details{margin-top:14px;overflow-wrap:anywhere}.naiPostBody summary{cursor:pointer}.naiPostBody ul{padding-inline-start:22px}',
    '.naiPostLarge{width:100%;height:min(65dvh,860px);object-fit:contain;background:#10111d}.naiPostStatus{color:#ddd8f6}',
    '@media(max-width:560px){.naiPostGrid{grid-template-columns:repeat(2,minmax(0,1fr))}.naiPostBody{padding:8px}.naiPostDialog{max-height:96dvh!important}}'
  ].join('\n');
  root.append(style);

  function openHistory(item, trigger) {
    const modalRoot = root.getElementById('modalRoot');
    const wrap = el('div', '', 'modalWrap');
    const dialog = el('section', '', 'modal naiPostDialog');
    dialog.setAttribute('role', 'dialog');
    dialog.setAttribute('aria-modal', 'true');
    dialog.setAttribute('aria-label', 'Original post history');
    const head = el('div', '', 'modalHead');
    const title = el('div', 'Original post history', 'modalTitle');
    const body = el('div', '', 'modalBody naiPostBody');
    const closeButton = button('Close', close);
    const status = el('span', '', 'naiPostStatus');
    status.setAttribute('role', 'status');
    head.append(title, closeButton);
    dialog.append(head, body);
    wrap.append(dialog);
    modalRoot.append(wrap);
    const requests = new AbortController();
    let serial = 0, previewBack = null;
    function close() {
      requests.abort();
      wrap.remove();
      if (trigger.isConnected) trigger.focus();
    }
    wrap.onclick = event => { if (event.target === wrap) close(); };
    wrap.addEventListener('keydown', event => {
      if (event.key === 'Escape') {
        event.preventDefault(); event.stopPropagation();
        if (previewBack) previewBack(); else close();
      }
    });
    closeButton.focus();
    function showSources(data, expanded) {
      if (!data.sources.length) return;
      const details = el('details');
      details.open = expanded;
      details.append(el('summary', 'Recorded sources (' + data.sources.length + ')'));
      const list = el('ul');
      for (const src of data.sources) {
        const row = el('li', src.path || src.name);
        if (src.url && /^https?:\/\//i.test(src.url)) {
          const link = el('a', src.url);
          link.href = src.url; link.target = '_blank'; link.rel = 'noopener noreferrer';
          row.append(document.createTextNode(' '), link);
        }
        list.append(row);
      }
      details.append(list); body.append(details);
    }
    function showLarge(row, cell, post, base) {
      const contents = [...body.childNodes], scroll = body.scrollTop;
      const back = button('Back to post', () => previewBack());
      previewBack = () => {
        previewBack = null;
        body.querySelector('video')?.pause();
        body.replaceChildren(...contents);
        body.scrollTop = scroll;
        cell.focus({preventScroll:true});
      };
      const actions = el('div', '', 'naiPostBar');
      actions.append(back);
      if (row.media_id) actions.append(button('Show in Library', () => { close(); root.naiSelectMedia(row.media_id); }));
      const link = organizerLink(base, post, row.workbench, 'Open in Workbench');
      if (link) actions.append(link);
      const video = row.media_type === 'video';
      const image = el(video ? 'video' : 'img', '', 'naiPostLarge');
      if (video) image.controls = true;
      else image.alt = row.name;
      image.onerror = () => image.replaceWith(el('p', 'The recorded photo is unavailable.'));
      image.src = row.media_id ? '/api/media/' + encodeURIComponent(row.media_id) + '/original' :
        '/api/post-previews/' + encodeURIComponent(row.preview) + '?size=large';
      body.replaceChildren(actions, el('p', row.name), image);
      body.scrollTop = 0;
      back.focus();
    }
    async function load(post, offset) {
      const token = ++serial;
      previewBack = null;
      status.textContent = 'Loading original post history…';
      body.replaceChildren(status);
      try {
        const url = new URL('/api/media/' + encodeURIComponent(item.id) + '/post-history', location.origin);
        if (post) url.searchParams.set('post', post);
        if (offset != null) url.searchParams.set('offset', offset);
        const response = await fetch(url, {signal: requests.signal, cache:'no-store'});
        if (response.status === 404) throw Error('Post history is unavailable. Check that the photo is still saved and the companion is up to date.');
        const data = await response.json();
        if (!response.ok) throw Error(data.error || 'Original post history could not be loaded.');
        if (token !== serial || !wrap.isConnected) return;
        render(data);
      } catch (error) {
        if (token !== serial || !wrap.isConnected) return;
        status.textContent = error.message || 'Could not reach the Library.';
        body.replaceChildren(status, button('Retry', () => load(post, offset)));
      }
    }
    function render(data) {
      body.replaceChildren();
      body.scrollTop = 0;
      if (!data.page) {
        body.append(el('p', 'No original post is recorded for this photo.'));
        showSources(data, true);
        return;
      }
      const page = data.page, bar = el('div', '', 'naiPostBar');
      const chosen = data.posts.find(p => p.key === page.post);
      if (data.posts.length > 1) {
        const select = el('select');
        select.setAttribute('aria-label', 'Original post');
        for (const p of data.posts) {
          const option = el('option', p.label); option.value = p.key; select.append(option);
        }
        select.value = page.post;
        select.onchange = () => load(select.value);
        bar.append(el('span', 'Original posts (' + data.posts.length + ')'), select);
      } else bar.append(el('strong', chosen.label));
      const originName = chosen.kind === 'instagram' ? 'Instagram' : 'Forum';
      let metadata = originName;
      if (chosen.post_id && !chosen.label.includes(chosen.post_id)) metadata += ' · ' + chosen.post_id;
      if (chosen.post_date && !chosen.label.includes(chosen.post_date)) metadata += ' · ' + chosen.post_date;
      bar.append(el('span', metadata, 'muted'));
      const link = organizerLink(data.organizer, page.post, page.workbench, 'Open in Workbench');
      if (link) bar.append(link);
      body.append(bar);
      const end = page.offset + page.items.length;
      const nav = el('div', '', 'naiPostBar');
      nav.append(el('span', (page.offset + 1) + '–' + end + ' of ' + page.total + ' recorded'));
      if (page.total > page.limit) {
        const prev = button('Previous', () => load(page.post, page.offset - page.limit));
        const next = button('Next', () => load(page.post, page.offset + page.limit));
        prev.disabled = !page.offset; next.disabled = end >= page.total;
        nav.append(prev, next);
        if (page.focus < page.offset || page.focus >= end) nav.append(button('Back to this photo', () => load(page.post)));
      }
      body.append(nav);
      const grid = el('div', '', 'naiPostGrid');
      body.append(grid);
      for (const [index, row] of page.items.entries()) {
        const cell = el('div', '', 'naiPostCell');
        if (row.current) cell.setAttribute('aria-current', 'true');
        grid.append(cell);
        function unavailable() {
          const target = organizerLink(data.organizer, page.post, row.workbench, 'View in Workbench');
          const placeholder = el('div', '', 'naiPostImage naiPostEmptyPic');
          placeholder.append(target || el('span', 'Preview unavailable'));
          return placeholder;
        }
        if (row.media_id || row.preview) {
          const pic = button('', () => showLarge(row, pic, page.post, data.organizer));
          pic.className = 'naiPostPic';
          pic.setAttribute('aria-label', 'View ' + row.name);
          const image = el('img', '', 'naiPostImage'); image.alt = '';
          pic.append(image); cell.append(pic);
          if (row.media_id) root.naiLoadThumbnail(row.media_id, image);
          else {
            image.loading = 'lazy';
            image.onerror = () => pic.replaceWith(unavailable());
            image.src = '/api/post-previews/' + encodeURIComponent(row.preview);
          }
        } else {
          cell.append(unavailable());
        }
        cell.append(el('small', '#' + (page.offset + index + 1) + ' · ' +
          (row.current ? 'This photo' : row.media_id ? 'In Library' : 'Outside Library')), el('span', row.name));
      }
      if (page.workbench && !data.organizer) {
        body.append(el('p', 'For the full Workbench view, open Workbench and refresh this history.', 'muted'),
          button('Refresh history', () => load(page.post, page.offset)));
      }
      showSources(data, false);
    }
    load();
  }
  root.naiPostHistoryButton = (panel, item) => {
    const trigger = button('Original post history', () => openHistory(item, trigger));
    panel.append(trigger);
  };
  root.naiRefreshSelectedMetadata?.();
})();
