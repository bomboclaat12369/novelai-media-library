/* Read-only bridge to the approved Media Library card renderer. */
(() => {
  'use strict';
  if (globalThis.AfterHoursCards) return;

  const modules = ['ranks', 'collection', 'editions', 'base'];
  const demoTiers = ['Bronze', 'Silver', 'Gold', 'Master', 'Grandmaster'];
  let root = null;
  let catalog = null;
  let rows = new Map();
  let entries = new Map();
  let initialization = null;
  let phase = 'idle';
  let failure = null;

  function entryFor(card, isDemo) {
    // Source rank presentation is independent of the game's rarity and bonuses.
    const fallback = {
      name: card.name || card.id,
      rating: Number.isFinite(card.rating) ? card.rating : 1200,
      played: isDemo ? 20 : 0,
      rating_status: isDemo ? 'Established' : 'Unrated',
      provisional: !isDemo,
      tier: isDemo ? demoTiers[card.rarity] || 'Bronze' : 'Unranked',
      titles: [],
      captain_sets: [],
    };
    return {
      ...fallback,
      ...(card.presentation || {}),
      id: card.id,
      images: [card.id],
      count: 1,
    };
  }

  function update(nextCatalog) {
    if (!nextCatalog?.people || !nextCatalog?.cards) {
      throw new Error('A card catalog is required for presentation.');
    }
    catalog = nextCatalog;
    rows = new Map();
    entries = new Map();
    for (const card of Object.values(catalog.cards)) {
      const entry = entryFor(card, Boolean(catalog.demo));
      entries.set(card.id, entry);
      if (!rows.has(card.owner)) rows.set(card.owner, []);
      rows.get(card.owner).push(entry);
    }
    if (!root) return;
    root.naiGetLibrary = () => ({
      characters: Object.values(catalog.people).map(person => ({
        id: person.id,
        name: person.name,
      })),
    });
    if (!root.naiCards?.cache) return;
    root.naiCards.cache.clear();
    for (const person of Object.values(catalog.people)) {
      root.naiCards.cache.set(person.id, {
        collection: {
          finish: person.collection?.finish || 'obsidian',
          frames: person.collection?.frames || {},
        },
      });
    }
  }

  function loadModule(name) {
    return new Promise((resolve, reject) => {
      const script = document.createElement('script');
      script.src = '/game/renderer/' + name + '.js';
      script.async = false;
      script.onload = () => resolve();
      script.onerror = () => reject(new Error('The approved ' + name + ' card module could not load.'));
      document.head.append(script);
    });
  }

  function init(nextCatalog) {
    update(nextCatalog);
    if (initialization) return initialization;
    phase = 'loading';
    initialization = (async () => {
      root = globalThis.gameRoot;
      if (!root || document.getElementById('nai-media-host')?.shadowRoot !== root) {
        throw new Error('The game shadow root must belong to #nai-media-host.');
      }
      document.documentElement.dataset.naiStandalone = '1';
      // Renderer editing helpers are intentionally disconnected from the companion.
      root.naiOutfitRequest = () => Promise.reject(new Error('Library editing is unavailable inside the game.'));
      root.naiOutfitOriginal = () => Promise.reject(new Error('Use a game-owned card to inspect its original.'));
      update(catalog);
      const response = await fetch('/game/api/renderer');
      if (!response.ok) throw new Error('The approved card assets could not be loaded.');
      const assets = await response.json();
      if (!assets.editions?.editions || !assets.editions.fonts || !assets.base?.frames) {
        throw new Error('The approved card asset catalog is incomplete.');
      }
      globalThis.naiCardEditionAssets = assets.editions;
      globalThis.naiCardBaseAssets = assets.base;
      globalThis.naiCardTitleAssets = assets.titles || {};
      for (const name of modules) await loadModule(name);
      if (!root.naiCards?.lightCard || !root.naiCards.baseReady || !root.naiCards.frameTypography) {
        throw new Error('The approved card renderer did not initialize.');
      }
      update(catalog);
      const [fontResults] = await Promise.all([
        root.naiCards.frameTypography.ready,
        root.naiCards.baseReady,
      ]);
      if (fontResults.some(result => result.status === 'rejected')) {
        throw new Error('An approved card font could not be loaded.');
      }
      await document.fonts.ready;
      phase = 'ready';
      return api;
    })().catch(error => {
      phase = 'error';
      failure = error;
      // Keep the rejected promise: retrying halfway through module decoration
      // would wrap the same renderer twice. A page reload retries cleanly.
      throw error;
    });
    return initialization;
  }

  function placeholder(label, name) {
    const box = document.createElement('div');
    box.className = 'game-card-placeholder';
    box.setAttribute('role', 'img');
    box.setAttribute('aria-label', label + (name ? ' · ' + name : ''));
    box.style.cssText = 'width:100%;height:100%;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:12px;background:#111923;color:#b8becb;text-align:center;padding:16px;box-sizing:border-box';
    const mark = document.createElement('span');
    mark.textContent = name ? name.trim().slice(0, 1).toUpperCase() : '◇';
    mark.style.cssText = 'font:500 clamp(24px,12cqw,60px)/1 Georgia,serif;color:#bda879';
    const caption = document.createElement('span');
    caption.textContent = label;
    caption.style.cssText = 'font:600 clamp(9px,2.7cqw,13px)/1.5 system-ui;letter-spacing:.08em;text-transform:uppercase';
    box.append(mark, caption);
    return box;
  }

  function originalURL(card) {
    // Never accept remote or arbitrary file URLs from catalog metadata.
    if (typeof card.image !== 'string' || !card.image.startsWith('/api/image/')) return null;
    return '/game/api/image/' + encodeURIComponent(card.id) + '?original=1';
  }

  function mount(container, nextCatalog, card, options = {}) {
    if (phase !== 'ready') throw failure || new Error('Wait for AfterHoursCards.init before mounting cards.');
    if (nextCatalog !== catalog) update(nextCatalog);
    if (!card || !catalog.cards[card.id]) throw new Error('The card is not in this catalog.');
    if (container.getRootNode() !== root) throw new Error('Cards must be mounted inside the game shadow root.');
    const owner = catalog.people[card.owner];
    const name = owner?.name || 'Collection';
    const owned = options.owned === true;
    const url = owned && !catalog.demo && card.available !== false ? originalURL(card) : null;
    const label = !owned ? 'Not collected' : catalog.demo ? 'Demo portrait' : 'Artwork unavailable';
    let photo = placeholder(label, name);
    let node;
    if (url) {
      photo = document.createElement('img');
      photo.alt = name + ' · ' + (card.name || 'Owned photograph');
      photo.loading = 'lazy';
      photo.decoding = 'async';
      photo.draggable = false;
      photo.addEventListener('error', () => {
        photo.replaceWith(placeholder('Artwork unavailable', name));
        if (node) node.dataset.artwork = 'unavailable';
      }, {once: true});
      photo.src = url;
    }
    node = root.naiCards.lightCard(entries.get(card.id), rows.get(card.owner) || [], card.owner, photo, true, card.id);
    // Native artwork is 7:10; the approved aperture inside it is exactly 3:4.
    node.style.width = '100%';
    node.style.height = 'auto';
    node.style.aspectRatio = '7 / 10';
    node.style.boxSizing = 'border-box';
    node.dataset.gameCard = card.id;
    node.dataset.gameOwned = String(owned);
    node.dataset.artwork = url ? 'original' : catalog.demo && owned ? 'demo' : owned ? 'unavailable' : 'locked';
    container.replaceChildren(node);
    return node;
  }

  const api = {
    init,
    update,
    mount,
    get ready() { return initialization; },
    get status() { return phase; },
    get error() { return failure?.message || null; },
  };
  globalThis.AfterHoursCards = api;
})();
