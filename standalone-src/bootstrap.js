// Native companion transport for the local browser tab. No extension bridge.
(() => {
  'use strict';
  document.documentElement.dataset.naiStandalone = '1';
  window.GM_xmlhttpRequest = options => {
    const url = new URL(options.url, location.href);
    if (!['127.0.0.1','localhost'].includes(url.hostname) || url.port !== '8765' || !url.pathname.startsWith('/api/')) {
      queueMicrotask(() => options.onerror?.({status:0,error:'Only local companion requests are supported.'}));
      return {abort(){}};
    }
    const xhr = new XMLHttpRequest();
    xhr.open(options.method || 'GET', url.pathname + url.search, true);
    xhr.timeout = options.timeout || 0;
    if (options.responseType && options.responseType !== 'text') xhr.responseType = options.responseType;
    for (const [key,value] of Object.entries(options.headers || {})) {
      if (!/^(origin|host|referer|content-length|cookie)$/i.test(key)) xhr.setRequestHeader(key,value);
    }
    const response = event => ({
      status:xhr.status, statusText:xhr.statusText,
      response:xhr.response,
      responseText:!xhr.responseType || xhr.responseType === 'text' ? xhr.responseText : '',
      responseHeaders:xhr.getAllResponseHeaders(), finalUrl:xhr.responseURL,
      loaded:event?.loaded || 0, total:event?.total || 0, lengthComputable:!!event?.lengthComputable,
    });
    for (const name of ['load','error','timeout','abort','loadend','loadstart','progress','readystatechange']) {
      xhr.addEventListener(name,event => options['on'+name]?.(response(event)));
    }
    if(options.upload?.onprogress)xhr.upload.onprogress=options.upload.onprogress;
    xhr.send(options.data ?? null);
    return {abort:()=>xhr.abort()};
  };
})();
