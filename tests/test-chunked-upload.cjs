const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const {webcrypto, createHash} = require('node:crypto');
const repo = path.resolve(__dirname,'..');
const config = JSON.parse(fs.readFileSync(path.join(repo,process.env.NAI_RELEASE_CONFIG || 'release-userscript.json')));
const source = fs.readFileSync(path.join(repo,config.parts.find(p=>p.endsWith('.review-core.txt'))),'utf8');
const code = source.slice(source.indexOf('  let chunkUploadsAvailable'),source.indexOf('  async function uploadFileResilient'));

function fixture({stall=false, retry=false}={}) {
  const events=[], received=[], progress={textContent:''};
  let offset=0, drops=0;
  const context=vm.createContext({Blob,Uint8Array,crypto:webcrypto,performance,console,
    btoa:s=>Buffer.from(s,'binary').toString('base64'),
    setTimeout:fn=>setTimeout(fn,stall ? 20 : 5000),clearTimeout,
    API:'http://127.0.0.1:8765',activeUploadHandle:null,importToken274:()=> 'nai_fixture_123456789',
    formatBytes:n=>String(n),modalRoot:{querySelector:()=>progress},
    gmRequest:async options=>{events.push({action:'cleanup',options}); return {};},
    GM_xmlhttpRequest:options=>{
      const action=options.url.split('/').at(-1), body=options.data ? JSON.parse(options.data) : null;
      events.push({action,body});
      assert.ok(!options.data || Buffer.byteLength(options.data)<3*1024*1024);
      let aborted=false;
      setImmediate(()=>{
        if (aborted || (stall && action==='chunk')) return;
        let result={};
        if(action==='health') result={chunked_uploads:true};
        if(action==='start') result={offset:0};
        if(action==='chunk') {
          const bytes=Buffer.from(body.data,'base64');
          assert.equal(createHash('sha256').update(bytes).digest('hex'),body.sha256);
          if(body.offset===offset) {received.push(bytes); offset+=bytes.length;}
          else assert.equal(body.offset+bytes.length,offset);
          if(retry && drops++===0) {options.onerror(); return;}
          result={offset};
        }
        if(action==='finish') result={item:{id:'saved'}};
        options.onload({status:200,responseText:JSON.stringify(result)});
      });
      return {abort(){aborted=true; options.onabort();}};
    }});
  vm.runInContext(code+'\nthis.upload = uploadFileChunked;',context);
  return {context,events,received,progress};
}

function file(size) {
  const bytes=Buffer.alloc(size); for(let i=0;i<size;i++) bytes[i]=i%256;
  const blob=new Blob([bytes],{type:'video/mp4'});blob.name='test.mp4';return {blob,bytes};
}

test('file over 64 MiB is transported as bounded verified chunks without changing bytes',async()=>{
  const f=fixture(), {blob,bytes}=file(66*1024*1024+13);
  const result=await f.context.upload(blob,'character',[], '');
  assert.equal(result.item.id,'saved');
  assert.deepEqual(Buffer.concat(f.received),bytes);
  assert.equal(f.events.filter(e=>e.action==='chunk').length,34);
  assert.equal(f.events.filter(e=>e.action==='finish').length,1);
  assert.equal(f.context.activeUploadHandle,null);
});

test('a lost chunk acknowledgment retries identical bytes at the same offset',async()=>{
  const f=fixture({retry:true}), {blob,bytes}=file(3*1024*1024);
  await f.context.upload(blob,'character',[]);
  assert.deepEqual(Buffer.concat(f.received),bytes);
  const chunks=f.events.filter(e=>e.action==='chunk');
  assert.equal(chunks.length,3); assert.equal(chunks[0].body.offset,chunks[1].body.offset);
});

test('X cancels pending chunk, requests cleanup and does not finish the file',async()=>{
  const f=fixture({stall:true}), {blob}=file(3*1024*1024);
  const pending=f.context.upload(blob,'character',[]);
  const rejection=assert.rejects(pending,/Import canceled/);
  while(!f.events.some(e=>e.action==='chunk')) await new Promise(r=>setImmediate(r));
  f.context.activeUploadHandle.abort();
  await rejection;
  assert.equal(f.events.filter(e=>e.action==='cleanup').length,1);
  assert.equal(f.events.filter(e=>e.action==='finish').length,0);
  assert.equal(f.context.activeUploadHandle,null);
});

test('missing extension callbacks eventually reject and clean up without requiring X',async()=>{
  const f=fixture({stall:true}), {blob}=file(3*1024*1024);
  await assert.rejects(f.context.upload(blob,'character',[]),/stopped responding/);
  assert.equal(f.events.filter(e=>e.action==='chunk').length,2);
  assert.equal(f.events.filter(e=>e.action==='cleanup').length,1);
  assert.equal(f.context.activeUploadHandle,null);
});
