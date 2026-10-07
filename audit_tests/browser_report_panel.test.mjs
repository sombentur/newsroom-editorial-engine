// The fallback copy reads only the open report panel, never the whole Gemini conversation (0.4.12),
// and no page message or browser command can freeze the extension.
import assert from 'node:assert/strict';
import vm from 'node:vm';
import fs from 'node:fs';
import {withTimeout} from '../chrome-extension/observer.mjs';

class El{
  constructor(tag,attrs={},kids=[],text=''){
    Object.assign(this,{tagName:tag.toUpperCase(),attrs,kids,text,parentElement:null,isConnected:true});
    kids.forEach(k=>k.parentElement=this);
  }
  getAttribute(a){return a in this.attrs?this.attrs[a]:null;}
  getClientRects(){return [{}];}
  get innerText(){return [this.text,...this.kids.map(k=>k.innerText)].filter(Boolean).join('\n');}
  get textContent(){return this.innerText;}
  get innerHTML(){return this.text+this.kids.map(k=>k.outerHTML).join('');}
  get outerHTML(){const t=this.tagName.toLowerCase(),a=Object.entries(this.attrs).map(([k,v])=>` ${k}="${v}"`).join('');return `<${t}${a}>${this.innerHTML}</${t}>`;}
  contains(o){for(let e=o;e;e=e.parentElement)if(e===this)return true;return false;}
  closest(s){for(let e=this;e;e=e.parentElement)if(e.matches(s))return e;return null;}
  descendants(){return this.kids.flatMap(k=>[k,...k.descendants()]);}
  matches(selector){return selector.split(',').some(s=>{
    const m=s.trim().match(/^\[([\w-]+)(?:(\*?=)"(.*)")?\]$/);
    if(m)return m[2]==='*='?String(this.getAttribute(m[1])||'').includes(m[3]):m[2]?this.getAttribute(m[1])===m[3]:this.getAttribute(m[1])!==null;
    return this.tagName===s.trim().toUpperCase();
  });}
  querySelectorAll(s){return this.descendants().filter(e=>e.matches(s));}
  querySelector(s){return this.querySelectorAll(s)[0]||null;}
  cloneNode(){return new El(this.tagName,{...this.attrs},this.kids.map(k=>k.cloneNode()),this.text);}
  remove(){if(this.parentElement)this.parentElement.kids=this.parentElement.kids.filter(k=>k!==this);this.parentElement=null;}
}

const prompt='Research the Bidadi integrated township project and write the complete report in Kannada.';
function page({withPanel=true}={}){
  const share=new El('button',{'aria-label':'Share & Export'},[new El('mat-icon',{},[],'share')]);
  const report=new El('div',{class:'markdown markdown-main-panel'},[
    new El('h2',{class:'cdk-visually-hidden'},[],'Gemini said'),
    new El('h1',{},[],'ಬಿಡದಿ ಟೌನ್‌ಶಿಪ್ ವರದಿ'),
    new El('p',{},[new El('button',{},[],'Learn More')],'ಬಿಡದಿ ವರದಿಯ ವಿವರ '.repeat(150)),
    new El('p',{},[new El('a',{href:'https://example.org/source'},[],'ಮೂಲ')]),
  ]);
  const toolbar=new El('div',{class:'toolbar'},[new El('span',{},[],'ಬಿಡದಿ ರೈತರ ಹೋರಾಟದ ವಿಶ್ಲೇಷಣೆ'),
    new El('button',{'aria-label':'Table of contents menu'},[],'Contents'),new El('div',{class:'share-wrap'},[share]),new El('button',{},[],'Create')]);
  const panel=new El('div',{class:'immersive-panel'},[toolbar,new El('div',{class:'container'},[report])]);
  // The chat is longer than the report: the old fallback took everything.
  const chat=new El('section',{class:'chat-history'},[new El('h1',{class:'cdk-visually-hidden'},[],'Conversation with Gemini'),
    new El('div',{class:'query-text'},[],prompt),new El('div',{class:'markdown'},[],'ಹಿಂದಿನ ಸಂಭಾಷಣೆಯ ಪಠ್ಯ '.repeat(300))]);
  const body=new El('body',{},[new El('main',{role:'main'},withPanel?[chat,panel]:[chat])]);
  return {body,querySelectorAll:s=>body.querySelectorAll(s),querySelector:s=>body.querySelector(s),getElementById:()=>null};
}
function helper(document){
  let handler;
  vm.runInNewContext(fs.readFileSync(new URL('../chrome-extension/content.js',import.meta.url),'utf8'),
    {document,location:{href:'https://gemini.google.com/app/x',hostname:'gemini.google.com'},crypto:{randomUUID:()=>'snap'},
     getComputedStyle:()=>({visibility:'visible'}),chrome:{runtime:{id:'test',onMessage:{addListener:f=>handler=f}}}});
  return msg=>{let reply;handler(msg,{id:'test'},r=>reply=r);return reply;};
}
const reportText=document=>helper(document)({type:'report-text',prompt});

// The side-panel report is observed as the report, so the rules can start Share & Export -> Copy.
const observed=helper(page())({type:'observe',prompt});
const reports=observed.elements.filter(e=>e.role==='report');
assert.ok(reports.some(e=>e.name.includes('ಬಿಡದಿ ಟೌನ್‌ಶಿಪ್ ವರದಿ')),'the panel report is observed as a report');
assert.ok(!reports.some(e=>e.name.includes(prompt.slice(0,40))),'the job prompt is never a report');
assert.ok(observed.elements.some(e=>e.name==='Share & Export'),'Share & Export observed');
assert.ok(!helper(page({withPanel:false}))({type:'observe',prompt}).elements.some(e=>e.role==='report'&&e.name.includes('ಬಿಡದಿ ಟೌನ್‌ಶಿಪ್ ವರದಿ')),'no panel, no panel report');

const copied=reportText(page());
assert.equal(copied.format,'html');
assert.ok(copied.result.startsWith('<h1>ಬಿಡದಿ ರೈತರ ಹೋರಾಟದ ವಿಶ್ಲೇಷಣೆ</h1>'),'report title from the panel toolbar comes first');
assert.ok(copied.result.includes('ಬಿಡದಿ ವರದಿಯ ವಿವರ'),'report body copied');
assert.ok(copied.result.includes('<h1>ಬಿಡದಿ ಟೌನ್‌ಶಿಪ್ ವರದಿ</h1>'),'report heading kept as a heading');
assert.ok(copied.result.includes('https://example.org/source'),'source link kept');
for(const junk of ['ಹಿಂದಿನ ಸಂಭಾಷಣೆ','Conversation with Gemini','Gemini said','Learn More','Share & Export','Contents','Create',prompt])
  assert.ok(!copied.result.includes(junk),'not copied: '+junk);
assert.match(reportText(page({withPanel:false})).error,/full report is not open/);

// Time limits: a call that never answers fails with a clear error instead of hanging forever.
await assert.rejects(withTimeout(new Promise(()=>{}),20,'Screenshot'),/Screenshot timed out/);
assert.equal(await withTimeout(Promise.resolve(7),1000,'Quick call'),7);
const worker=fs.readFileSync(new URL('../chrome-extension/worker.js',import.meta.url),'utf8');
assert.match(worker,/withTimeout\(command\(active,'Page\.captureScreenshot'[^\n]*\.catch\(\(\)=>null\)/,'screenshot is optional');
assert.match(worker,/withTimeout\(chrome\.debugger\.sendCommand/,'every browser command has a time limit');
assert.ok(!/await chrome\.tabs\.sendMessage\(/.test(worker),'every page message has a time limit');
console.log('Report panel and time-limit checks passed.');
