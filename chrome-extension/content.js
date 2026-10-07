// MAINTAINER NOTE (2026-09-27): LIVE PAGE ADAPTER: Observe current DOM controls; prepare revalidates identity before input. Existing tabs may need refresh after extension reload to install this observer. Clipboard reads belong only to the explicit Gemini Copy content path, after its UI confirmation. See ../docs/MAINTAINER_HANDOFF.md.
// Observes live controls; the server selects an element ID, never JavaScript.
(() => {
  let current = null;
  const shown = e => e && e.isConnected && e.getClientRects().length && getComputedStyle(e).visibility !== 'hidden';
  const name = e => (e.getAttribute('aria-label') || e.getAttribute('title') || e.getAttribute('placeholder') || e.innerText || e.alt || '').trim().slice(0,400);
  const editable = e => e.matches('textarea,[contenteditable="true"],[role="textbox"]') && e.getAttribute('type') !== 'password';
  // Only text a person (or the app) typed counts as composer content. ChatGPT renders the chosen tool ("Create image")
  // and attachments as non-editable chips inside the message box, and other extensions add buttons there: no draft.
  const DECOR='[contenteditable="false"],button,[role="button"],img,svg,[aria-hidden="true"],[class*="quillbot" i],[id*="quillbot" i],grammarly-extension';
  // Like innerText: inline text nodes join verbatim (a link or bold span splits one line into several nodes),
  // block elements and <br> start a new line, hidden nodes and decorations are left out.
  const BLOCK=/^(?:P|DIV|LI|UL|OL|BR|TR|H[1-6]|PRE|BLOCKQUOTE|SECTION|ARTICLE)$/;
  const typed = e => {
    if (typeof e.value === 'string') return e.value;
    let text='';
    const walker=document.createTreeWalker(e,NodeFilter.SHOW_ELEMENT|NodeFilter.SHOW_TEXT,{acceptNode:n=>n.nodeType===1?((n.matches(DECOR)||getComputedStyle(n).display==='none')?NodeFilter.FILTER_REJECT:NodeFilter.FILTER_ACCEPT):NodeFilter.FILTER_ACCEPT});
    for(let n=walker.nextNode();n;n=walker.nextNode()){
      if(n.nodeType===1){if(n!==e&&BLOCK.test(n.tagName))text+='\n';}
      else text+=n.nodeValue;
    }
    return text;
  };
  const value = e => typed(e).trim();
  // The decoration text itself (tool chips such as "Create image", attachment names): reported so the app can see a
  // chosen tool without a labelled Remove button.
  const chips = e => typeof e.value === 'string' ? '' : [...e.querySelectorAll(DECOR)].map(d => (d.innerText || d.getAttribute('aria-label') || '').trim()).filter(Boolean).join(' | ');
  // Rich-text editors may turn line breaks into paragraphs or non-breaking spaces.
  // Compare every word and punctuation mark; only whitespace layout is ignored.
  const canonical = text => text.replace(/\s+/gu,' ').trim();
  const matchesPrompt = (el,prompt) => editable(el) && !!canonical(prompt) && canonical(value(el))===canonical(prompt);
  // Gemini shows a finished Deep Research report in a side panel, not in a chat reply: the nearest large
  // container around its Share & Export button, and the largest report block inside it (never the chat).
  function reportPanel(prompt) {
    const share=[...document.querySelectorAll('button,[role="button"]')].find(b=>/share\s*(?:&|and)\s*export/i.test(name(b))&&shown(b));
    let panel=share&&share.parentElement;
    while(panel&&panel!==document.body&&(panel.innerText||'').length<2000)panel=panel.parentElement;
    if(!share||!panel||panel===document.body)return null;
    const start=String(prompt||'').trim().slice(0,80);
    const largest=selector=>[...panel.querySelectorAll(selector)]
      .filter(e=>!e.contains(share)&&(e.textContent||'').length>2000&&shown(e)&&!(start&&e.innerText.trim().startsWith(start)))
      .sort((a,b)=>b.innerText.length-a.innerText.length)[0];
    return {share,panel,body:largest('[class*="markdown"]')||largest('article,[role="document"],section,div')||null};
  }
  // A ChatGPT answer carries its own action bar ("Read aloud", "Regenerate response"). The answer is the largest
  // text block beside the latest bar that does not contain the job's prompt (independent of page markup).
  const ANSWER_BAR=/^(?:read aloud|regenerate(?: response)?)$/i;
  // The user's own messages (ChatGPT renders them as markdown too): never an answer.
  const USER_MESSAGE='[data-user-message-bubble],[data-markdown-text-tone="user-message"],[data-message-author-role="user"],[data-turn="user"]';
  const inUserMessage=e=>!!(e.closest(USER_MESSAGE)||e.querySelector(USER_MESSAGE));
  function answerBar(){return [...document.querySelectorAll('button,[role="button"]')].reverse().find(b=>ANSWER_BAR.test(name(b))&&shown(b))||null;}
  function answerBlock(prompt,bar){
    let box=bar.parentElement;
    while(box&&box!==document.body&&(box.innerText||'').length<300)box=box.parentElement;
    if(!box||box===document.body)return null;
    const opening=canonical(String(prompt||'')).slice(0,80);
    return [...box.querySelectorAll('div,section,article,pre,p')]
      .filter(e=>!e.contains(bar)&&(e.textContent||'').length>150&&shown(e)&&!inUserMessage(e)&&!(opening&&canonical(e.innerText).includes(opening)))
      .sort((a,b)=>b.innerText.length-a.innerText.length)[0]||null;
  }
  // Compact outline of the elements around an anchor (tag.class[data/role]:text length) to diagnose page changes.
  function outline(el){
    const parts=[];
    for(let e=el,i=0;e&&e!==document.body&&i<14;e=e.parentElement,i++){
      const cls=typeof e.className==='string'?e.className.trim().split(/\s+/).slice(0,2).join('.'):'';
      const data=[...(e.attributes||[])].filter(a=>/^data-|^role$/.test(a.name)).slice(0,3).map(a=>a.name+'='+String(a.value).slice(0,24)).join(',');
      parts.push(e.tagName.toLowerCase()+(cls?'.'+cls:'')+(data?'['+data+']':'')+':'+(e.innerText||'').length);
    }
    return parts.join(' < ').slice(0,700);
  }
  // The report's own title is shown in the panel toolbar beside Share & Export, not in the report body.
  function panelTitle({share,panel}){
    for(let bar=share.parentElement,i=0;bar&&bar!==panel&&i<6;bar=bar.parentElement,i++){
      const c=bar.cloneNode(true);
      c.querySelectorAll('button,[role="button"],mat-icon,[class*="-symbols"],[class*="visually-hidden"],[aria-hidden="true"]').forEach(e=>e.remove());
      const title=(c.textContent||'').replace(/\s+/g,' ').trim();
      if(title)return title.length<=200?title:'';
    }
    return '';
  }
  function snapshot(prompt) {
    const nodes=[]; const seen=new Set();
    function add(e,role) {
      if (!shown(e) || seen.has(e) || nodes.length>=240 || e.closest('nav,[role="navigation"]')) return;
      if(e.matches('input[type="password"],input[type="email"]'))return;
      seen.add(e);nodes.push({el:e,role,label:name(e)});
    }
    const CONTROLS='button,[role="button"],[role="menuitem"],[role="menuitemcheckbox"],[role="menuitemradio"],[role="option"],[role="tab"],[role="radio"],[role="checkbox"],[role="switch"],textarea,[contenteditable="true"],[role="textbox"]';
    const repeats={};
    function addControl(e){
      if(seen.has(e)||nodes.length>=200)return;  // leave room for report and image elements
      const label=name(e);
      // A finished Deep Research report carries dozens of identical source chips ("Learn More"); a few are enough.
      if((repeats[label]||0)>=5)return;
      const before=nodes.length;add(e,editable(e)?'textbox':e.getAttribute('role')||'button');
      if(nodes.length>before)repeats[label]=(repeats[label]||0)+1;
    }
    // Open menus and dialogs first (Gemini renders them at the end of the page), so items such as
    // Share & Export -> Copy contents are never cut off by a long report.
    document.querySelectorAll('.cdk-overlay-container,[role="menu"],[role="dialog"],[role="listbox"]').forEach(o=>o.querySelectorAll(CONTROLS).forEach(addControl));
    document.querySelectorAll(CONTROLS).forEach(addControl);
    // Answers: provider message markers, plus the "markdown" blocks both providers render answers in.
    const reports=[...document.querySelectorAll('model-response .markdown,model-response message-content,[data-message-author-role="assistant"],[data-turn="assistant"] [class*="markdown" i],[class*="markdown" i],main article,[role="main"] article,[role="document"]')].filter(e=>shown(e)&&e.innerText.length>500);
    // Never the job's own message: the SEO prompt itself names every answer key (e.g. "seo_title").
    const opening=canonical(String(prompt||'')).slice(0,80);
    const ownMessage=e=>inUserMessage(e)||(opening&&canonical(e.innerText).includes(opening));
    reports.filter(e=>!ownMessage(e)&&!reports.some(other=>other!==e&&e.contains(other))).slice(-4).forEach(e=>add(e,'report'));
    const deep=reportPanel(prompt);if(deep?.body)add(deep.body,'report');
    const bar=answerBar(),answer=bar&&answerBlock(prompt,bar);if(answer)add(answer,'report');
    document.querySelectorAll('main img,[role="main"] img,[role="dialog"] img,[data-message-author-role="assistant"] img').forEach(e=>{if(e.naturalWidth>=512&&e.naturalHeight>=256)add(e,'image');});
    const id=crypto.randomUUID(); current={id,nodes,prompt};
    const effort=thinkingLevel();
    const main=document.querySelector('main,[role="main"]');
    const pageText=(main?.innerText || document.body.innerText).slice(-18000);
    return {effort,hint:bar?outline(answer||bar):undefined,visible:document.visibilityState==='visible',copied_message:/\b(?:content )?copied(?: to clipboard)?\b/i.test(document.body.innerText),snapshot:id,url:location.href,text:pageText,elements:nodes.map((n,i)=>({id:i+1,role:n.role,name:n.label,disabled:!!n.el.disabled||n.el.getAttribute('aria-disabled')==='true',editable:editable(n.el),empty:!value(n.el),draft:editable(n.el)?value(n.el).slice(0,200):undefined,chips:editable(n.el)?chips(n.el).slice(0,200):undefined,selected:['aria-selected','aria-checked','aria-pressed'].some(a=>n.el.getAttribute(a)==='true')})),prompt_verified:nodes.some(n=>matchesPrompt(n.el,prompt))};
  }
  // ChatGPT's thinking level: the open model menu's live status ("High, 3 of 5."), else the composer's model button.
  const POWER='[role="menuitem"][aria-label="Power"],[role="menuitem"][data-reasoning-slider]';
  function thinkingLevel(){
    if(location.hostname!=='chatgpt.com')return null;
    const power=[...document.querySelectorAll(POWER)].find(shown);
    if(power){
      const status=[...document.querySelectorAll('[role="status"]')].map(e=>(e.innerText||'').trim()).find(t=>/,\s*\d+\s+of\s+\d+\.?$/.test(t));
      if(status)return status.replace(/,\s*\d+\s+of\s+\d+\.?$/,'').trim().slice(0,40);
    }
    const pill=[...document.querySelectorAll('button[aria-label="Select ChatGPT model"]')].find(shown);
    return pill?((pill.innerText||'').trim().slice(0,40)||null):null;
  }
  // One arrow-key step on the "Power" item (checked: the observed control), or Escape to close the open menu.
  function levelKey(msg){
    const codes={ArrowLeft:37,ArrowRight:39,Escape:27};
    if(!(msg.key in codes))throw new Error('Unsupported key.');
    let el=document.activeElement||document.body;
    if(msg.key!=='Escape'){
      el=target(msg).el;
      if(!el.matches(POWER))throw new Error('The thinking-level control changed. Inspect again.');
      el.focus();
    }
    const key={key:msg.key,code:msg.key,keyCode:codes[msg.key],which:codes[msg.key],bubbles:true,cancelable:true,composed:true};
    el.dispatchEvent(new KeyboardEvent('keydown',key));el.dispatchEvent(new KeyboardEvent('keyup',key));
    return {ok:true};
  }
  function target(msg) {
    if(!current||msg.snapshot!==current.id)throw new Error('Page observation expired. Inspect again.');
    const node=current.nodes[msg.target-1];
    if(!node)throw new Error('The control changed. Inspect again.');
    // React can replace the composer while the controller is thinking. Recover
    // only the same observed DOM id; never guess a different field by position.
    if(!node.el.isConnected && node.el.id){
      const replacement=document.getElementById(node.el.id);
      if(replacement && replacement.tagName===node.el.tagName && editable(replacement) && editable(node.el))node.el=replacement;
    }
    if(!shown(node.el)||(!editable(node.el)&&node.label!==name(node.el)))throw new Error('The control changed. Inspect again.');
    return node;
  }
  function prepare(msg){
    const {el,role}=target(msg);
    if(el.disabled||el.getAttribute('aria-disabled')==='true')throw new Error('Control is disabled.');
    if(role==='report'||role==='image')throw new Error('This result is not a clickable control.');
    if(msg.action==='fill_prompt'&&(!editable(el)||value(el)))throw new Error('Composer is not empty.');
    if(msg.action==='submit'&&!current.nodes.some(n=>shown(n.el)&&matchesPrompt(n.el,current.prompt)))throw new Error('Prompt text changed before sending.');
    el.scrollIntoView({block:'center',inline:'nearest'});
    const r=el.getBoundingClientRect();const x=r.x+r.width/2,y=r.y+r.height/2;
    const hit=document.elementFromPoint(x,y);
    if(hit&&!(el===hit||el.contains(hit))&&hit.closest&&hit.closest('.cdk-overlay-backdrop')){
      // An open menu's transparent backdrop covers the page: close the menu, as clicking outside it would.
      hit.closest('.cdk-overlay-backdrop').click();
      throw new Error('Another control covers the target (an open menu, now closed). Inspect the page again.');
    }
    if(!hit||!(el===hit||el.contains(hit))){
      // Name what is on top (tag, classes, label) so a stuck page can be diagnosed from the app.
      const who=hit?(hit.tagName||'').toLowerCase()+(typeof hit.className==='string'&&hit.className?'.'+hit.className.trim().split(/\s+/).slice(0,2).join('.'):'')+(hit.getAttribute&&hit.getAttribute('aria-label')?' "'+hit.getAttribute('aria-label').slice(0,40)+'"':''):'nothing';
      throw new Error('Another control covers the target ('+who+'). Inspect the page again.');
    }
    // One-time mark: the page helper clicks (and types into) this exact control.
    document.querySelectorAll('[data-newsroom-target]').forEach(e=>e.removeAttribute('data-newsroom-target'));
    const token=crypto.randomUUID();el.setAttribute('data-newsroom-target',token);
    return {x,y,token,visible:document.visibilityState==='visible'};
  }
  // Clicks and typing happen here, inside the page: debugger-driven input (and even evaluation) stalled on
  // Gemini's report page while this helper kept answering. prepare() has already checked the control.
  function marked(token){
    const el=document.querySelector('[data-newsroom-target="'+String(token).replace(/[^\w-]/g,'')+'"]');
    if(!el)throw new Error('The control changed. Inspect again.');
    return el;
  }
  function clickMarked(msg){
    const el=marked(msg.token);
    const r=el.getBoundingClientRect();
    const at={bubbles:true,cancelable:true,composed:true,view:window,clientX:r.left+r.width/2,clientY:r.top+r.height/2,button:0};
    const pointer={...at,pointerId:1,pointerType:'mouse',isPrimary:true};
    el.dispatchEvent(new PointerEvent('pointerdown',{...pointer,buttons:1}));
    el.dispatchEvent(new MouseEvent('mousedown',{...at,buttons:1}));
    // A synthetic click does not move focus: put the caret in a composer before text is inserted.
    if(editable(el))el.focus();
    el.dispatchEvent(new PointerEvent('pointerup',{...pointer,buttons:0}));
    el.dispatchEvent(new MouseEvent('mouseup',{...at,buttons:0}));
    el.click();
    if(!editable(el))el.removeAttribute('data-newsroom-target');  // a composer keeps its mark for typing
    return {ok:true};
  }
  function typeMarked(msg){
    const el=marked(msg.token);el.removeAttribute('data-newsroom-target');
    if(!editable(el)||value(el))throw new Error('Composer is not empty.');
    el.focus();
    // Return empty so worker.js uses Input.insertText (Chrome DevTools keyboard simulation).
    // execCommand() updates the DOM but skips React's synthetic event system on ChatGPT/Gemini;
    // the send button then submits React's empty internal state, delivering a blank message.
    return {ok:false,empty:true};
  }
  // Sending clears the composer. If the Send click was ignored, press Enter in the composer that still holds
  // exactly the job's prompt (from the latest observation), as a person would.
  function pressEnter(){
    const node=current&&current.nodes.find(n=>shown(n.el)&&matchesPrompt(n.el,current.prompt));
    if(!node)return {ok:false};
    node.el.focus();
    const key={key:'Enter',code:'Enter',keyCode:13,which:13,bubbles:true,cancelable:true,composed:true};
    for(const type of ['keydown','keypress','keyup'])node.el.dispatchEvent(new KeyboardEvent(type,key));
    return {ok:true};
  }
  // Unsent text the app did not type (a restored draft, or another extension's box): returned so the app saves it to
  // the article's history, then cleared so the job can start. Password fields are never touched.
  const TEXT_BOXES='textarea,[contenteditable="true"],[role="textbox"]';
  function clearDrafts(){
    const saved=[];
    for(const el of document.querySelectorAll(TEXT_BOXES)){
      if(!shown(el)||!editable(el)||!value(el))continue;
      saved.push({label:String(el.getAttribute('aria-label')||el.getAttribute('placeholder')||el.id||el.tagName.toLowerCase()).slice(0,80),text:value(el).slice(0,20000)});
      el.focus();
      if(typeof el.select==='function')el.select();else document.execCommand('selectAll',false);
      document.execCommand('delete',false);
    }
    return {saved,left:[...document.querySelectorAll(TEXT_BOXES)].filter(el=>shown(el)&&editable(el)&&value(el)).length};
  }
  function collect(msg){
    const {el,role}=target(msg);
    if(msg.action==='collect_image'){
      if(role!=='image'||!el.complete)throw new Error('The generated image is not ready.');
      return {url:el.currentSrc||el.src,width:el.naturalWidth,height:el.naturalHeight};
    }
    if(role!=='report')throw new Error('No report selected.');
    const links=[...el.querySelectorAll('a[href^="https://"]')].map(a=>`${a.textContent}: ${a.href}`);
    return {result:el.innerText+'\n\nPROVIDER CITATION LINKS — use only these exact URLs for sources and claim_evidence; do not invent links:\n'+links.join('\n')};
  }
  chrome.runtime.onMessage.addListener((msg,sender,reply)=>{
    if(sender.id!==chrome.runtime.id)return;
    try{
      if(msg.type==='copied-report'){
        if(location.hostname!=='gemini.google.com')throw new Error('Report export is only available in Gemini.');
        if(!/\b(?:content )?copied(?: to clipboard)?\b/i.test(document.body.innerText))throw new Error('Gemini has not confirmed Copy content. No clipboard content was read.');
        (async()=>{
          // Gemini's plain-text copy loses every line break; its HTML copy keeps headings, lists and links.
          try{for(const item of await navigator.clipboard.read()){if(item.types.includes('text/html'))return reply({result:await (await item.getType('text/html')).text(),format:'html'});}}catch{}
          reply({result:await navigator.clipboard.readText(),format:'text'});
        })().catch(()=>reply({error:'Chrome did not allow reading Copy content. Accept the extension clipboard permission and keep Gemini active.'}));return true;
      }
      if(msg.type==='report-text'){
        if(location.hostname!=='gemini.google.com')throw new Error('Report text is only read from Gemini.');
        // Only the open report panel: never the chat, the page's hidden headings or the whole conversation.
        const deep=reportPanel(msg.prompt);
        if(!deep)throw new Error('The full report is not open. Open it, then use Continue.');
        const report=(deep.body||deep.panel).cloneNode(true);
        // Keep headings, lists, tables and source links; drop controls, icon ligatures and screen-reader-only text.
        report.querySelectorAll('button,[role="button"],mat-icon,svg,style,script,noscript,template,input,textarea,[hidden],[class*="visually-hidden"],[class*="sr-only"],[class*="-symbols"],[class*="material-icons"]').forEach(e=>e.remove());
        const title=panelTitle(deep).replace(/[&<>"]/g,ch=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'})[ch]);
        reply({result:(title?'<h1>'+title+'</h1>':'')+report.innerHTML,format:'html'});
      }
      else if(msg.type==='observe')reply(snapshot(msg.prompt));
      else if(msg.type==='prepare')reply(prepare(msg));
      else if(msg.type==='click')reply(clickMarked(msg));
      else if(msg.type==='type')reply(typeMarked(msg));
      else if(msg.type==='press-enter')reply(pressEnter());
      else if(msg.type==='level-key')reply(levelKey(msg));
      else if(msg.type==='clear-drafts')reply(clearDrafts());
      else if(msg.type==='extract')reply(collect(msg));
      else if(msg.type==='scroll'){const main=document.querySelector('main,[role="main"]');const e=main&&main.scrollHeight>main.clientHeight?main:document.scrollingElement;e.scrollBy(0,msg.direction==='up'?-600:600);reply({ok:true});}
      else if(msg.type==='collect'){const result=getSelection()?.toString()||'';if(result.length<500)throw new Error('Select the completed report including sources first.');reply({result,message:'Report returned by editor'});}
      else if(msg.type==='fetch-image'){
        const {el,role}=target(msg);if(role!=='image')throw new Error('No generated image selected.');
        fetch(el.currentSrc||el.src).then(r=>{if(!r.ok)throw new Error('Image download unavailable');return r.blob();}).then(blob=>{
          if(!blob.type.startsWith('image/')||blob.size>8500000)throw new Error('Use an image below 8 MB.');
          const reader=new FileReader();reader.onload=()=>reply({result:reader.result.split(',')[1]});reader.readAsDataURL(blob);
        }).catch(()=>reply({error:'Image download blocked. Download it in the job tab and return the file through the popup.'}));return true;
      }
    }catch(e){reply({error:e.message});}
  });
})();
