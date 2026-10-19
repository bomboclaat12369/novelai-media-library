// Exercise the actual layout function without browser dependencies.
const fs=require('fs'),vm=require('vm'),assert=require('assert/strict');
const source=fs.readFileSync('payload/userscript-2.8.90.battles.txt','utf8');
const begin=source.indexOf('        function layout(){'),end=source.indexOf('        for(const [index,id]',begin);
const layout=source.slice(begin,end);
function fit(count,width,height,ratios=Array(count).fill(2/3)){
 const mosaic={isConnected:true,clientWidth:width,clientHeight:height,style:{}},images=ratios.map(r=>({naturalWidth:r*600,naturalHeight:600}));
 vm.runInNewContext(layout+';layout();',{count,mosaic,images});
 const cols=Number(mosaic.style.gridTemplateColumns.match(/repeat\((\d+)/)[1]),rows=Number(mosaic.style.gridTemplateRows.match(/repeat\((\d+)/)[1]);
 assert(cols*rows>=count);assert(cols>=1&&rows>=1);return {cols,rows};
}
assert.deepEqual(fit(4,600,520),{cols:2,rows:2});
assert.deepEqual(fit(1,600,520),{cols:1,rows:1});
for(const n of [2,3,5,6,7,8,9,10,11,12])for(const [w,h] of [[600,520],[820,830],[350,400]])fit(n,w,h);
fit(8,600,520,[1.5,1.5,2/3,2/3,1,1,1.8,.5]);
for(const n of [1,4,12,13,50,100]){const count=Math.min(12,n),indices=Array.from({length:count},(_,j)=>count===1?0:Math.round(j*(n-1)/(count-1)));assert.equal(new Set(indices).size,count);assert.equal(indices[0],0);if(n>1)assert.equal(indices.at(-1),n-1)}
console.log('Adaptive layout: 4-photo 2×2, mixed aspects, 1–12 visible images, compact/large panels, unique cover-to-last samples.');
