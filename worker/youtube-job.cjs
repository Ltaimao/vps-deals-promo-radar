#!/usr/bin/env node
// No API credential extraction. Creates a short-lived management-owned job and
// invokes it with a private capability using a real browser when needed by WAF.
const fs=require('fs'),path=require('path'),crypto=require('crypto');
const args=process.argv.slice(2),command=args[0];
const option=name=>{const n=args.indexOf('--'+name);return n<0?undefined:args[n+1]};
const channels={tattoo:'UCQ8j4vfF-Oosb0PVlaXdvmA',vps:'UCfgVJrtBJSeViu95AnaQxyA'};
function privatePath(file){if(!file)throw Error('output_file_required');const p=path.resolve(file),repo=path.resolve(__dirname,'..');if(p===repo||p.startsWith(repo+path.sep))throw Error('capability_file_must_be_outside_repository');return p}
function write(file,data){fs.writeFileSync(file,JSON.stringify(data,null,2)+'\n',{mode:0o600});fs.chmodSync(file,0o600)}
async function main(){
 if(command==='create'){
  const channel=option('channel'),operation=option('operation'),out=privatePath(option('output'));
  if(!Object.hasOwn(channels,channel)||!['inspect','upload','verify'].includes(operation))throw Error('explicit_channel_and_operation_required');
  const manifest=option('manifest')?JSON.parse(fs.readFileSync(option('manifest'),'utf8')):{};
  if(operation==='upload'){
   if(!option('media'))throw Error('reviewed_local_media_required');
   const bytes=fs.readFileSync(option('media'));const sha=crypto.createHash('sha256').update(bytes).digest('hex');
   if(manifest.mediaSha256!==sha||manifest.reviewed!==true||bytes.length>24*1024*1024)throw Error('reviewed_media_hash_or_size_invalid');
  }
  const capability=crypto.randomBytes(32).toString('hex');
  const envelope={...manifest,id:crypto.randomUUID(),channel,operation,expectedChannelId:channels[channel],expiresAt:new Date(Date.now()+3600000).toISOString(),tokenSha256:crypto.createHash('sha256').update(capability).digest('hex')};
  if(operation==='verify')envelope.contentId=option('content-id');
  write(out,{capability,envelope});console.log(JSON.stringify({created:true,jobId:envelope.id,channel,operation,privateFile:out}));return;
 }
 if(command==='invoke'){
  const file=privatePath(option('job')),input=JSON.parse(fs.readFileSync(file,'utf8'));
  if(!/^[a-f0-9-]{36}$/.test(input.envelope.id)||!/^[a-f0-9]{64}$/.test(input.capability))throw Error('bad_capability_file');
  const {chromium}=require('playwright');
  const browser=await chromium.launch({executablePath:process.env.CHROMIUM_PATH||'/usr/bin/chromium',headless:true,args:['--no-sandbox']});
  try{
   const page=await browser.newPage();
   await page.goto('https://www.vpsdealswire.com/?utm_source=internal_qa&utm_medium=validation',{waitUntil:'domcontentloaded'});
   const result=await page.evaluate(async({id,token})=>{const r=await fetch('/api/youtube/jobs/'+id,{method:'POST',headers:{Authorization:'Bearer '+token},signal:AbortSignal.timeout(240000)});return {httpStatus:r.status,...await r.json()};},{id:input.envelope.id,token:input.capability});
   const out=option('result')?privatePath(option('result')):file+'.result.json';write(out,result);
   console.log(JSON.stringify({httpStatus:result.httpStatus,ok:result.ok,state:result.state,error:result.error,channel:result.channel,channelId:result.channelId,videoId:result.videoId,inventoryCount:result.videos?.length,publicVideos:result.videos?.filter(v=>v.privacy==='public').length,nonPublicVideos:result.videos?.filter(v=>v.privacy!=='public').length,resultFile:out}));
  }finally{await browser.close()}
  return;
 }
 throw Error('use_create_or_invoke');
}
main().catch(error=>{console.error(/^[a-z0-9_]+$/.test(error.message)?error.message:'operation_failed_check_private_record_before_retry');process.exit(1)});
