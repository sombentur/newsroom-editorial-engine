export function assertJobTab(job,tab){
 const u=new URL(tab.url||'');const host=job.kind==='research'?'gemini.google.com':'chatgpt.com';
 if(u.protocol!=='https:'||u.hostname!==host||u.port)throw new Error('Job tab left its permitted website. Complete sign-in yourself.');
}
export function validateAction(d,obs,state){
 if(!['click','fill_prompt','submit','scroll_down','scroll_up','wait','collect_report','collect_image','attention','reload_page','level_up','level_down','close_menu'].includes(d.action))throw new Error('Unsupported browser action');
 if(['level_up','level_down','close_menu'].includes(d.action)){
  // ChatGPT's thinking level is set only before the prompt is entered.
  if(state.filled||state.submitted)throw new Error('The thinking level is set only before the prompt is entered');
  if(d.action!=='close_menu'){
   const e=obs.elements.find(e=>e.id===d.target);
   if(!e||e.disabled||e.role!=='menuitem'||String(e.name||'').trim().toLowerCase()!=='power')throw new Error('Target is not the thinking-level control');
  }
  return d;
 }
 if(d.action==='fill_prompt'&&state.submitted)throw new Error('Duplicate submission prevented');
 // Sending clears the composer: a prompt still in it was not sent, so exactly one more Send is allowed.
 if(d.action==='submit'&&state.submitted&&!(obs.prompt_verified&&!state.resent))throw new Error('Duplicate submission prevented');
 if(['click','fill_prompt','submit','collect_report','collect_image'].includes(d.action)){
  const e=obs.elements.find(e=>e.id===d.target);
  if(!e||e.disabled)throw new Error('Target is not in the current observation');
  if(d.action==='fill_prompt'&&(!e.editable||!e.empty))throw new Error('Existing text will not be overwritten');
  if(d.action==='submit'&&(!state.filled||!obs.prompt_verified))throw new Error('Prompt has not been verified');
  if(['click','submit'].includes(d.action)&&(!['button','menuitem','menuitemcheckbox','menuitemradio','option','tab','radio','checkbox','switch'].includes(e.role)||/\b(sign in|log in|upgrade|buy|subscribe|delete|share|publish|password|account settings)\b/i.test(e.name)))throw new Error('Control is outside the job scope');
  if(d.action==='click'&&/^(send|send message|send prompt|submit|submit prompt)$/i.test(e.name.trim()))throw new Error('Use duplicate-protected submission');
 }
 return d;
}
