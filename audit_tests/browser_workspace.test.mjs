import assert from 'node:assert/strict';
import {Workspace} from '../chrome-extension/workspace.mjs';
let saved={},created=0,groups=0,attached=[],detached=[],draft=false;const tabs=new Map();
const chrome={storage:{session:{get:async()=>structuredClone(saved),set:async v=>{saved=structuredClone(v);}}},tabs:{
 get:async id=>{if(!tabs.has(id))throw Error('closed');return tabs.get(id);},
 create:async p=>{const t={...p,id:++created,windowId:1,groupId:-1,status:'complete'};tabs.set(t.id,t);return t;},
 group:async p=>{groups++;p.tabIds.forEach(id=>tabs.get(id).groupId=42);return 42;},
 update:async(id,p)=>Object.assign(tabs.get(id),p),
 sendMessage:async(id,msg)=>msg?.type==='clear-drafts'?(draft=false,{saved:[{label:'Ask anything',text:'old draft'}],left:0}):({elements:[{editable:true,disabled:false,empty:!draft}]})}};
const w=new Workspace(chrome,async a=>attached.push(a.tabId),async a=>detached.push(a.tabId));
let r=await w.inspect();assert.equal(created,2);assert.equal(groups,1);assert.ok(r.status.research.ready&&r.status.image.ready);
await w.inspect();assert.equal(created,2);assert.equal(groups,1);
await w.released(1);r=await w.inspect();assert.equal(r.status.research.ready,false);await w.reconnect();
await w.prepare('research','first');draft=true;const kept=await w.prepare('research','second');
assert.equal(draft,false,'leftover text cleared');assert.match(kept.savedText,/\[Ask anything\] old draft/,'and handed over to be saved');
tabs.get(1).url='https://example.com/';r=await w.inspect();assert.equal(r.status.research.ready,false);
tabs.delete(1);await w.ensure();assert.equal(created,3);assert.equal((await w.state()).image.tabId,2);
await w.release();assert.deepEqual(detached,[3,2]);
// A released job's generation may still show as running; the next job still gets a fresh chat.
draft=false;await w.prepare('research','third');
// 0.4.24: a work tab showing a loading error with its own Reload button is reloaded, at most every 2 minutes.
{
 let reloads=0,page={elements:[{editable:true,disabled:false,empty:true}],text:''};
 const tabs2=new Map();let made=0,store={};
 const c2={storage:{session:{get:async()=>structuredClone(store),set:async v=>{store=structuredClone(v);}}},tabs:{
  get:async id=>tabs2.get(id),create:async p=>{const t={...p,id:++made,windowId:1,groupId:7,status:'complete'};tabs2.set(t.id,t);return t;},
  group:async()=>7,update:async(id,p)=>Object.assign(tabs2.get(id),p),reload:async()=>{reloads++;},
  sendMessage:async id=>id===2?page:{elements:[{editable:true,disabled:false,empty:true}],text:''}}};
 const w2=new Workspace(c2,async()=>{},async()=>{});
 assert.ok((await w2.inspect()).status.image.ready);
 page={elements:[{role:'button',name:'Reload'},{role:'button',name:'Sign out'}],text:'We couldn\u2019t load your account Try reloading, or sign out and sign in again Reload Sign out'};
 let s=(await w2.inspect()).status;
 assert.equal(reloads,1);assert.equal(s.image.ready,false);assert.match(s.image.message,/Reloading/);assert.ok(s.research.ready,'the Gemini lane is unaffected');
 await w2.inspect();assert.equal(reloads,1,'not again within 2 minutes');
 page={elements:[],text:'Something went wrong in this report'};store.workspace.image.reloadedAt=0;
 await w2.inspect();assert.equal(reloads,1,'no Reload button: never reloaded on page text alone');
}
// 0.4.25: a replaced tab (no previous job on record) showing an old conversation still starts the job in a fresh chat;
// only this job's own unsent prompt may be left behind, never another draft.
{
 let page={elements:[{editable:true,disabled:false,empty:true}],prompt_verified:false};
 const tabs3=new Map();let made=0,store={};
 const c3={storage:{session:{get:async()=>structuredClone(store),set:async v=>{store=structuredClone(v);}}},tabs:{
  get:async id=>tabs3.get(id),create:async p=>{const t={...p,id:++made,windowId:1,groupId:9,status:'complete'};tabs3.set(t.id,t);return t;},
  group:async()=>9,update:async(id,p)=>Object.assign(tabs3.get(id),p),sendMessage:async()=>page}};
 const w3=new Workspace(c3,async()=>{},async()=>{});
 await w3.ensure();
 tabs3.get(1).url='https://gemini.google.com/app/f63e5685197b3e8a';  // the replaced tab shows a stuck conversation
 await w3.prepare('research','fresh-job','Research prompt');
 assert.equal(tabs3.get(1).url,'https://gemini.google.com/app','a fresh chat for the new job');
 tabs3.get(1).url='https://gemini.google.com/app/f63e5685197b3e8a';
 page={elements:[{editable:true,disabled:false,empty:false}],prompt_verified:true};  // this job's own unsent prompt
 await w3.prepare('research','next-job','Research prompt');
 assert.equal(tabs3.get(1).url,'https://gemini.google.com/app','its own unsent prompt does not block a fresh chat');
 page={elements:[{editable:true,disabled:false,empty:false}],prompt_verified:false};  // text the app did not type
 c3.tabs.sendMessage=async(id,msg)=>msg?.type==='clear-drafts'?{saved:[],left:1}:page;  // it cannot be cleared
 await assert.rejects(w3.prepare('research','third-job','Research prompt'),/could not be saved and cleared/);
}
console.log('Workspace checks passed: creation, reuse, grouping, release, reconnect, drafts, host guard, closed-tab replacement, load-error reload, fresh chat per job.');
