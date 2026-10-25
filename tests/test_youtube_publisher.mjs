import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createHash,randomUUID,timingSafeEqual} from 'node:crypto';
if (!crypto.subtle.timingSafeEqual) crypto.subtle.timingSafeEqual=(a,b)=>timingSafeEqual(Buffer.from(a),Buffer.from(b));
const source=readFileSync(new URL('../worker/api.js',import.meta.url),'utf8').replace('import { DurableObject } from "cloudflare:workers";', 'class DurableObject { constructor(ctx,env){this.ctx=ctx;this.env=env;} }');
const {default:worker,YouTubePublisher}=await import('data:text/javascript;base64,'+Buffer.from(source).toString('base64'));
const C={tattoo:'UCQ8j4vfF-Oosb0PVlaXdvmA',vps:'UCfgVJrtBJSeViu95AnaQxyA'};
const media=Buffer.concat([Buffer.from([0,0,0,24]),Buffer.from('ftypisom'),Buffer.alloc(100)]);
const hash=s=>createHash('sha256').update(s).digest('hex');
class KV {
 constructor(){this.map=new Map()}
 async get(k,t){const v=this.map.get(k);return v==null?null:t==='json'?JSON.parse(v):v}
 async put(k,v){this.map.set(k,v)}
 async list({prefix}){return {keys:[...this.map.keys()].filter(k=>k.startsWith(prefix)).map(name=>({name})),list_complete:true}}
}
function storage(){let values=new Map();return {kv:{get:k=>structuredClone(values.get(k)),put:(k,v)=>values.set(k,structuredClone(v))},transactionSync(fn){const before=structuredClone(values);try{return fn()}catch(e){values=before;throw e}},async sync(){}}}
function job(channel='tattoo',operation='inspect',contentId='td-y001'){
 const token='a'.repeat(64),site=channel==='tattoo'?'https://www.tattoodoodle.com':'https://www.vpsdealswire.com';
 return {token,record:{id:randomUUID(),channel,operation,expectedChannelId:C[channel],expiresAt:new Date(Date.now()+3600000).toISOString(),tokenSha256:hash(token),contentId,
  videoUrl:site+(channel==='tattoo'?'/assets/videos/':'/videos/')+contentId+'.mp4',mediaSha256:hash(media),title:'A practical original tutorial',description:site+'/?utm_source=youtube&utm_medium=organic_video&utm_content='+contentId+'\nA useful reference guide.',publishAt:new Date(Date.now()+86400000).toISOString(),reviewed:true}};
}
function setup(){
 const SUBS=new KV(),objects=new Map();const env={SUBS,YT_CLIENT_ID:'client',YT_CLIENT_SECRET:'client-secret-placeholder',YT_REFRESH_TOKEN:'vps-refresh-placeholder',YT_REFRESH_TOKEN_TATTOO:'tattoo-refresh-placeholder'};
 env.YT_PUBLISHER={getByName(name){if(!objects.has(name))objects.set(name,new YouTubePublisher({storage:storage()},env));return objects.get(name)}};
 return {env,SUBS,objects};
}
async function call(s,j,header='Bearer '+j.token){await s.SUBS.put('yt:job:'+j.record.id,JSON.stringify(j.record));const r=await worker.fetch(new Request('https://www.vpsdealswire.com/api/youtube/jobs/'+j.record.id,{method:'POST',headers:{Authorization:header},body:JSON.stringify({channel:'attacker_cannot_override'})}),s.env,{});return {status:r.status,body:await r.json()}}
function api(channel='tattoo'){
 const state={channel,channelReturned:C[channel],init:0,put:0,tokens:[],videos:[],throwUpload:false,videoId:'AbCdEfGhI12',privacy:'private',processing:'processing',publishAt:null,meta:null,badHash:false,scope:'https://www.googleapis.com/auth/youtube'};
 const response=x=>new Response(JSON.stringify(x),{headers:{'Content-Type':'application/json'}});
 state.fetch=async(input,options={})=>{
  const u=String(input);
  if(u.includes('oauth2.googleapis.com')){state.tokens.push(new URLSearchParams(options.body).get('refresh_token'));return response({access_token:'access-placeholder',scope:state.scope})}
  if(u.includes('/youtube/v3/channels?'))return response({items:[{id:state.channelReturned,snippet:{title:'Expected channel'},contentDetails:{relatedPlaylists:{uploads:'uploads'}}}]});
  if(u.includes('/youtube/v3/playlistItems?'))return response({items:state.videos.map(v=>({contentDetails:{videoId:v.id}}))});
  if(u.includes('/youtube/v3/videos?part=snippet,status,processingDetails')){
   const ids=new URL(u).searchParams.get('id').split(',');return response({items:state.videos.filter(v=>ids.includes(v.id))});
  }
  if(u.startsWith('https://www.googleapis.com/upload/youtube/v3/videos?')){state.init++;state.meta=JSON.parse(options.body);state.publishAt=state.meta.status.publishAt;return new Response(null,{headers:{location:'https://www.googleapis.com/upload/session'}})}
  if(u==='https://www.googleapis.com/upload/session'){
   state.put++;if(state.throwUpload)throw new Error('timeout with unknown remote outcome');
   state.videos=[{id:state.videoId,snippet:{channelId:C[channel],title:state.meta.snippet.title,description:state.meta.snippet.description,publishedAt:'2026-10-25T00:00:00Z'},status:{privacyStatus:state.privacy,publishAt:state.publishAt,uploadStatus:'uploaded'},processingDetails:{processingStatus:state.processing}}];return response({id:state.videoId});
  }
  if(u.endsWith('.mp4'))return new Response(state.badHash?Buffer.concat([media,Buffer.from('changed')]):media,{headers:{'Content-Type':'video/mp4'}});
  if(u.startsWith('https://www.tattoodoodle.com/')||u.startsWith('https://www.vpsdealswire.com/'))return new Response('<h1>Live guide</h1>');
  throw new Error('Unexpected request '+u);
 };return state;
}
async function mock(a,fn){const old=globalThis.fetch;globalThis.fetch=a.fetch;try{return await fn()}finally{globalThis.fetch=old}}

test('job payload is management-owned; capabilities are required before OAuth or RPC',async()=>{
 const s=setup(),j=job();await mock({fetch(){throw Error('must not call')}},async()=>{
  assert.equal((await call(s,j,'')).status,401);assert.equal((await call(s,j,'Bearer '+'b'.repeat(64))).status,401);
 });assert.equal(s.objects.size,0);
});
test('both channel identities and inventory use the correct existing refresh token, without uploads',async()=>{
 for(const channel of ['tattoo','vps']){const s=setup(),j=job(channel),a=api(channel);await mock(a,async()=>{const r=await call(s,j);assert.equal(r.body.state,'channel_verified');assert.equal(r.body.channelId,C[channel]);assert.equal(r.body.inventoryComplete,true);assert.equal((await call(s,j)).body.state,'channel_verified')});assert.equal(a.init,0);assert.equal(a.tokens.length,1);assert.equal(a.tokens[0],channel+'-refresh-placeholder')}
});
test('unknown channel, wrong expected ID and expired envelopes cannot invoke Google',async()=>{
 for(const mutate of [j=>j.channel='typo',j=>j.expectedChannelId=C.vps,j=>j.expiresAt='2020-01-01']){const s=setup(),j=job();mutate(j.record);await mock({fetch(){throw Error('must not call')}},async()=>assert.notEqual((await call(s,j)).status,200));assert.equal(s.objects.size,0)}
});
test('wrong actual OAuth channel is a preflight failure, never an upload',async()=>{
 const s=setup(),j=job('tattoo','upload'),a=api();a.channelReturned=C.vps;await mock(a,async()=>{const r=await call(s,j);assert.equal(r.body.error,'channel_identity_mismatch');assert.equal(r.body.state,'preflight_failed')});assert.equal(a.init,0);
});
test('a read-only OAuth grant is identified and cannot submit an upload',async()=>{
 const s=setup(),a=api();a.scope='https://www.googleapis.com/auth/youtube.readonly';await mock(a,async()=>{assert.equal((await call(s,job())).body.uploadScopeGranted,false);assert.equal((await call(s,job('tattoo','upload'))).body.error,'youtube_upload_scope_missing')});assert.equal(a.init,0);
});
test('verified upload uses private native scheduling and reads back the actual video',async()=>{
 const s=setup(),j=job('tattoo','upload'),a=api();await mock(a,async()=>{const r=await call(s,j);assert.equal(r.body.state,'scheduled');assert.equal(r.body.videoId,a.videoId);assert.equal(r.body.channelId,C.tattoo);assert.equal(r.body.verifiedPublishAt,j.record.publishAt);assert.equal(r.body.actualPublishedAt,undefined);await call(s,j)});assert.equal(a.init,1);assert.equal(a.put,1);assert.equal(a.meta.status.privacyStatus,'private');assert.equal(a.meta.status.publishAt,j.record.publishAt);
});
test('two concurrent jobs for one content ID reserve at most one upload',async()=>{
 const s=setup(),j=job('tattoo','upload'),other=job('tattoo','upload'),a=api();await mock(a,async()=>{await Promise.all([call(s,j),call(s,other)])});assert.equal(a.init,1);assert.equal(a.put,1);
});
test('a changed source file is rejected before any YouTube write',async()=>{
 const s=setup(),j=job('tattoo','upload'),a=api();a.badHash=true;await mock(a,async()=>assert.equal((await call(s,j)).body.error,'media_hash_mismatch'));assert.equal(a.init,0);
});
test('a historical slug is blocked even when its old channel is unknown',async()=>{
 const s=setup(),j=job('tattoo','upload'),a=api();await s.SUBS.put('yt:last:old',JSON.stringify({slug:'td-y001'}));await mock(a,async()=>assert.equal((await call(s,j)).body.error,'legacy_slug_already_uploaded'));assert.equal(a.init,0);
});
test('identical bytes under a different content ID cannot upload again',async()=>{
 const s=setup(),first=job('tattoo','upload'),second=job('tattoo','upload','td-y002'),a=api();await mock(a,async()=>{await call(s,first);assert.equal((await call(s,second)).body.error,'duplicate_media_or_slug')});assert.equal(a.init,1);
});
test('an ambiguous upload is not retried; an existing matching video can be reconciled',async()=>{
 const s=setup(),j=job('tattoo','upload'),a=api();a.throwUpload=true;await mock(a,async()=>{
  assert.equal((await call(s,j)).body.state,'upload_uncertain');assert.equal((await call(s,job('tattoo','upload'))).body.error,'previous_attempt_requires_reconciliation');assert.equal(a.init,1);
  a.videos=[{id:a.videoId,snippet:{channelId:C.tattoo,title:j.record.title,description:j.record.description,publishedAt:'2026-10-25T00:00:00Z'},status:{privacyStatus:'private',publishAt:j.record.publishAt},processingDetails:{processingStatus:'processing'}}];
  assert.equal((await call(s,job('tattoo','verify'))).body.state,'scheduled');assert.equal(a.init,1);
 });
});
test('processing failure or missing native schedule is never reported published',async()=>{
 for(const failure of [true,false]){const s=setup(),j=job('tattoo','upload'),a=api();if(failure)a.processing='failed';await mock(a,async()=>{
  await call(s,j);if(!failure)delete a.videos[0].status.publishAt;
  const r=await call(s,job('tattoo','verify'));assert.equal(r.body.state,failure?'processing_failed':'uploaded_unverified');assert.equal(r.body.ok,false);
 })}
});
test('public readback records real publication and 7/28 day dates without another upload',async()=>{
 const s=setup(),j=job('tattoo','upload'),a=api();await mock(a,async()=>{
  await call(s,j);const obj=s.objects.get('tattoo'),asset=obj.ctx.storage.kv.get('asset:td-y001');asset.publishAt='2026-10-24T00:00:00Z';obj.ctx.storage.kv.put('asset:td-y001',asset);
  a.videos[0].status={privacyStatus:'public',uploadStatus:'processed'};a.videos[0].processingDetails.processingStatus='succeeded';
  const r=await call(s,job('tattoo','verify'));assert.equal(r.body.state,'published');assert.equal(r.body.actualPublishedAt,'2026-10-25T00:00:00.000Z');assert.equal(r.body.review7At,'2026-11-01T00:00:00.000Z');assert.equal(r.body.review28At,'2026-11-22T00:00:00.000Z');
 });assert.equal(a.init,1);
});
test('invalid UTM, unreviewed media and a past schedule fail before external calls',async()=>{
 for(const mutate of [j=>j.description='https://evil.example/',j=>j.reviewed=false,j=>j.publishAt='2026-01-01']){const s=setup(),j=job('tattoo','upload');mutate(j.record);await mock({fetch(){throw Error('must not call')}},async()=>assert.notEqual((await call(s,j)).status,200));assert.equal(s.objects.size,0)}
});
