// 0.4.16: clicks and typing are done by the page helper (debugger input stalled on Gemini's report page).
import assert from 'node:assert/strict';
import vm from 'node:vm';
import fs from 'node:fs';

const plain=o=>JSON.parse(JSON.stringify(o));  // objects from the page helper's own context
class FakeEvent{constructor(type,init={}){Object.assign(this,init);this.type=type;}}
function fixture({composer=false,ignoresTyping=false}={}){
  const document={activeElement:null};
  const el={tagName:composer?'DIV':'BUTTON',isConnected:true,innerText:'',value:undefined,disabled:false,attrs:{},events:[],
    getAttribute(a){return a==='contenteditable'&&composer?'true':a==='aria-label'?(composer?'Ask anything':'Send'):(this.attrs[a]??null);},
    setAttribute(a,v){this.attrs[a]=v;},removeAttribute(a){delete this.attrs[a];},
    matches(s){return composer&&s.includes('contenteditable');},closest:()=>null,getClientRects:()=>[{}],scrollIntoView(){},
    getBoundingClientRect:()=>({x:10,y:10,left:10,top:10,width:200,height:50}),
    dispatchEvent(e){this.events.push(e.type);return true;},click(){this.events.push('click');},focus(){document.activeElement=this;}};
  const main={innerText:'page'};
  Object.assign(document,{body:main,getElementById:()=>null,elementFromPoint:()=>el,
    querySelector:s=>s==='main,[role="main"]'?main:(el.attrs['data-newsroom-target']&&s===`[data-newsroom-target="${el.attrs['data-newsroom-target']}"]`?el:null),
    querySelectorAll:s=>s.startsWith('button,')||s.startsWith('textarea,')?[el]:[],
    execCommand(cmd,ui,text){if(cmd==='insertText'&&document.activeElement===el&&!ignoresTyping)el.innerText+=text;
      if(cmd==='delete'&&document.activeElement===el)el.innerText='';return true;}});
  let handler;
  vm.runInNewContext(fs.readFileSync(new URL('../chrome-extension/content.js',import.meta.url),'utf8'),
    {document,window:{},MouseEvent:FakeEvent,PointerEvent:FakeEvent,location:{href:'https://chatgpt.com/',hostname:'chatgpt.com'},
     crypto:{randomUUID:()=>'tok-1'},getComputedStyle:()=>({visibility:'visible'}),chrome:{runtime:{id:'test',onMessage:{addListener:f=>handler=f}}}});
  const call=msg=>{let out;handler(msg,{id:'test'},r=>out=r);return out;};
  const obs=call({type:'observe',prompt:''});
  return {el,document,call,obs};
}

// A button: prepared, then clicked once by the page helper with a full pointer/mouse sequence.
const b=fixture();
const point=b.call({type:'prepare',snapshot:b.obs.snapshot,target:1,action:'click'});
assert.equal(point.token,'tok-1');
assert.deepEqual(plain(b.call({type:'click',token:point.token})),{ok:true});
assert.deepEqual(b.el.events,['pointerdown','mousedown','pointerup','mouseup','click']);
assert.match(b.call({type:'click',token:point.token}).error,/control changed/,'the mark is used once');

// A composer: the click puts the caret in it, then the page helper types the prompt.
const c=fixture({composer:true});
const at=c.call({type:'prepare',snapshot:c.obs.snapshot,target:1,action:'fill_prompt'});
c.call({type:'click',token:at.token});
assert.equal(c.document.activeElement,c.el,'caret placed in the composer');
assert.deepEqual(plain(c.call({type:'type',token:at.token,text:'Write the report'})),{ok:true,empty:false});
assert.equal(c.el.innerText,'Write the report');

// An editor that ignores in-page typing stays empty, so the worker may fall back to debugger text input.
const d=fixture({composer:true,ignoresTyping:true});
const p2=d.call({type:'prepare',snapshot:d.obs.snapshot,target:1,action:'fill_prompt'});
d.call({type:'click',token:p2.token});
assert.deepEqual(plain(d.call({type:'type',token:p2.token,text:'Write the report'})),{ok:false,empty:true});

// 0.4.26: leftover text in a work tab is handed back (to be saved in the article history) and cleared.
const e=fixture({composer:true});
e.el.innerText='old draft typed earlier';
assert.deepEqual(plain(e.call({type:'clear-drafts'})),{saved:[{label:'Ask anything',text:'old draft typed earlier'}],left:0});
assert.equal(e.el.innerText,'','cleared');

const worker=fs.readFileSync(new URL('../chrome-extension/worker.js',import.meta.url),'utf8');
assert.match(worker,/if\(point\.token\)\{await send\(active,\{type:'click',token:point\.token\}\);return;\}/,'clicks by the page helper');
assert.match(worker,/if\(!typed\|\|typed\.empty\)await command\(active,'Input\.insertText'/,'debugger typing only as a fallback');
assert.match(worker,/collect_report'\)\{[\s\S]{0,400}type:'report-text'/,'finished report read from its panel first');
assert.ok(!/Runtime\.evaluate/.test(worker),'no page evaluation');
assert.match(worker,/Emulation\.setFocusEmulationEnabled',\{enabled:true\}/,'work tabs keep rendering in the background');
assert.ok(!/exportPhase:job\.capture_existing/.test(worker),'re-copy jobs use the same path');
console.log('Page helper click and typing checks passed.');
