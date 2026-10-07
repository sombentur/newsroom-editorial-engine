// 0.4.20: ChatGPT's answer is observed as a report (its "markdown" block); the job's own prompt never is.
import assert from 'node:assert/strict';
import vm from 'node:vm';
import fs from 'node:fs';

const prompt='You are the SEO editor for Kannada Edition (WordPress with Rank Math). Read the article below and reply with ONE JSON object only, with these keys: "seo_title", "meta_description", ... '+'ಲೇಖನ '.repeat(200);
const answer='{"seo_title": "ಬಿಡದಿ ರೈತರ ಹೋರಾಟ", "meta_description": "'+'ವಿವರ '.repeat(150)+'"}';
function block(cls,text,{user=false}={}){
  return {isConnected:true,innerText:text,className:cls,disabled:false,tagName:'DIV',
    getAttribute:a=>a==='class'?cls:null,getClientRects:()=>[{}],matches:()=>false,
    closest:s=>user&&s.includes('data-turn="user"')?{}:null,querySelector:()=>null,contains:()=>false};
}
const mine=block('whitespace-pre-wrap',prompt,{user:false});   // no user marker: excluded by its text
const reply=block('markdown prose',answer);
const document={body:{innerText:prompt+answer},querySelector:()=>({innerText:prompt+answer}),getElementById:()=>null,
  querySelectorAll:s=>s.includes('[class*="markdown"')?[mine,reply]:[]};
let handler;
vm.runInNewContext(fs.readFileSync(new URL('../chrome-extension/content.js',import.meta.url),'utf8'),
  {document,location:{href:'https://chatgpt.com/c/1',hostname:'chatgpt.com'},crypto:{randomUUID:()=>'snap'},
   getComputedStyle:()=>({visibility:'visible'}),chrome:{runtime:{id:'test',onMessage:{addListener:f=>handler=f}}}});
let obs;handler({type:'observe',prompt},{id:'test'},r=>obs=r);
const reports=obs.elements.filter(e=>e.role==='report');
assert.equal(reports.length,1,'only the answer is a report');
assert.ok(reports[0].name.startsWith('{"seo_title"'),'the JSON answer, not the prompt');

// 0.4.21: markup-independent: the largest block beside the answer's own action bar ("Read aloud").
class El{
  constructor(tag,kids=[],text='',label=null){Object.assign(this,{tagName:tag.toUpperCase(),kids,text,label,parentElement:null,isConnected:true,className:'',attributes:[]});kids.forEach(k=>k.parentElement=this);}
  getAttribute(a){return a==='aria-label'?this.label:null;}
  getClientRects(){return [{}];}
  get innerText(){return [this.text,...this.kids.map(k=>k.innerText)].filter(Boolean).join('\n');}
  get textContent(){return this.innerText;}
  contains(o){for(let e=o;e;e=e.parentElement)if(e===this)return true;return false;}
  closest(){return null;} matches(){return false;} querySelector(s){return this.querySelectorAll(s)[0]||null;}
  descendants(){return this.kids.flatMap(k=>[k,...k.descendants()]);}
  querySelectorAll(s){const tags=s.split(',').map(x=>x.trim().toUpperCase());return this.descendants().filter(e=>tags.includes(e.tagName)||(s.includes('button')&&e.tagName==='BUTTON'));}
}
const readAloud=new El('button',[],'','Read aloud');
const turnUser=new El('div',[new El('div',[],prompt)]);
const turnAnswer=new El('div',[new El('div',[new El('pre',[],answer)]),new El('div',[readAloud,new El('button',[],'','Regenerate response')])]);
const body=new El('body',[new El('div',[turnUser,turnAnswer])]);
const page={body,querySelector:()=>body,getElementById:()=>null,querySelectorAll:s=>body.querySelectorAll(s)};
let handler2;
vm.runInNewContext(fs.readFileSync(new URL('../chrome-extension/content.js',import.meta.url),'utf8'),
  {document:page,location:{href:'https://chatgpt.com/c/2',hostname:'chatgpt.com'},crypto:{randomUUID:()=>'snap2'},
   getComputedStyle:()=>({visibility:'visible'}),chrome:{runtime:{id:'test',onMessage:{addListener:f=>handler2=f}}}});
let obs2;handler2({type:'observe',prompt},{id:'test'},r=>obs2=r);
const found=obs2.elements.filter(e=>e.role==='report');
assert.equal(found.length,1,'the answer beside Read aloud');
assert.ok(found[0].name.startsWith('{"seo_title"'),'the answer, never the prompt');
assert.ok(typeof obs2.hint==='string'&&obs2.hint.startsWith('div'),'structure outline recorded');
// 0.4.23: the page as ChatGPT renders it now: the user's message is markdown too, inside its bubble.
class Node2{
  constructor(tag,attrs={},kids=[],text=''){Object.assign(this,{tagName:tag.toUpperCase(),attrs,kids,text,parentElement:null,isConnected:true});kids.forEach(k=>k.parentElement=this);}
  get className(){return this.attrs.class||'';}
  get attributes(){return Object.entries(this.attrs).map(([name,value])=>({name,value}));}
  getAttribute(a){return a in this.attrs?this.attrs[a]:null;}
  getClientRects(){return [{}];}
  get innerText(){return [this.text,...this.kids.map(k=>k.innerText)].filter(Boolean).join('\n');}
  get textContent(){return this.innerText;}
  contains(o){for(let e=o;e;e=e.parentElement)if(e===this)return true;return false;}
  matches(selector){return selector.split(',').some(raw=>{const s=raw.trim();let m;
    if((m=s.match(/^\[([\w-]+)\*="([^"]*)"( i)?\]$/))){const v=String(this.getAttribute(m[1])??'');return m[3]?v.toLowerCase().includes(m[2].toLowerCase()):v.includes(m[2]);}
    if((m=s.match(/^\[([\w-]+)="([^"]*)"\]$/)))return this.getAttribute(m[1])===m[2];
    if((m=s.match(/^\[([\w-]+)\]$/)))return this.getAttribute(m[1])!==null;
    if(/^[\w-]+$/.test(s))return this.tagName===s.toUpperCase();
    return false;});}
  closest(s){for(let e=this;e;e=e.parentElement)if(e.matches(s))return e;return null;}
  descendants(){return this.kids.flatMap(k=>[k,...k.descendants()]);}
  querySelectorAll(s){return this.descendants().filter(e=>e.matches(s));}
  querySelector(s){return this.querySelectorAll(s)[0]||null;}
}
const opening='You are the SEO editor for Kannada Edition (WordPress with Rank Math). Reply with ONE JSON object.';
const articleBody='ಬಿಡದಿ ರೈತರ ಹೋರಾಟದ ಲೇಖನ '.repeat(400);
const userBubble=new Node2('div',{'data-user-message-bubble':'true'},[new Node2('div',{class:'MarkdownRoot-rZKhxa','data-markdown-text-tone':'user-message'},
  [new Node2('p',{class:'Paragraph-kKnbIo'},[],opening),new Node2('p',{class:'Paragraph-kKnbIo'},[],articleBody)])]);
const answerRoot=new Node2('div',{class:'MarkdownRoot-rZKhxa'},[new Node2('pre',{},[],answer)]);
const bar2=new Node2('div',{},[new Node2('button',{'aria-label':'Copy'}),new Node2('button',{'aria-label':'Read aloud'}),new Node2('button',{'aria-label':'Regenerate response'})]);
const body2=new Node2('body',{},[new Node2('main',{},[new Node2('div',{},[userBubble]),new Node2('div',{},[answerRoot,bar2])])]);
const page2={body:body2,querySelector:s=>body2.querySelector(s)||body2,getElementById:()=>null,querySelectorAll:s=>body2.querySelectorAll(s)};
let handler3;
vm.runInNewContext(fs.readFileSync(new URL('../chrome-extension/content.js',import.meta.url),'utf8'),
  {document:page2,location:{href:'https://chatgpt.com/c/3',hostname:'chatgpt.com'},crypto:{randomUUID:()=>'snap3'},
   getComputedStyle:()=>({visibility:'visible'}),chrome:{runtime:{id:'test',onMessage:{addListener:f=>handler3=f}}}});
let obs3;handler3({type:'observe',prompt:opening+'\n\n'+articleBody},{id:'test'},r=>obs3=r);
const answers=obs3.elements.filter(e=>e.role==='report');
assert.ok(answers.length>=1&&answers.every(e=>!e.name.includes('ಬಿಡದಿ ರೈತರ ಹೋರಾಟದ ಲೇಖನ')),'never the user message bubble');
assert.ok(answers.some(e=>e.name.includes('"seo_title"')),'the JSON answer is observed');
console.log('ChatGPT answer checks passed.');
