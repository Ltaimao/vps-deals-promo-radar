import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
const source=readFileSync(new URL('../worker/api.js',import.meta.url));
const {default:worker}=await import('data:text/javascript;base64,'+source.toString('base64'));
class KV {
 constructor(){this.map=new Map();this.writes=[];}
 async get(key,type){const value=this.map.get(key);return value==null?null:type==='json'?JSON.parse(value):value;}
 async put(key,value,options={}){this.map.set(key,value);this.writes.push({key,value,options});}
 async delete(key){this.map.delete(key);}
 async list({prefix}){return {keys:[...this.map.keys()].filter(k=>k.startsWith(prefix)).map(name=>({name})),list_complete:true};}
}
const hash=createHash('sha256').update('vpsdw:test@example.com').digest('hex');
const ttl=30*24*60*60;
function request(){return new Request('https://www.vpsdealswire.com/api/subscribe',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({email:'test@example.com'})});}
async function withFetch(mock,body){const original=globalThis.fetch;globalThis.fetch=mock;try{await body();}finally{globalThis.fetch=original;}}

test('new and existing pending requests have TTL on email record and token',async()=>{
 for(const existing of [false,true]){
  const SUBS=new KV();
  if(existing)SUBS.map.set('sub:'+hash,JSON.stringify({status:'pending',email:'test@example.com',token:crypto.randomUUID(),created_at:'2026-10-01'}));
  await withFetch(async()=>new Response('{}'),async()=>{
   const response=await worker.fetch(request(),{SUBS,RESEND_API_KEY:'test-placeholder'},{});
   assert.equal((await response.json()).ok,true);
   assert.equal(SUBS.writes.find(w=>w.key==='sub:'+hash).options.expirationTtl,ttl);
   assert.equal(SUBS.writes.find(w=>w.key.startsWith('pending:')).options.expirationTtl,ttl);
  });
 }
});
test('confirmed subscribers are not given pending TTL or sent another confirmation',async()=>{
 const SUBS=new KV();SUBS.map.set('sub:'+hash,JSON.stringify({status:'active',email:'test@example.com'}));
 await withFetch(async()=>{throw Error('Must not send mail')},async()=>{
  const response=await worker.fetch(request(),{SUBS},{});assert.equal((await response.json()).ok,true);
  assert.ok(!SUBS.writes.some(w=>w.key==='sub:'+hash));
 });
});
test('confirmation turns expiring pending record into non-expiring active subscription',async()=>{
 const SUBS=new KV(),token=crypto.randomUUID();
 SUBS.map.set('pending:'+token,JSON.stringify({ehash:hash,email:'test@example.com'}));
 const response=await worker.fetch(new Request('https://www.vpsdealswire.com/api/confirm?token='+token),{SUBS},{});
 assert.equal(response.status,200);
 const write=SUBS.writes.find(w=>w.key==='sub:'+hash);assert.equal(JSON.parse(write.value).status,'active');
 assert.equal(write.options.expirationTtl,undefined);
});
async function scheduled(SUBS,deals,series,stamp){
 await withFetch(async url=>new Response(JSON.stringify(String(url).includes('offers.json')?{generated_at:stamp,deals}:{deal_series:series})),async()=>{
  let pending;await worker.scheduled({}, {SUBS},{waitUntil(p){pending=p;}});await pending;
 });
 return SUBS.map.get('meta:last_cron');
}
test('hourly, yearly, and unverified historical amounts cannot become monthly alerts',async()=>{
 const SUBS=new KV();
 const deals=['hour','year',undefined].map((billing_period,i)=>({offer_id:'key'+i,price:1,currency:'USD',billing_period}));
 await scheduled(SUBS,deals,{},'A');
 assert.ok(!SUBS.writes.some(w=>w.key.startsWith('dropwatch:')));
});
test('monthly alerts require different snapshot ids and verified same-currency monthly history',async()=>{
 const SUBS=new KV(),deal={offer_id:'key',price:5,currency:'USD',billing_period:'month'};
 const history={key:{points:[['old',100],['new',5]],monthly_points_by_currency:{USD:[['old',10],['new',5]]}}};
 assert.match(await scheduled(SUBS,[deal],history,'snapshot-A'),/confirmed=0/);
 assert.match(await scheduled(SUBS,[deal],history,'snapshot-A'),/confirmed=0/);
 assert.match(await scheduled(SUBS,[deal],history,'snapshot-B'),/confirmed=1/);
 const other=new KV();deal.currency='EUR';
 assert.match(await scheduled(other,[deal],history,'snapshot-B'),/confirmed=0/);
});

test('scheduled retention removes only provably expired legacy pending records',async()=>{
 const SUBS=new KV();
 const expiredToken=crypto.randomUUID();
 SUBS.map.set('sub:expired',JSON.stringify({status:'pending',created_at:'2020-01-01',token:expiredToken}));
 SUBS.map.set('pending:'+expiredToken,'{}');
 SUBS.map.set('sub:recent',JSON.stringify({status:'pending',created_at:new Date().toISOString()}));
 SUBS.map.set('sub:undated',JSON.stringify({status:'pending'}));
 SUBS.map.set('sub:active',JSON.stringify({status:'active',email:'test@example.com',created_at:'2020-01-01'}));
 assert.match(await scheduled(SUBS,[],{},'retention-test'),/expired_pending=1/);
 assert.ok(!SUBS.map.has('sub:expired'));
 assert.ok(!SUBS.map.has('pending:'+expiredToken));
 assert.ok(SUBS.map.has('sub:recent'));
 assert.ok(SUBS.map.has('sub:undated'));
 assert.ok(SUBS.map.has('sub:active'));
});
