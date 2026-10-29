// Scope browser form-history suppression to this app, never the host website.
(() => {
  const root=document.getElementById('nai-media-host')?.shadowRoot ||
    (document.documentElement.dataset.localDuplicateReview==='1'?document:null);
  if(!root||root.__noSavedFormInfo)return;
  root.__noSavedFormInfo=true;
  const selector='input,textarea,form';
  function apply(node){
    if(node.nodeType===1&&node.matches(selector))node.setAttribute('autocomplete','off');
    node.querySelectorAll?.(selector).forEach(el=>el.setAttribute('autocomplete','off'));
  }
  apply(root);
  new MutationObserver(records=>{for(const record of records)for(const node of record.addedNodes)apply(node)}).observe(root,{childList:true,subtree:true});
  root.addEventListener('focusin',event=>{if(event.target.matches?.(selector))event.target.setAttribute('autocomplete','off')},true);
})();
