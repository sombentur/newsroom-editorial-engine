// A long Deep Research report (hundreds of "Learn More" chips) must not hide the open export menu.
import assert from 'node:assert/strict';
import vm from 'node:vm';
import fs from 'node:fs';
const el=(label,role=null)=>({isConnected:true,innerText:label,value:undefined,disabled:false,tagName:'BUTTON',
  getAttribute:a=>a==='aria-label'?label:a==='role'?role:null,matches:()=>false,closest:()=>null,getClientRects:()=>[{}]});
const chips=Array.from({length:300},()=>el('Learn More'));
const share=el('Share & Export');const copy=el('Copy contents','menuitem');const docs=el('Export to Docs','menuitem');
const overlay={querySelectorAll:()=>[docs,copy]};
const main={innerText:'Report'};
const document={body:main,querySelector:()=>main,getElementById:()=>null,
  querySelectorAll:s=>s.startsWith('.cdk-overlay-container')?[overlay]:s.startsWith('button,')?[...chips,share,docs,copy]:[]};
let handler;
vm.runInNewContext(fs.readFileSync(new URL('../chrome-extension/content.js',import.meta.url),'utf8'),
  {document,location:{href:'https://gemini.google.com/app/x',hostname:'gemini.google.com'},crypto:{randomUUID:()=>'snap'},
   getComputedStyle:()=>({visibility:'visible'}),chrome:{runtime:{id:'test',onMessage:{addListener:f=>handler=f}}}});
let obs;handler({type:'observe',prompt:''},{id:'test'},r=>obs=r);
const names=obs.elements.map(e=>e.name);
assert.equal(names[0],'Export to Docs');assert.ok(names.includes('Copy contents'),'menu item observed first');
assert.ok(names.includes('Share & Export'),'export button kept');
assert.equal(names.filter(n=>n==='Learn More').length,5,'repeated source chips trimmed');
console.log('Snapshot checks passed.');
