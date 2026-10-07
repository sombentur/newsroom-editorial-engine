// After an extension update, a work tab's page helper is re-injected (or the tab reloaded) instead of failing the job.
import assert from 'node:assert/strict';
import {isMissingObserver,reconnectObserver} from '../chrome-extension/observer.mjs';
assert.ok(isMissingObserver(new Error('Could not establish connection. Receiving end does not exist.')));
assert.ok(!isMissingObserver(new Error('No tab with id: 5')));
const injected=[];const reloaded=[];
const withScripting={scripting:{executeScript:async({target,files})=>{injected.push([target.tabId,files[0]]);}},tabs:{reload:async id=>reloaded.push(id)}};
assert.equal(await reconnectObserver(withScripting,7),'injected');assert.deepEqual(injected,[[7,'content.js']]);assert.deepEqual(reloaded,[]);
const failing={scripting:{executeScript:async()=>{throw new Error('Cannot access contents of the page');}},tabs:{reload:async id=>reloaded.push(id)}};
assert.equal(await reconnectObserver(failing,8),'reloaded');assert.deepEqual(reloaded,[8]);
assert.equal(await reconnectObserver({tabs:{reload:async id=>reloaded.push(id)}},9),'reloaded');
console.log('Observer reconnect checks passed.');
