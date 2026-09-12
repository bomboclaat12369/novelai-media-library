// ==UserScript==
// @name         NovelAI Local Media Library
// @namespace    local.novelai.media.library
// @version      2.2.0
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

  const MANIFEST = 'https://raw.githubusercontent.com/bomboclaat12369/novelai-media-library/main/manifest.json';
  const CACHE_CODE = 'nai-media-github-payload';
  const CACHE_VERSION = 'nai-media-github-payload-version';

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

  function run(code) {
    eval(code);
  }

  async function loadLatest() {
    const cached = localStorage.getItem(CACHE_CODE) || '';
    try {
      const manifest = JSON.parse(await requestText(MANIFEST));
      const version = String(manifest.userscript_payload_version || '');
      const parts = Array.isArray(manifest.userscript_parts) ? manifest.userscript_parts : [];
      if (!version || !parts.length) throw new Error('Invalid userscript manifest');

      const cachedVersion = localStorage.getItem(CACHE_VERSION) || '';
      if (cached && cachedVersion === version) {
        run(cached);
        return;
      }

      const code = (await Promise.all(parts.map(requestText))).join('');
      if (!code.includes('NovelAI Local Media Library') || !code.includes('loadLibrary')) {
        throw new Error('Downloaded userscript payload did not look valid');
      }
      localStorage.setItem(CACHE_CODE, code);
      localStorage.setItem(CACHE_VERSION, version);
      run(code);
    } catch (err) {
      if (cached) {
        console.warn('NovelAI Media Library update check failed; using cached version.', err);
        run(cached);
      } else {
        console.error('NovelAI Media Library could not load.', err);
        alert(`NovelAI Media Library could not load.\n\n${err.message || err}`);
      }
    }
  }

  loadLatest();
})();
