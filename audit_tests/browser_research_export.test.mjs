import assert from 'node:assert/strict';
import {exportAction,validateCopiedReport,controlLabel} from '../chrome-extension/research-export.mjs';
const obs={elements:[{id:1,role:'button',name:'Share & export'},{id:2,role:'menuitem',name:'Copy content'}]};
assert.equal(exportAction(obs).target,1);assert.equal(exportAction(obs,'copy').target,2);
// Gemini's current labels, including Material icon ligatures in the button text.
const live={elements:[{id:7,role:'button',name:'Share & Export keyboard_arrow_down'},{id:8,role:'menuitem',name:'content_copy Copy contents'},
  {id:9,role:'menuitem',name:'Export to Docs'},{id:10,role:'button',name:'Create'}]};
assert.equal(controlLabel(live.elements[0]),'Share & Export');
assert.equal(exportAction(live).target,7);assert.equal(exportAction(live,'copy').target,8);
assert.equal(exportAction({elements:[...obs.elements,{name:'Stop response'}]}).action,'wait');
assert.equal(exportAction({elements:[...obs.elements,{name:'stop Stop response'}]}).action,'wait');
assert.throws(()=>exportAction({elements:[{id:1,role:'button',name:'Share'}]}),/visible/);
// A long report paragraph that merely mentions "share and export" is never treated as the control.
assert.throws(()=>exportAction({elements:[{id:3,role:'button',name:'Farmers share and export concerns about fake seeds sold across North Karnataka'}]}),/visible/);
assert.throws(()=>validateCopiedReport("I've put together a research plan"+'x'.repeat(600)),/plan/);
assert.throws(()=>validateCopiedReport('x'.repeat(600),true),/Kannada/);
assert.equal(validateCopiedReport('ಕನ್ನಡ '.repeat(150),true),'ಕನ್ನಡ '.repeat(150));
// Same button on the report card and in the open panel: the panel's (last) one is used.
assert.equal(exportAction({elements:[{id:4,role:'button',name:'Share & Export'},{id:5,role:'button',name:'Share & Export'}]}).target,5);
// Gemini's current export menu: Share report / Export to Docs / Export to Notebook / Copy.
const menu={elements:[{id:20,role:'button',name:'Copy'},{id:21,role:'button',name:'Copy prompt'},{id:22,role:'menuitem',name:'Share report'},
  {id:23,role:'menuitem',name:'Export to Docs'},{id:24,role:'menuitem',name:'Export to Notebook'},{id:25,role:'menuitem',name:'content_copy Copy'}]};
assert.equal(exportAction(menu,'copy').target,25,'the menu item, never the chat Copy button');
assert.throws(()=>exportAction({elements:[{id:20,role:'button',name:'Copy'},{id:21,role:'button',name:'Copy prompt'}]},'copy'),/visible/);
console.log('Report export checks passed.');
