// ==UserScript==
// @name         NovelAI Local Media Library
// @namespace    local.novelai.media.library
// @version      2.2.3
// @description  NovelAI media library loader with automatic GitHub updates.
// @updateURL    https://raw.githubusercontent.com/bomboclaat12369/novelai-media-library/main/novelai-media.user.js
// @downloadURL  https://raw.githubusercontent.com/bomboclaat12369/novelai-media-library/main/novelai-media.user.js
// @homepageURL  https://github.com/bomboclaat12369/novelai-media-library
// @match        https://novelai.net/*
// @grant        GM_xmlhttpRequest
// @connect      raw.githubusercontent.com
// @connect      127.0.0.1
// @connect      localhost
// @run-at       document-idle
// @noframes
// ==/UserScript==

(() => {
  'use strict';

  const LOADER_VERSION = '2.2.3';
  const MANIFEST = 'https://raw.githubusercontent.com/bomboclaat12369/novelai-media-library/main/manifest.json';
  const CACHE_CODE = 'nai-media-github-payload';
  const CACHE_VERSION = 'nai-media-github-payload-version';
  document.documentElement.dataset.naiMediaLoaderVersion = LOADER_VERSION;

  function requestText(url) {
    return new Promise((resolve, reject) => {
      const sep = url.includes('?') ? '&' : '?';
      GM_xmlhttpRequest({
        method: 'GET',
        url: `${url}${sep}_=${Date.now()}`,
        timeout: 20000,
        headers: { 'Cache-Control': 'no-cache' },
        onload: r => r.status >= 200 && r.status < 300 ? resolve(r.responseText || '') : reject(new Error(`HTTP ${r.status}`)),
        onerror: () => reject(new Error('Network error')),
        ontimeout: () => reject(new Error('Update request timed out')),
      });
    });
  }

  function run(code, version = '') {
    if (version) document.documentElement.dataset.naiMediaPayloadVersion = version;
    eval(code);
  }

  async function fetchLatest(cachedVersion = '') {
    const manifest = JSON.parse(await requestText(MANIFEST));
    const version = String(manifest.userscript_payload_version || '');
    const parts = Array.isArray(manifest.userscript_parts) ? manifest.userscript_parts : [];
    if (!version || !parts.length) throw new Error('Invalid userscript manifest');
    if (cachedVersion === version) return { version, code: null };

    const code = (await Promise.all(parts.map(requestText))).join('');
    if (!code.includes('NovelAI Local Media Library') || !code.includes('loadLibrary')) {
      throw new Error('Downloaded userscript payload did not look valid');
    }
    localStorage.setItem(CACHE_CODE, code);
    localStorage.setItem(CACHE_VERSION, version);
    return { version, code };
  }

  async function loadLatest() {
    const cached = localStorage.getItem(CACHE_CODE) || '';
    const cachedVersion = localStorage.getItem(CACHE_VERSION) || '';

    if (cached) {
      // Critical startup path: run the last verified payload immediately. GitHub is checked
      // only after the UI is already alive, so network latency can never delay panel startup.
      run(cached, cachedVersion);
      fetchLatest(cachedVersion).then(latest => {
        if (latest?.version && latest.version !== cachedVersion) {
          document.documentElement.dataset.naiMediaUpdateReady = latest.version;
          console.info(`[NovelAI Media] payload ${latest.version} cached for the next page load.`);
        }
      }).catch(err => {
        console.warn('NovelAI Media Library background update check failed; keeping cached version.', err);
      });
      return;
    }

    try {
      const latest = await fetchLatest('');
      if (!latest.code) throw new Error('No userscript payload was downloaded');
      run(latest.code, latest.version);
    } catch (err) {
      console.error('NovelAI Media Library could not load.', err);
      alert(`NovelAI Media Library could not load.\n\n${err.message || err}`);
    }
  }

  loadLatest();
})();