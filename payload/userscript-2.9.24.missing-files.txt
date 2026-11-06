// Shared missing-originals interface, used by the library and Folder Organizer.
(() => {
 'use strict';
 window.naiOpenMissingFiles=function({host,request}) {
  const make=(tag,text)=>{const node=document.createElement(tag);if(text)node.textContent=text;return node};
  const wrap=make('div'),panel=make('section'),style=make('style');wrap.className='naiMissingOverlay';panel.className='naiMissingPanel';panel.setAttribute('role','dialog');panel.setAttribute('aria-modal','true');panel.setAttribute('aria-label','Missing file finder');
  style.textContent='.naiMissingOverlay{position:fixed;inset:0;z-index:2147483600;background:#000b;display:grid;place-items:center;color:#eee;font:14px system-ui}.naiMissingPanel{background:#151b2b;border:1px solid #66718c;border-radius:12px;padding:22px;width:min(860px,90vw);max-height:88vh;overflow:auto;box-sizing:border-box}.naiMissingPanel button{margin:4px;padding:7px 11px}.naiMissingPanel textarea{width:100%;box-sizing:border-box;min-height:68px;background:#0d1220;color:#eee;padding:9px}.naiMissingPanel article{padding:12px 0;border-top:1px solid #475066;overflow-wrap:anywhere}.naiMissingPanel p{margin:7px 0}.naiMissingPanel .mfControls{display:flex;flex-wrap:wrap;gap:6px;align-items:center}.naiMissingPanel input{margin-right:8px}';
  let job=null,offset=0,timer=null,closed=false,working=false,lastPage=null;const selected=new Set();const prior=host.activeElement||document.activeElement;
  function btn(text,fn){const b=make('button',text);b.type='button';b.onclick=()=>Promise.resolve().then(fn).catch(e=>{status.textContent=e.message});return b}
  const status=make('p','Ready to check saved originals.');status.setAttribute('aria-live','polite');
  function close(){closed=true;clearTimeout(timer);window.removeEventListener('keydown',keys,true);wrap.remove();prior?.focus?.()}
  function keys(e){if(e.key==='Escape'){e.preventDefault();e.stopImmediatePropagation();close()}else if(e.key==='Tab'){const nodes=[...panel.querySelectorAll('button,input,textarea')].filter(n=>!n.disabled);const at=nodes.indexOf((host.activeElement||document.activeElement));if(e.shiftKey&&at<=0){e.preventDefault();nodes.at(-1)?.focus()}else if(!e.shiftKey&&at===nodes.length-1){e.preventDefault();nodes[0]?.focus()}}}
  const roots=make('textarea');roots.setAttribute('aria-label','Folders to search for missing originals');roots.placeholder='Optional: paste a folder path, one per line';
  const list=make('div'),controls=make('div');controls.className='mfControls';
  const scan=btn('Scan originals / find copies',async()=>{working=true;setControls();try{selected.clear();offset=0;job=await request('start',{search_roots:roots.value.split(/\r?\n/).map(s=>s.trim()).filter(Boolean)});await refresh()}finally{working=false;setControls()}});
  const stop=btn('Stop scan',async()=>{if(job)await request('stop',{job_id:job.id});await refresh()});
  const recover=btn('Recover selected',async()=>{
   if(!selected.size||!job)return;
   if(!window.confirm('Copy '+selected.size+' verified original(s) back to their expected locations? Existing files will not be replaced.'))return;
   working=true;setControls();try{for(const id of [...selected]){status.textContent='Recovering original…';await request('recover',{job_id:job.id,id});selected.delete(id)}await refresh()}finally{working=false;setControls()}
  });
  const previous=btn('Previous',async()=>{offset=Math.max(0,offset-100);selected.clear();await refresh()});
  const next=btn('Next',async()=>{offset+=100;selected.clear();await refresh()});
  const download=btn('Download report',async()=>{
   if(!job)return;const id=job.id,report={...lastPage,issues:[]};delete report.offset;
   for(let at=0;at<lastPage.total_issues;at+=500){const page=await request('status?'+new URLSearchParams({id,offset:at,limit:500}));report.issues.push(...page.issues)}
   const url=URL.createObjectURL(new Blob([JSON.stringify(report,null,2)],{type:'application/json'})),a=make('a');a.href=url;a.download='missing-originals.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
  });
  function setControls(){scan.disabled=working||!!job?.running;roots.disabled=scan.disabled;stop.disabled=working||!job?.running;recover.disabled=working||!!job?.running||!!job?.cancelled||!!job?.error||!selected.size;download.disabled=working||!job||!!job.running;previous.disabled=working||offset===0;next.disabled=working||!lastPage||offset+100>=lastPage.total_issues;for(const input of list.querySelectorAll('input'))input.disabled=working||!!job?.running||!!job?.cancelled||!!job?.error}
  async function refresh(){clearTimeout(timer);const query=new URLSearchParams({offset,limit:100});if(job)query.set('id',job.id);const result=await request('status?'+query);if(closed)return;job=result;lastPage=result;
   status.textContent=result.phase+' · '+result.checked+'/'+result.total+' checked · '+result.missing+' unavailable · '+result.recoverable+' verified matches'+(result.searched?' · '+result.searched+' files searched':'')+(result.error?' · '+result.error:'');
   list.replaceChildren();for(const issue of result.issues){const row=make('article'),title=make('strong',issue.name);row.append(title,make('p',issue.collection),make('p',issue.problem+': '+issue.path));
    if(issue.recovered)row.append(make('p','Recovered to the expected location.'));
    else if(issue.candidate){const label=make('label'),check=make('input');check.type='checkbox';check.checked=selected.has(issue.id);check.setAttribute('aria-label','Recover '+issue.name);check.onchange=()=>{check.checked?selected.add(issue.id):selected.delete(issue.id);setControls()};label.append(check,document.createTextNode('Verified copy: '+issue.candidate));row.append(label)}
    list.append(row);
   }
   if(!result.running&&!result.total_issues&&!result.error)list.append(make('p','All checked originals are available.'));
   if(result.errors?.length)list.append(make('p','Some locations could not be searched. Details are included in the downloaded report.'));
   setControls();if(result.running)timer=setTimeout(()=>refresh().catch(e=>{if(!closed)status.textContent=e.message}),700);
  }
  controls.append(scan,stop,recover,download);const nav=make('div');nav.className='mfControls';nav.append(previous,next);
  const closeButton=btn('Close',close);panel.append(make('h2','Missing file finder'),closeButton,make('p','Checks originals in this library or the active organizer collection. To find copies, enter folders to search. Matching uses the saved file checksum.'),roots,controls,status,make('p','Recovery copies verified files back to their expected locations. Sets, stars and duplicate history keep their existing references.'),list,nav);wrap.append(style,panel);host.append(wrap);window.addEventListener('keydown',keys,true);closeButton.focus();setControls();refresh().catch(()=>{});
  return {close};
 };
})();
