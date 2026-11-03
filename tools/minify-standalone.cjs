// Compact the release only; retain readable source, global API names and function names.
const {minify}=require('terser');
let source='';process.stdin.setEncoding('utf8');process.stdin.on('data',chunk=>source+=chunk);
process.stdin.on('end',async()=>{
 try{
  const result=await minify(source,{compress:{passes:1},mangle:{toplevel:false},keep_fnames:true,keep_classnames:true,format:{comments:false,inline_script:true}});
  process.stdout.write(result.code);
 }catch(error){console.error(error);process.exitCode=1;}
});
