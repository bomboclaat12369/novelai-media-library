// Integrate the six original approved repairs. No regeneration, crop or resampling.
const fs=require('fs'),path=require('path'),crypto=require('crypto');
const {createCanvas,loadImage}=require('@napi-rs/canvas');
const expected={
 'signature':'b9bc866fa3555b20d9375da833e8ecdc456ca2f1615975f1a3100feab94a94ee',
 'hall-of-fame':'014c8b1ef7858c33fe4e7abc3580ffa8797589b259ac219a5b71c2bf9c05ae08',
 'number-one':'5a1ab8d6a9e7fa906b5117f8b717c1a13bdc648b230b1f9fe0fffabe29476779',
 'valentines':'97e50cd663b70e2b512d1f0754c80aaf36e5f30d219895b637d2a67bc3e5a277',
 'christmas':'bfc9135864aa26dfcf9cc7236f7e34f8042951b606a43f724fd61390255ecae8',
 'whore-stage':'39cbcbda36118486c6291464b17a4bcdc68c59be98c7564dc75452daf1891d2e'
};
(async()=>{
 const directory=process.argv[2]||'assets/cards/editions/repairs/2026-11-04';
 for(const [id,hash] of Object.entries(expected)){
  const bytes=fs.readFileSync(path.join(directory,id+'.png'));
  if(crypto.createHash('sha256').update(bytes).digest('hex')!==hash)throw Error('Repair checksum mismatch: '+id);
  const im=await loadImage(bytes);if(im.width!==1049||im.height!==1499)throw Error('Unexpected repair dimensions');
  const c=createCanvas(1050,1500),ctx=c.getContext('2d');ctx.drawImage(im,0,0);
  fs.writeFileSync('assets/cards/editions/refined/'+id+'.png',c.toBuffer('image/png'));
  console.log(id+': approved pixels retained; transparent one-pixel canvas padding');
 }
})().catch(e=>{console.error(e.message);process.exitCode=1});
