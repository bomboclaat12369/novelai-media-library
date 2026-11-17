'use strict';
// Optional local check. Read-only media; the launcher owns a separate review save.
const fs=require('node:fs'),crypto=require('node:crypto'),path=require('node:path');
const {chromium}=require('playwright');
(async()=>{
 const root=process.env.AFTER_HOURS_REVIEW_LIBRARY;
 if(!root)throw Error('Set AFTER_HOURS_REVIEW_LIBRARY to the read-only Library folder.');
 const digest=()=>Object.fromEntries(['library.json','battles.json'].map(name=>[name,crypto.createHash('sha256').update(fs.readFileSync(path.join(root,name))).digest('hex')]));
 const before=digest();
 const {url}=JSON.parse(fs.readFileSync('game/test-data/illustrated-preview/preview-server.json','utf8'));
 const browser=await chromium.launch({headless:true,executablePath:process.env.CHROME_EXE||'C:/Program Files/Google/Chrome/Application/chrome.exe'});
 try{
  const page=await browser.newPage({viewport:{width:1600,height:1000}}),errors=[];
  page.on('pageerror',error=>errors.push(error.message));
  await page.goto(url);
  await page.locator('.illustrated-venue').waitFor();
  const images=[];
  for(const room of ['room-0','room-1']){
   await page.locator('.illustrated-room[data-room="'+room+'"]').click();
   images.push(await page.locator('.booking-photo').evaluate(async img=>{await img.decode();return {width:img.naturalWidth,height:img.naturalHeight};}));
  }
  const boot=await (await page.request.get(url+'api/bootstrap')).json();
  const unowned=Object.values(boot.catalog.cards).find(card=>card.image&&card.available&&!boot.state.owned[card.id]);
  const denied=(await page.request.get(new URL('/game'+unowned.image,url).href)).status();
  const unchanged=JSON.stringify(before)===JSON.stringify(digest());
  if(!unchanged||errors.length||denied!==403||images.some(image=>!image.width))throw Error(JSON.stringify({unchanged,errors,denied,images}));
  const report={read_only_library:true,source_hashes_before:before,source_hashes_after:digest(),career:'Separate illustrated-preview career',catalog_characters:Object.keys(boot.catalog.people).length,catalog_cards:Object.keys(boot.catalog.cards).length,owned_cards:Object.keys(boot.state.owned).length,original_dimensions:images,unowned_http_status:denied,browser_errors:errors};
  fs.mkdirSync('.release-output/illustrated-venue',{recursive:true});
  fs.writeFileSync('.release-output/illustrated-venue/real-library-check.json',JSON.stringify(report,null,2));
  console.log(JSON.stringify({passed:true,characters:report.catalog_characters,cards:report.catalog_cards,originals:images,source_unchanged:unchanged}));
 }finally{await browser.close();}
})().catch(error=>{console.error(error.stack);process.exitCode=1;});
