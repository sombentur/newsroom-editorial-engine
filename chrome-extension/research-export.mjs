// MAINTAINER NOTE (2026-09-27): REPORT RECOVERY: Select only observed Share & Export and Copy content(s) controls. Reject obvious plans, short output and missing requested Kannada. These are basic checks, not proof of factual correctness or complete citations. Site labels/toasts may change; live export must be verified. See ../docs/MAINTAINER_HANDOFF.md.
// Gemini buttons often include Material icon ligatures in their text (e.g. "keyboard_arrow_down",
// "content_copy"); strip them so labels like "Share & Export" still match.
export const controlLabel=e=>String(e?.name||'').replace(/\b[a-z]+(?:_[a-z]+)+\b/g,' ').replace(/\s+/g,' ').trim();
const MENU=/(?:^|\s)share\s*(?:&|and)\s*export(?:\s|$)/i;
const COPY=/(?:^|\s)copy\s+contents?(?:\s|$)/i;
// Inside the open export menu the item may be labelled just "Copy" (Share report / Export to Docs / Export to Notebook / Copy).
const MENU_COPY=/^copy(?:\s+contents?)?$/i;
const STOP=/(?:^|\s)stop\s+(?:response|generating|answering)(?:\s|$)/i;
const short=e=>controlLabel(e).length<=40;
// Gemini can show the same export button on the report card and in the open report panel; the panel's comes last.
export function exportAction(obs, phase='menu') {
 if(obs.elements.some(e=>!e.disabled&&short(e)&&STOP.test(controlLabel(e))))return {action:'wait',reason:'Gemini is still generating the report. Waiting for completion.'};
 const matches=obs.elements.filter(e=>!e.disabled&&short(e)&&(phase==='menu'
  ?['button','menuitem'].includes(e.role)&&MENU.test(controlLabel(e))
  :(e.role==='menuitem'&&MENU_COPY.test(controlLabel(e)))||(e.role==='button'&&COPY.test(controlLabel(e)))));
 if(!matches.length)throw new Error('Open the completed Gemini report so its '+(phase==='menu'?'Share & Export':'Copy contents')+' control is visible. No new research will be submitted.');
 return {action:'click',target:matches[matches.length-1].id};
}
export function validateCopiedReport(text, requireKannada=false){
 if(typeof text!=='string'||text.trim().length<500)throw new Error('Copied report is missing or too short.');
 if(/I.ve put together a research plan|^Research Websites\s*\n/i.test(text.trim()))throw new Error('Gemini copied the research plan, not the completed report.');
 if(requireKannada&&(text.match(/[\u0c80-\u0cff]/g)||[]).length<100)throw new Error('The copied content is not the requested Kannada report.');
 return text;
}
