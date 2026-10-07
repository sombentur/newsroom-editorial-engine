import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import fs from 'node:fs';
function fixture(){
 let handler;let live;
 function field(){return {id:'prompt-textarea',tagName:'DIV',isConnected:true,innerText:'',value:'',disabled:false,
  getAttribute:a=>a==='contenteditable'?'true':a==='aria-label'?'Ask anything':null,
  matches:selector=>selector.includes('contenteditable'),closest:()=>null,getClientRects:()=>[{}],
  scrollIntoView(){},setAttribute(){},removeAttribute(){},getBoundingClientRect:()=>({x:10,y:10,width:200,height:50})};}
 live=field();const original=live;
 const main={innerText:'ChatGPT'};
 const document={body:main,querySelector:()=>main,getElementById:id=>id==='prompt-textarea'?live:null,elementFromPoint:()=>live,
 querySelectorAll:s=>s.startsWith('button,')?[live]:[]};
 const context={document,location:{href:'https://chatgpt.com/'},crypto:{randomUUID:()=> 'snapshot-1'},getComputedStyle:()=>({visibility:'visible'}),
 chrome:{runtime:{id:'test',onMessage:{addListener:f=>handler=f}}}};
 vm.runInNewContext(fs.readFileSync(new URL('../chrome-extension/content.js',import.meta.url),'utf8'),context);
 function call(msg){let output;handler(msg,{id:'test'},r=>output=r);return output;}
 return {call,replace(text=''){original.isConnected=false;live=field();live.innerText=text;live.value=text;},original};
}
test('composer re-render keeps the same observed identity',()=>{const f=fixture();const obs=f.call({type:'observe',prompt:'test prompt'});f.replace();const p=f.call({type:'prepare',snapshot:obs.snapshot,target:1,action:'fill_prompt'});assert.equal(p.x,110);});
test('re-rendered composer with existing text is not overwritten',()=>{const f=fixture();const obs=f.call({type:'observe',prompt:'test'});f.replace('owner draft');assert.match(f.call({type:'prepare',snapshot:obs.snapshot,target:1,action:'fill_prompt'}).error,/not empty/);});
test('stale observation is rejected',()=>{const f=fixture();f.call({type:'observe',prompt:'test'});assert.match(f.call({type:'prepare',snapshot:'old',target:1,action:'fill_prompt'}).error,/expired/);});

test('rich-text whitespace changes preserve full prompt verification',()=>{const f=fixture();f.replace('Research\u00a0Karnataka.\n\nInclude sources.');assert.equal(f.call({type:'observe',prompt:'Research Karnataka.\nInclude sources.'}).prompt_verified,true);});
test('missing words and changed Kannada text fail verification',()=>{const f=fixture();f.replace('ಕರ್ನಾಟಕ ನದಿಗಳು');assert.equal(f.call({type:'observe',prompt:'ಕರ್ನಾಟಕ ಪ್ರಮುಖ ನದಿಗಳು'}).prompt_verified,false);f.replace('Include sources.');assert.equal(f.call({type:'observe',prompt:'Do not include sources.'}).prompt_verified,false);});
test('empty prompt never verifies',()=>{const f=fixture();assert.equal(f.call({type:'observe',prompt:' '}).prompt_verified,false);});
test('text changed after observation cannot be submitted',()=>{const f=fixture();f.original.value='expected';const obs=f.call({type:'observe',prompt:'expected'});assert.equal(obs.prompt_verified,true);f.original.value='different';assert.match(f.call({type:'prepare',snapshot:obs.snapshot,target:1,action:'submit'}).error,/changed before sending/);});
