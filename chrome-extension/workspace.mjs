// MAINTAINER NOTE (2026-09-27): TAB OWNERSHIP: Local storage (kept across extension reloads; tab ids are revalidated) tracks extension-created work tabs, not personal tabs. Extension reload/update can invalidate old observers and tab ownership state. A queued capture_existing job uses its saved capture_tab_id to recover the original report; never substitute a blank/new tab silently. See ../docs/MAINTAINER_HANDOFF.md.
import {assertJobTab} from './policy.mjs';
import {isMissingObserver,reconnectObserver,withTimeout} from './observer.mjs';
// A provider page that failed to load, with its own Reload button (a person would press it; never Sign out).
const PAGE_LOAD_ERROR=/couldn.t load your account|something went wrong|an error occurred|unable to load|network error|try reloading/i;
const RELOAD_CONTROL=/^(?:reload|try again|retry)$/i;
const urls={research:'https://gemini.google.com/app',image:'https://chatgpt.com/'};
// Gemini runs in the Google account chosen in the app (e.g. https://gemini.google.com/u/1/app; owner request, 28 Sep 2026).
const GEMINI_ACCOUNT=/^https:\/\/gemini\.google\.com\/(?:u\/\d{1,2}\/)?app$/;
export class Workspace {
 constructor(chrome,attach,detach){this.chrome=chrome;this.attach=attach;this.detach=detach;this.area=chrome.storage.local||chrome.storage.session;}
 async state(){return (await this.area.get('workspace')).workspace||{};}
 async url(kind){
  if(kind!=='research')return urls[kind];
  const {researchUrl}=await this.area.get('researchUrl');
  return GEMINI_ACCOUNT.test(String(researchUrl||''))?researchUrl:urls.research;
 }
 async save(state){await this.area.set({workspace:state});}
 async ensure(){
  const state=await this.state();
  for(const kind of ['research','image']){
   let tab;try{if(state[kind])tab=await this.chrome.tabs.get(state[kind].tabId);}catch{}
   if(!tab){
    const other=state[kind==='research'?'image':'research'];let windowId;
    try{if(other)windowId=(await this.chrome.tabs.get(other.tabId)).windowId;}catch{}
    tab=await this.chrome.tabs.create({url:await this.url(kind),active:false,...(windowId===undefined?{}:{windowId})});
    state[kind]={tabId:tab.id};await this.save(state);
   }
  }
  const a=await this.chrome.tabs.get(state.research.tabId),b=await this.chrome.tabs.get(state.image.tabId);
  if(a.groupId<0||a.groupId!==b.groupId){
   try{state.groupId=await this.chrome.tabs.group({tabIds:[a.id,b.id],createProperties:{windowId:a.windowId}});state.groupError=null;}
   catch{state.groupError='Tabs are connected separately; grouping is unavailable.';}
  }
  await this.save(state);return state;
 }
 async inspect(){
  const state=await this.ensure(),status={};
  for(const kind of ['research','image']){
   const entry=state[kind],active={job:{kind},tabId:entry.tabId};
   try{
    const tab=await this.chrome.tabs.get(entry.tabId);assertJobTab(active.job,tab);
    if(entry.detached)throw new Error('Control released in Chrome. Click Connect both work tabs to reconnect.');
    if(tab.status!=='complete')throw new Error('Work tab is loading.');
    await this.attach(active);
    // Readiness reads controls only. It never types or clicks in either tab.
    let obs;
    try{obs=await withTimeout(this.chrome.tabs.sendMessage(entry.tabId,{type:'observe',prompt:''}),20000,'Work tab check');}
    catch(e){
     if(!isMissingObserver(e))throw e;
     if(await reconnectObserver(this.chrome,entry.tabId)==='reloaded')throw new Error('Work tab reconnecting after an update.');
     obs=await withTimeout(this.chrome.tabs.sendMessage(entry.tabId,{type:'observe',prompt:''}),20000,'Work tab check');
    }
    if(!obs||obs.error)throw new Error('Page observer unavailable. Reload this work tab.');
    const ready=obs.elements.some(e=>e.editable&&!e.disabled);
    if(!ready&&PAGE_LOAD_ERROR.test(String(obs.text||'').slice(-2000))&&obs.elements.some(e=>RELOAD_CONTROL.test(String(e.name||'').trim()))
       &&Date.now()-(entry.reloadedAt||0)>120000){
     entry.reloadedAt=Date.now();await this.save(state);await this.chrome.tabs.reload(entry.tabId);
     status[kind]={tab_id:entry.tabId,attached:true,ready:false,message:'Reloading: the page showed a loading error'};continue;
    }
    status[kind]={tab_id:entry.tabId,attached:true,ready,message:ready?'Connected · page controls ready':'Connected · sign-in or page setup may be needed'};
   }catch(e){status[kind]={tab_id:entry.tabId,attached:false,ready:false,message:String(e.message).slice(0,200)};}
  }
  return {state,status};
 }
 async prepare(kind,jobId,prompt=''){
  const state=await this.state(),entry=state[kind];if(!entry)throw new Error('Connect both work tabs first.');
  let savedText='';
  const tab=await this.chrome.tabs.get(entry.tabId);assertJobTab({kind},tab);
  // Every new job starts in a fresh chat, unless this is a brand-new tab already on it. (A replaced tab has no
  // previous job on record but may show any conversation, e.g. a stuck Deep Research.)
  const home=await this.url(kind);
  const onNewChat=String(tab.url||'').replace(/\/$/,'')===home.replace(/\/$/,'');
  if(entry.jobId!==jobId&&(entry.jobId||!onNewChat)){
   let obs;
   try{obs=await withTimeout(this.chrome.tabs.sendMessage(entry.tabId,{type:'observe',prompt}),20000,'Work tab check');}
   catch(e){
    if(!isMissingObserver(e))throw e;
    if(await reconnectObserver(this.chrome,entry.tabId)==='reloaded')throw new Error('Work tab reconnecting after an update.');
    obs=await withTimeout(this.chrome.tabs.sendMessage(entry.tabId,{type:'observe',prompt}),20000,'Work tab check');
   }
   if(!obs||obs.error)throw new Error('Cannot inspect the previous work tab.');
   // Unsent text the app did not type is saved to the article's history (the worker reports it), then cleared.
   // This job's own unsent prompt (an earlier attempt of the same job) is simply left behind with the old page.
   if(obs.elements.some(e=>e.editable&&!e.empty)&&!obs.prompt_verified){
    const cleared=await withTimeout(this.chrome.tabs.sendMessage(entry.tabId,{type:'clear-drafts'}),20000,'Saving leftover text');
    if(!cleared||cleared.error||cleared.left)throw new Error('The work tab contains text that could not be saved and cleared automatically. Clear it, then press Retry.');
    savedText=cleared.saved.map(d=>`[${d.label}] ${d.text}`).join('\n\n');
   }
   // The previous job is finished or released. If its generation still shows as running (e.g. a Deep Research
   // that was released after a timeout), leaving the page does not stop it: the provider keeps the
   // conversation, and its address is saved on that job for "Copy report again".
   await this.chrome.tabs.update(entry.tabId,{url:home});
  }
  entry.jobId=jobId;await this.save(state);return {tabId:entry.tabId,savedText};
 }
 async released(tabId){const state=await this.state();for(const kind of ['research','image'])if(state[kind]?.tabId===tabId)state[kind].detached=true;await this.save(state);}
 async reconnect(){const state=await this.state();for(const kind of ['research','image'])if(state[kind])state[kind].detached=false;await this.save(state);}
 async release(){const state=await this.state();for(const kind of ['research','image'])if(state[kind])await this.detach({tabId:state[kind].tabId});}
}
