// MAINTAINER NOTE (2026-09-27): CONTROLLER LOOP: Owns dedicated tabs, exactly-once prompt submission and saved active-job state. One active job per work tab (research lane and image/SEO lane); an attention job pauses only its own lane. Do not auto-resubmit an uncertain Send. Read ../docs/MAINTAINER_HANDOFF.md before changing recovery.
import {exportAction,validateCopiedReport} from './research-export.mjs';
import {assertJobTab,validateAction} from './policy.mjs';
import {Workspace} from './workspace.mjs';
import {isMissingObserver,reconnectObserver,withTimeout} from './observer.mjs';
const BASE='http://127.0.0.1:8001/api/browser-worker';
const VERSION='0.4.33';
chrome.storage.local.setAccessLevel({accessLevel:'TRUSTED_CONTEXTS'});
const attached=new Set();const images=new Map();let busy=false;let timer;
const workspace=new Workspace(chrome,attach,detach);
const tabKind=kind=>kind==='research'?'research':'image';let workspaceChecked=0;
async function workspaceSync(force=false){
 const config=await chrome.storage.local.get(['workspaceEnabled','workspaceStatus']);
 let status=config.workspaceStatus||{};
 if(force||Date.now()-workspaceChecked>15000){
  if(config.workspaceEnabled!==false)status=(await workspace.inspect()).status;
  else status={};
  await chrome.storage.local.set({workspaceStatus:status});workspaceChecked=Date.now();
  const reply=await api('/workspace',{tabs:status});
  if(reply.latest_version&&reply.latest_version!==VERSION){
   // The app copies new extension files into this folder on start; reload once to run them.
   const {reloadedFor}=await chrome.storage.local.get('reloadedFor');
   if(reloadedFor!==reply.latest_version){await chrome.storage.local.set({reloadedFor:reply.latest_version,message:'Updating to '+reply.latest_version+'…'});chrome.runtime.reload();return false;}
  }
  if(reply.research_url){
   // The app chose a Google account for Gemini: new research chats open there; an idle work tab moves over now.
   const {researchUrl}=await chrome.storage.local.get('researchUrl');
   if(researchUrl!==reply.research_url&&/^https:\/\/gemini\.google\.com\//.test(reply.research_url)){
    await chrome.storage.local.set({researchUrl:reply.research_url});
    const state=await workspace.state();
    if(researchUrl&&!(await getActive('research'))&&state.research?.tabId)await chrome.tabs.update(state.research.tabId,{url:reply.research_url}).catch(()=>{});
   }
  }
  if(reply.command){
   const command=reply.command;
   if(command.action==='connect'){await chrome.storage.local.set({workspaceEnabled:true});await workspace.reconnect();}
   else{await chrome.storage.local.set({workspaceEnabled:false});await workspace.release();}
   await api('/workspace/ack',{id:command.id});workspaceChecked=0;
   return false;
  }
 }
 // Each lane needs only its own work tab (Gemini for research, ChatGPT for SEO and images).
 return {research:!!status.research?.ready,image:!!status.image?.ready};
}
async function autoPair(){
 // Local app issues a token only to this extension on loopback; no code to type.
 try{const r=await api('/auto-pair',{});await chrome.storage.local.set({token:r.token,message:'Paired automatically',workspaceEnabled:true});workspaceChecked=0;return true;}
 catch(e){await chrome.storage.local.set({message:'Not paired: '+e.message});return false;}
}
async function api(path,body){
 const {token}=await chrome.storage.local.get('token');
 const r=await fetch(BASE+path,{method:body===undefined?'GET':'POST',headers:{'Content-Type':'application/json',Authorization:'Bearer '+(token||''),'X-Bridge-Version':VERSION},body:body===undefined?undefined:JSON.stringify(body),signal:AbortSignal.timeout(50000)});
 if(r.status===401&&path!=='/pair'){await chrome.storage.local.remove('token');await chrome.storage.local.set({workspaceEnabled:false,workspaceStatus:{}});await workspace.release();}
 if(!r.ok)throw new Error((await r.json()).detail||'Connection failed');return r.json();
}
async function send(active,msg){
 assertJobTab(active.job,await chrome.tabs.get(active.tabId));
 let r;
 try{r=await withTimeout(chrome.tabs.sendMessage(active.tabId,msg),30000,'Page helper');}
 catch(e){
  if(!isMissingObserver(e))throw e;
  if(await reconnectObserver(chrome,active.tabId)==='reloaded')throw new Error('Page observer reconnecting after an update (page reloaded).');
  r=await withTimeout(chrome.tabs.sendMessage(active.tabId,msg),30000,'Page helper');
 }
 if(r?.error)throw new Error(r.error);if(!r)throw new Error('Reload the job tab to load the updated page observer.');return r;
}
async function command(active,method,params={}){
 assertJobTab(active.job,await chrome.tabs.get(active.tabId));
 return withTimeout(chrome.debugger.sendCommand({tabId:active.tabId},method,params),20000,'Browser command '+method);
}
async function attach(active){
 assertJobTab(active.job,await chrome.tabs.get(active.tabId));
 if(attached.has(active.tabId))return;
 // An existing attachment may survive a service-worker restart. Probe before attaching.
 try{await command(active,'Page.getLayoutMetrics');}
 catch(e){if(/timed out/.test(e.message))throw e;await chrome.debugger.attach({tabId:active.tabId},'1.3');}
 attached.add(active.tabId);await command(active,'Network.enable',{maxTotalBufferSize:16000000,maxResourceBufferSize:10000000});
 // Never let a native file dialog open in a work tab (it would block the page and cannot be controlled).
 await command(active,'Page.setInterceptFileChooserDialog',{enabled:true}).catch(()=>{});
 // Keep the work tab rendering (and focused) while Chrome shows another tab or window: a hidden page pauses the
 // animation-frame work that e.g. ChatGPT's Send waits on. Clicks and typing still happen inside the page.
 await command(active,'Emulation.setFocusEmulationEnabled',{enabled:true}).catch(()=>{});
}
async function detach(active){if(active?.tabId){attached.delete(active.tabId);await chrome.debugger.detach({tabId:active.tabId}).catch(()=>{});images.delete(active.tabId);}}
chrome.debugger.onEvent.addListener((source,method,p)=>{
 if(!attached.has(source.tabId)||method!=='Network.responseReceived'||p.type!=='Image'||!p.response.mimeType.startsWith('image/'))return;
 const list=images.get(source.tabId)||[];list.push({url:p.response.url,id:p.requestId});images.set(source.tabId,list.slice(-40));
});
chrome.debugger.onDetach.addListener(async source=>{
 if(!attached.has(source.tabId))return;
 attached.delete(source.tabId);
 await workspace.released(source.tabId);
 for(const lane of LANES){const active=await getActive(lane);if(active?.tabId===source.tabId){active.detached=true;await setActive(lane,active);await chrome.storage.local.set({message:'Browser control detached. Use Continue to reconnect.'});}}
});
async function click(active,point){
 // The page helper clicks the control it prepared (checked: same control, nothing covering it). Debugger
 // mouse input (and evaluation) stalled on Gemini's report page; it remains only for an older page helper.
 if(point.token){await send(active,{type:'click',token:point.token});return;}
 await command(active,'Input.dispatchMouseEvent',{type:'mousePressed',x:point.x,y:point.y,button:'left',clickCount:1});
 await command(active,'Input.dispatchMouseEvent',{type:'mouseReleased',x:point.x,y:point.y,button:'left',clickCount:1});
}
// "Copy report again" (owner report, 28 Sep 2026): Gemini shows a finished Deep Research report only in the tab that
// watched it (a freshly loaded conversation shows it frozen), and that tab may no longer be the work tab. Look for an
// open Gemini tab on one of the article's recorded conversations that shows Share & Export. Never reload such a tab.
const bare=url=>String(url||'').replace(/[?#].*$/,'').replace(/\/$/,'');
async function openReportTab(job){
 const wanted=new Set((job.capture_candidates||[]).map(bare));
 if(!wanted.size)return null;
 for(const tab of await chrome.tabs.query({url:'https://gemini.google.com/*'})){
  if(!wanted.has(bare(tab.url)))continue;
  const look=()=>withTimeout(chrome.tabs.sendMessage(tab.id,{type:'observe',prompt:job.prompt}),15000,'Report search');
  let obs=null;
  try{obs=await look();}
  catch(e){
   if(!isMissingObserver(e))continue;
   try{await chrome.scripting.executeScript({target:{tabId:tab.id},files:['content.js']});obs=await look();}catch{continue;}
  }
  if(obs&&!obs.error&&obs.elements.some(e=>!e.disabled&&/share\s*(?:&|and)\s*export/i.test(String(e.name||''))))return tab.id;
 }
 return null;
}
// Chrome can replace a tab with a new id (e.g. a discarded tab brought back): keep following the work tab and any job.
chrome.tabs.onReplaced?.addListener(async(added,removed)=>{
 const state=await workspace.state();let changed=false;
 for(const kind of ['research','image'])if(state[kind]?.tabId===removed){state[kind].tabId=added;changed=true;}
 if(changed)await workspace.save(state);
 attached.delete(removed);
 for(const lane of LANES){const active=await getActive(lane);if(active?.tabId===removed){active.tabId=added;await setActive(lane,active);}}
});
async function verifyPrompt(active,prompt){
 // Read-only retries: never insert a second copy or erase an existing draft.
 for(let attempt=0;attempt<10;attempt++){
  if((await send(active,{type:'observe',prompt})).prompt_verified)return true;
  if(attempt<9)await new Promise(resolve=>setTimeout(resolve,300));
 }
 return false;
}
// Two lanes run side by side: Gemini Deep Research in the research tab, ChatGPT SEO/thumbnail
// jobs in the image tab. Each lane keeps its own saved active job, so a job needing attention in
// one tab never blocks the other.
const LANES=['research','image'];
const laneKey=lane=>'active:'+lane;
async function getActive(lane){return (await chrome.storage.local.get(laneKey(lane)))[laneKey(lane)];}
async function setActive(lane,active){await chrome.storage.local.set({[laneKey(lane)]:active});}
async function clearActive(lane){await chrome.storage.local.remove(laneKey(lane));}
async function allActive(){return Object.fromEntries(await Promise.all(LANES.map(async lane=>[lane,await getActive(lane)])));}
async function migrateActive(){
 // Before 0.4.0 a single saved job served both tabs.
 const {active}=await chrome.storage.local.get('active');
 if(active){if(!(await getActive(tabKind(active.job.kind))))await setActive(tabKind(active.job.kind),active);await chrome.storage.local.remove('active');}
}
async function tick(){
 if(busy)return;busy=true;
 try{
  await migrateActive();
  const {token}=await chrome.storage.local.get('token');if(!token&&!(await autoPair()))return;
  const workspaceReady=await workspaceSync();
  for(const lane of LANES)await tickLane(lane,workspaceReady);
 }catch(e){await chrome.storage.local.set({message:String(e.message||'Browser controller failed').slice(0,300)});}
 finally{busy=false;clearTimeout(timer);timer=setTimeout(tick,2500);}
}
async function tickLane(lane,workspaceReady){
 let active=await getActive(lane);
 try{
  if(!active){
   if(!workspaceReady?.[lane])return;
   const {job}=await api('/claim',{lane});if(!job)return;
   const state=await workspace.state();
   let captureTab=job.capture_tab_id,navigateTo=job.capture_existing&&job.capture_url||null;
   if(job.capture_existing){
    // The finished report may be open only in an earlier Gemini tab: copy it there, without reloading it.
    const found=await openReportTab(job).catch(()=>null);
    if(found){captureTab=found;navigateTo=null;await api('/jobs/'+job.id,{message:'Copying the finished report from the open Gemini tab that shows it'}).catch(()=>{});}
   }
   // A re-copy job runs in the existing Gemini work tab: treat that tab as a work tab (never close it).
   const inWorkTab=!job.capture_existing||[state.research?.tabId,state.image?.tabId].includes(captureTab);
   active={job,navigateTo,tabId:job.capture_existing?captureTab:state[tabKind(job.kind)].tabId,workspace:inWorkTab,needsPrepare:!job.capture_existing,exportPhase:null,filled:!!job.capture_existing,submitted:!!job.capture_existing,steps:0,protocol:2};
   await setActive(lane,active);return;
  }
  let job=await api('/jobs/'+active.job.id);
  if(['cancelled','completed','consumed'].includes(job.status)){
   // Closing a dedicated cancelled tab prevents further controller actions; work tabs are kept.
   if(!active.workspace||job.status==='cancelled')await detach(active);
   if(job.status==='cancelled'&&active.tabId&&!active.workspace)await chrome.tabs.remove(active.tabId).catch(()=>{});
   await clearActive(lane);workspaceChecked=0;return;
  }
  if(active.tabId&&!(await chrome.tabs.get(active.tabId).catch(()=>null))){
   // The job's tab is gone, so Continue can never succeed and would block this lane.
   if(active.workspace&&!active.submitted){
    // Nothing was sent yet: safe to restart this job in the current work tab.
    const state=await workspace.ensure();
    Object.assign(active,{tabId:state[tabKind(job.kind)].tabId,needsPrepare:true,pending:null,detached:false,steps:0});
    await setActive(lane,active);
    if(job.status==='attention')await api('/jobs/'+job.id+'/resume',{});
    return;
   }
   // A prompt was already sent in the closed tab; never resend it automatically.
   await api('/jobs/'+job.id+'/cancel',{reason:'Work tab was closed after sending; its result is lost. Select Retry in the workbench to run it again.'}).catch(()=>{});
   await clearActive(lane);workspaceChecked=0;return;
  }
  if(job.status==='attention')return;
  if((await chrome.storage.local.get('workspaceEnabled')).workspaceEnabled===false)return;
  if(active.protocol!==2)throw new Error('This job started in the old extension. Inspect its tab, then stop this browser job and retry from the workbench. It will not be resubmitted automatically.');
  if(!active.tabId)throw new Error('Tab creation had an uncertain outcome. Cancel this job before retrying.');
  if(active.pending)throw new Error('Last browser action had an uncertain outcome. Inspect the tab and use Continue; it will not be repeated automatically.');
  if(active.detached)throw new Error('Chrome browser control was detached. Use Continue to reconnect.');
  if(active.needsPrepare){
   const prepared=await workspace.prepare(tabKind(job.kind),job.id,job.prompt);
   // Leftover text found in the work tab was cleared; the app keeps it in full in the article's history.
   if(prepared?.savedText)await api('/jobs/'+job.id,{message:'Saved the text found in the work tab to the article history, then cleared it',saved_text:prepared.savedText.slice(0,20000)});active.needsPrepare=false;await setActive(lane,active);return;}
  if(active.navigateTo){
   // Re-copy: reopen the exact Gemini conversation that holds this article's report.
   const target=new URL(active.navigateTo);
   if(target.protocol!=='https:'||target.hostname!=='gemini.google.com')throw new Error('Refusing to open a non-Gemini report address.');
   await chrome.tabs.update(active.tabId,{url:target.href});
   active.navigateTo=null;active.readyAfter=Date.now()+10000;await setActive(lane,active);
   await api('/jobs/'+job.id,{message:'Opening the saved Gemini conversation'});return;
  }
  if(active.readyAfter&&Date.now()<active.readyAfter)return;
  await attach(active);
  if(active.exportPhase){
   await chrome.tabs.update(active.tabId,{active:true});
   const exportObs=await send(active,{type:'observe',prompt:job.prompt});
   if(active.exportPhase==='copy'&&exportObs.copied_message)return;
   // The export menu may already be open (e.g. after a retry): go straight to Copy contents.
   if(active.exportPhase==='menu'){try{exportAction(exportObs,'copy');active.exportPhase='copy';}catch{}}
   let step;
   try{step=exportAction(exportObs,active.exportPhase);}
   catch(e){
    // The full report (or its export menu) is not open: hand back to the planner, which opens it,
    // instead of stopping the job. Repeated misses still ask the owner.
    active.exportMisses=(active.exportMisses||0)+1;
    if(active.exportMisses>4)throw e;
    active.exportPhase=null;active.lastFingerprint=null;await setActive(lane,active);
    await api('/jobs/'+job.id,{message:'Opening the full Gemini report before copying it'});
    return;
   }
   if(step.action==='wait'){await api('/jobs/'+job.id,{message:step.reason});return;}
   const point=await send(active,{type:'prepare',snapshot:exportObs.snapshot,target:step.target,action:'click'});
   if((await api('/jobs/'+job.id)).status!=='running')return;
   await click(active,point);
   if(active.exportPhase==='menu'){active.exportPhase='copy';await setActive(lane,active);return;}
   await new Promise(resolve=>setTimeout(resolve,1000));
   // Read only after the observed Copy contents control was clicked.
   let copied,via='Share & Export → Copy contents';
   try{copied=(await send(active,{type:'copied-report'})).result;}
   catch{copied=(await send(active,{type:'report-text',prompt:job.prompt})).result;via='the open report panel (clipboard unavailable)';}
   const result=validateCopiedReport(copied,/kannada|ಕನ್ನಡ/i.test(job.prompt));
   await api('/jobs/'+job.id,{message:'Completed report saved from '+via,result});
   active.exportPhase=null;active.exportMisses=0;await setActive(lane,active);return;
  }
  const obs=await send(active,{type:'observe',prompt:job.prompt});
  obs.filled=active.filled||obs.prompt_verified;obs.submitted=active.submitted;
  active.filled=obs.filled;
  // The thinking level shows only in the open menu's status, outside the observed text: a level step is a change too.
  const fingerprint=JSON.stringify([obs.text,obs.elements,obs.filled,obs.submitted,obs.effort]);
  if(active.lastFingerprint===fingerprint&&active.lastAction==='wait'&&Date.now()-(active.lastPlan||0)<30000)return;
  if(active.lastFingerprint===fingerprint&&active.lastAction!=='wait')active.unchanged=(active.unchanged||0)+1;else active.unchanged=0;
  if(active.unchanged>=3)throw new Error('The page did not change after three actions. Inspect the job tab before continuing.');
  // A low-resolution screenshot helps interpret icon-only controls. It is not stored server-side.
  // Optional: Chrome does not paint a page it is not showing, so it may never arrive; the rules do not need it.
  const shot=obs.visible===false?null:await withTimeout(command(active,'Page.captureScreenshot',{format:'jpeg',quality:40,captureBeyondViewport:false}),5000,'Screenshot').catch(()=>null);
  if(shot?.data&&shot.data.length<2500000)obs.screenshot=shot.data;
  await chrome.storage.local.set({message:'Inspecting page and choosing the next action'});
  const d=validateAction(await api('/jobs/'+job.id+'/observe',obs),obs,active);
  // Check Stop immediately before execution, after the model request.
  job=await api('/jobs/'+job.id);if(job.status!=='running')return;
  active.lastFingerprint=fingerprint;active.lastAction=d.action;active.lastPlan=Date.now();active.steps++;
  if(d.action==='attention'){await setActive(lane,active);return;}
  if(d.action==='reload_page'){
   // Refresh a stale conversation view; the conversation itself is kept by the provider.
   await chrome.tabs.reload(active.tabId);active.readyAfter=Date.now()+15000;active.lastFingerprint=null;
   await setActive(lane,active);return;
  }
  // The app gives slower (higher thinking level) image jobs a longer limit.
  if(d.action==='wait'&&job.kind==='image'&&active.submittedAt&&Date.now()-active.submittedAt>(job.wait_limit_seconds||300)*1000)throw new Error('Generation wait limit reached. Inspect the job tab; no duplicate prompt was sent.');
  if(['level_up','level_down','close_menu'].includes(d.action)){
   // ChatGPT's thinking level: one arrow-key step on its "Power" menu item, or Escape to close the menu.
   await send(active,{type:'level-key',snapshot:obs.snapshot,target:d.target,key:{level_up:'ArrowRight',level_down:'ArrowLeft',close_menu:'Escape'}[d.action]});
   active.readyAfter=Date.now()+700;await setActive(lane,active);return;
  }
  if(['click','fill_prompt','submit'].includes(d.action)){
   const point=await send(active,{type:'prepare',snapshot:obs.snapshot,target:d.target,action:d.action});
   active.pending=d.action;if(d.action==='submit'){if(active.submitted)active.resent=true;active.submitted=true;active.submittedAt=Date.now();}
   await setActive(lane,active);
   await click(active,point);
   if(d.action==='submit'&&point.token){
    // Sending clears the composer. Still holding the prompt means the click was ignored: press Enter there.
    await new Promise(resolve=>setTimeout(resolve,1500));
    if((await send(active,{type:'observe',prompt:job.prompt})).prompt_verified)await send(active,{type:'press-enter'});
   }
   if(d.action==='fill_prompt'){
    // Typed by the page helper; debugger text input only if the editor ignored it (composer still empty).
    const typed=point.token?await send(active,{type:'type',token:point.token,text:job.prompt}):null;
    if(!typed||typed.empty)await command(active,'Input.insertText',{text:job.prompt});
    if(!await verifyPrompt(active,job.prompt))throw new Error('Prompt insertion could not be verified after waiting for the editor. Inspect the composer; no prompt was sent.');
    active.filled=true;
   }
   active.pending=null;
  }else if(d.action.startsWith('scroll_'))await send(active,{type:'scroll',direction:d.action==='scroll_up'?'up':'down'});
  else if(d.action==='collect_report'&&job.kind==='seo'){
   const answer=await send(active,{type:'extract',snapshot:obs.snapshot,target:d.target,action:'collect_report'});
   await api('/jobs/'+job.id,{message:'SEO assets collected from ChatGPT',result:answer.result});
  }else if(d.action==='collect_report'){
   // Read the finished report straight from its open panel (headings, tables and source links kept): no
   // clipboard, window focus or menu clicks. Share & Export -> Copy remains the fallback.
   let report=null;
   try{report=validateCopiedReport((await send(active,{type:'report-text',prompt:job.prompt})).result,/kannada|ಕನ್ನಡ/i.test(job.prompt));}catch{}
   if(report)await api('/jobs/'+job.id,{message:'Completed report saved from the open report panel',result:report});
   else{active.exportPhase='menu';await api('/jobs/'+job.id,{message:'Report ready; opening Share & Export to copy the complete report'});}
  }else if(d.action==='collect_image'){
   const image=await send(active,{type:'extract',snapshot:obs.snapshot,target:d.target,action:d.action});
   const network=(images.get(active.tabId)||[]).findLast(i=>i.url===image.url);let result;
   if(network){try{const body=await command(active,'Network.getResponseBody',{requestId:network.id});if(body.base64Encoded)result=body.body;}catch{}}
   if(!result)result=(await send(active,{type:'fetch-image',snapshot:obs.snapshot,target:d.target})).result;
   await api('/jobs/'+job.id,{message:'Generated image retrieved; preparing 16:9 thumbnail',result});
  }
  await setActive(lane,active);await chrome.storage.local.set({message:d.reason});
 }catch(e){
  const message=String(e.message||'Browser controller failed').slice(0,300);await chrome.storage.local.set({message});
  if(active?.job?.id){
   const transient=/control changed|observation expired|Another control covers|reconnecting|timed out|signal is aborted|Failed to fetch|NetworkError/i.test(message) && !active.pending;
   active.staleRetries=transient?(active.staleRetries||0)+1:0;
   await setActive(lane,active);
   await api('/jobs/'+active.job.id,{message:transient?('Page changed; inspecting it again - '+message).slice(0,300):message,attention:!(transient&&active.staleRetries<=2)}).catch(()=>{});
  }
 }
}
chrome.alarms.create('poll',{periodInMinutes:0.5});chrome.alarms.onAlarm.addListener(tick);chrome.runtime.onStartup.addListener(tick);chrome.runtime.onInstalled.addListener(tick);
chrome.runtime.onMessage.addListener((msg,sender,reply)=>{
 if(sender.tab||sender.id!==chrome.runtime.id)return;
 (async()=>{
  if(msg.type==='pair'){const r=await api('/pair',{code:msg.code});await chrome.storage.local.set({token:r.token,message:'Paired'});await tick();return {ok:true};}
  await migrateActive();
  const actives=await allActive();
  const running=LANES.filter(lane=>actives[lane]);
  const statuses=Object.fromEntries(await Promise.all(running.map(async lane=>[lane,(await api('/jobs/'+actives[lane].job.id).catch(()=>({}))).status])));
  const needingAttention=running.filter(lane=>statuses[lane]==='attention');
  if(msg.type==='connect-workspace'){await chrome.storage.local.set({workspaceEnabled:true});await workspace.reconnect();workspaceChecked=0;await tick();return {ok:true};}
  if(msg.type==='release-workspace'){await chrome.storage.local.set({workspaceEnabled:false});for(const lane of running)await api('/jobs/'+actives[lane].job.id+'/cancel',{});await workspace.release();workspaceChecked=0;await tick();return {ok:true};}
  if(msg.type==='show-research'||msg.type==='show-image'){const state=await workspace.state();const entry=state[msg.type==='show-research'?'research':'image'];if(entry)await chrome.tabs.update(entry.tabId,{active:true});return {ok:true};}
  if(msg.type==='workspace-status')return {status:(await chrome.storage.local.get('workspaceStatus')).workspaceStatus||{}};
  if(msg.type==='poll'){
   for(const lane of running){const active=actives[lane];if(statuses[lane]==='attention')await api('/jobs/'+active.job.id+'/resume',{});active.pending=null;active.detached=false;active.unchanged=0;await setActive(lane,active);}
   await tick();return {ok:true};
  }
  if(msg.type==='stop'){for(const lane of (needingAttention.length?needingAttention:running))await api('/jobs/'+actives[lane].job.id+'/cancel',{});await tick();return {ok:true};}
  if(msg.type==='open'){const lane=needingAttention[0]||running[0];if(lane&&actives[lane].tabId)await chrome.tabs.update(actives[lane].tabId,{active:true});return {ok:true};}
  if(msg.type==='collect'){
   const lane=msg.image?'image':(actives.research?'research':'image');const active=actives[lane];
   if(!active)throw new Error('No active job');
   if(!!msg.image!==(active.job.kind==='image'))throw new Error('Return the result type requested by the active job.');
   const result=msg.image?{result:msg.image,message:'Image returned by editor'}:await send(active,{type:'collect'});
   await api('/jobs/'+active.job.id,result);await tick();return {ok:true};
  }
 })().then(reply).catch(e=>reply({error:e.message}));return true;
});
