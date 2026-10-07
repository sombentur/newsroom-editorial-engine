const status=document.getElementById('status');
async function send(msg){status.textContent='Working…';const r=await chrome.runtime.sendMessage(msg);status.textContent=r?.error || 'Done';refresh();}
document.getElementById('pair').onclick=()=>send({type:'pair',code:document.getElementById('code').value.trim()});
for(const id of ['poll','open','collect','stop','connect-workspace','release-workspace','show-research','show-image']) document.getElementById(id).onclick=()=>send({type:id});
document.getElementById('image').onchange=async e=>{const f=e.target.files[0];if(!f)return;if(f.size>8500000){status.textContent='Use an image under 8 MB';return;}const reader=new FileReader();reader.onload=()=>send({type:'collect',image:reader.result.split(',')[1]});reader.readAsDataURL(f);};
async function refresh(){
 const {token,message}=await chrome.storage.local.get(['token','message']);
 const offline=/fetch|Not paired|Connection failed/i.test(message||'');
 document.getElementById('connection').textContent=token&&!offline?'Connected to Newsroom':token?'Waiting for the Newsroom app':'Connecting automatically…';
 document.getElementById('dot').className='dot '+(token&&!offline?'ok':offline?'bad':'');
 if(status.textContent==='Connecting…'||status.textContent==='Done')status.textContent=message||'Ready';
 const r=await chrome.runtime.sendMessage({type:"workspace-status"});
 document.getElementById("workspace-status").textContent=["research","image"].map(k=>(k==="research"?"Gemini: ":"ChatGPT: ")+(r?.status?.[k]?.message||"Not connected")).join("\n");
}
refresh();setInterval(refresh,2000);
