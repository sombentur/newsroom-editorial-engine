import test from 'node:test';
import assert from 'node:assert/strict';
import {assertJobTab,validateAction} from '../chrome-extension/policy.mjs';
const obs={prompt_verified:true,elements:[{id:1,role:'textbox',editable:true,empty:true},{id:2,role:'button',name:'Send prompt'},{id:3,role:'button',name:'Delete chat'}]};
test('dedicated host enforced',()=>{assertJobTab({kind:'image'},{url:'https://chatgpt.com/c/123'});for(const url of ['https://chatgpt.com.evil.example/','http://chatgpt.com/','https://gemini.google.com/','https://chatgpt.com:444/'])assert.throws(()=>assertJobTab({kind:'image'},{url}));});
test('unknown and sensitive controls rejected',()=>{for(const target of [3,99])assert.throws(()=>validateAction({action:'click',target},obs,{}));});
test('duplicate submission prevented locally',()=>{assert.throws(()=>validateAction({action:'submit',target:2},{...obs,prompt_verified:false},{filled:true,submitted:true}));assert.throws(()=>validateAction({action:'submit',target:2},obs,{filled:true,submitted:true,resent:true}));assert.throws(()=>validateAction({action:'fill_prompt',target:1},obs,{submitted:true}));assert.throws(()=>validateAction({action:'click',target:2},obs,{}));validateAction({action:'submit',target:2},obs,{filled:true,submitted:false});});
test('arbitrary scripts cannot be requested',()=>{assert.throws(()=>validateAction({action:'eval',target:0},obs,{}));});
test('existing composer contents preserved',()=>{assert.throws(()=>validateAction({action:'fill_prompt',target:1},{elements:[{id:1,editable:true,empty:false}]},{}));});

test('Gemini Deep Research checkbox menu is clickable',()=>{validateAction({action:'click',target:7},{elements:[{id:7,role:'menuitemcheckbox',name:'Deep research'}]},{});});
test('an unsent prompt (still in the composer) may be sent exactly once more',()=>{validateAction({action:'submit',target:2},obs,{filled:true,submitted:true});});
test('ChatGPT thinking level: only the Power item, only before the prompt',()=>{
 const menu={elements:[{id:4,role:'menuitem',name:'Power'},{id:5,role:'menuitem',name:'Select model'}]};
 validateAction({action:'level_down',target:4},menu,{});validateAction({action:'close_menu',target:0},menu,{});
 assert.throws(()=>validateAction({action:'level_up',target:5},menu,{}));
 assert.throws(()=>validateAction({action:'level_up',target:4},menu,{filled:true}));
 assert.throws(()=>validateAction({action:'close_menu',target:0},menu,{submitted:true}));
});
