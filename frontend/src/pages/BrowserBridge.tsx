// MAINTAINER NOTE (2026-09-27): BROWSER STATUS UI: Attached/page-controls-ready does not verify account quota, subscription or final generation. Continue is currently in the Chrome extension popup; Stop this browser job is also exposed here. Distinguish installed version, heartbeat, workspace readiness and job state. See docs/MAINTAINER_HANDOFF.md.
import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { apiGet, apiPost } from '@/lib/api';
import { queryClient } from '@/lib/queryClient';
import { Button } from '@/components/ui/button';
import RouteSelector, { EXTENSION_VERSION } from '@/components/RouteSelector';
import { SectionLabel } from '@/lib/ui';
import { cn } from '@/lib/utils';
import { toast } from 'sonner';

type Job = {id:string; article_id:string; kind:string; status:string; message:string; last_observation?:{at:string}; activity?:{action:string;note:string;at:string}[]};
type TabStatus = {attached:boolean;ready:boolean;message:string};
type Status = {gemini_account?:string|null;research_url?:string;workspace?:Record<string,TabStatus>;workspace_seen?:string;research:boolean;image:boolean;paired:boolean;auto_pair_blocked?:boolean;latest_version?:string;version?:string;controller_model:string;controller_configured:boolean;last_seen:string|null;jobs:Job[]};

const JOB_LABEL: Record<string,string> = { research: 'Gemini · Deep Research', image: 'ChatGPT · Thumbnail', seo: 'ChatGPT · SEO assets' };
const STATUS_TONE: Record<string,string> = {
  running: 'border-sky-200 bg-sky-50 text-sky-800', queued: 'border-slate-300 bg-slate-100 text-slate-700',
  attention: 'border-amber-200 bg-amber-50 text-amber-800', completed: 'border-emerald-200 bg-emerald-50 text-emerald-700',
  cancelled: 'border-slate-200 bg-white text-slate-500', consumed: 'border-emerald-200 bg-emerald-50 text-emerald-700',
};

export default function BrowserBridge() {
  const { data } = useQuery({ queryKey: ['browser-status'], queryFn: () => apiGet<Status>('/browser/status'), refetchInterval: 5000 });
  const [code,setCode]=useState(''); const [busy,setBusy]=useState(false); const [address,setAddress]=useState('');
  async function act(fn:()=>Promise<unknown>){setBusy(true);try{await fn();await queryClient.invalidateQueries({queryKey:['browser-status']});}catch(e){toast.error(e instanceof Error?e.message:'Connection failed');}finally{setBusy(false);}}
  if(!data)return <p className="text-sm text-slate-600">Loading browser connection…</p>;
  const connected=!!data.last_seen && Date.now()-new Date(data.last_seen).getTime()<90000;
  const fresh=!!data.workspace_seen && Date.now()-new Date(data.workspace_seen).getTime()<45000;
  const workspaceReady=fresh && data.workspace?.research?.ready && data.workspace?.image?.ready;
  const supported=!!data.version&&data.version.split('.').map(Number).reduce((a,n,i)=>a+n*1000**(2-i),0)>=3001;  // 0.3.1 or newer
  return <div className="space-y-5 text-sm text-slate-700">
    <RouteSelector />

    <div className="grid gap-4 lg:grid-cols-2">
      <section className="surface rounded-2xl border border-slate-200 p-5">
        <SectionLabel>Chrome work tabs</SectionLabel>
        <p className="mt-2 text-slate-600">The extension opens its own Gemini and ChatGPT tabs in your signed-in Chrome. Research runs in Gemini while SEO and thumbnails run in ChatGPT at the same time. Your personal chat tabs are never used.</p>
        <div className="mt-4 grid gap-3 sm:grid-cols-2">{(['research','image'] as const).map(kind=>{
          const tab=data.workspace?.[kind]; const ok=connected&&fresh&&tab?.ready;
          return <div key={kind} className="rounded-xl border border-slate-200 bg-slate-50/70 p-3">
            <div className="flex items-center gap-2 font-medium text-slate-900"><span className={cn('h-2 w-2 rounded-full',ok?'bg-emerald-500 animate-soft-pulse':'bg-slate-400')} />{kind==='research'?'Gemini · Deep Research':'ChatGPT · SEO & thumbnails'}</div>
            <p className="mt-1 text-xs text-slate-600">{connected && fresh ? tab?.message || 'Control released' : 'Waiting for extension connection'}</p>
          </div>;})}</div>
        <div className="mt-4 flex flex-wrap gap-2"><Button disabled={busy||!connected||!supported} onClick={()=>act(()=>apiPost('/browser/workspace',{action:'connect'}))}>Connect both work tabs</Button><Button variant="outline" disabled={busy||!connected||!supported} onClick={()=>act(()=>apiPost('/browser/workspace',{action:'disconnect'}))}>Release control</Button></div>
        <p className="mt-3 text-xs text-slate-500">Release control stops browser jobs and detaches both tabs. “Page controls ready” does not verify your subscription or a successful generation.</p>
        <div className="mt-4 rounded-xl border border-slate-200 bg-white/60 p-3" data-testid="gemini-account">
          <div className="font-medium text-slate-900">Gemini account for Deep Research</div>
          <p className="mt-1 text-xs text-slate-600">Now: <strong>{data.gemini_account ? `the account at ${data.research_url}` : 'the first account signed in to Chrome'}</strong>. To use another Google account, open Gemini in Chrome and switch to that account: its address shows e.g. <span className="font-mono">https://gemini.google.com/u/1/app</span>. Paste that address here. The Gemini work tab moves to it when idle, and every research chat opens there. No need to close any tab.</p>
          <div className="mt-2 flex flex-wrap items-center gap-2">
            <input value={address} onChange={e=>setAddress(e.target.value)} placeholder="https://gemini.google.com/u/1/app" aria-label="Gemini address of the chosen account"
              className="min-w-[240px] flex-1 rounded-lg border border-slate-300 bg-white px-2.5 py-1.5 font-mono text-xs text-slate-900" />
            <Button size="sm" disabled={busy||!/^https:\/\/gemini\.google\.com\//.test(address.trim())} onClick={()=>act(async()=>{const r=await apiPost<{research_url:string}>('/browser/gemini-account',{address:address.trim()});setAddress('');toast.success('Gemini research now uses '+r.research_url);})}>Use this account</Button>
            {data.gemini_account && <Button size="sm" variant="outline" disabled={busy} onClick={()=>act(async()=>{await apiPost('/browser/gemini-account',{address:''});toast.success('Gemini research uses the first signed-in account');})}>Use first account</Button>}
          </div>
          <p className="mt-2 text-[11px] text-slate-500">The number after /u/ follows the order the accounts were signed in to Chrome; if you sign out and in again, check it here.</p>
        </div>
      </section>

      <section className="surface rounded-2xl border border-slate-200 p-5">
        <SectionLabel>Extension connection</SectionLabel>
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <span className={cn('inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-medium', connected?'border-emerald-200 bg-emerald-50 text-emerald-700':'border-slate-300 bg-slate-100 text-slate-600')}>{data.paired?(connected?'Connected':'Paired · Chrome offline'):'Not paired'}</span>
          <span className="text-xs text-slate-500">Extension {data.version || 'not detected'} · latest {data.latest_version || EXTENSION_VERSION}</span>
        </div>
        <p className="mt-3 text-slate-600"><strong className="text-slate-900">No code needed.</strong> The extension connects to this app by itself whenever Chrome and the app are running, and the app keeps the extension up to date each time it starts. Page steps are chosen by <strong className="text-slate-900">{data.controller_model || 'no model'}</strong> {data.controller_configured ? '(a few small API calls per job)' : '— API key missing'}.</p>
        {data.auto_pair_blocked && <div className="mt-3 flex flex-wrap items-center gap-3 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-amber-800"><span>Automatic connection is paused because Chrome was disconnected here.</span><Button size="sm" disabled={busy} onClick={()=>act(()=>apiPost('/browser/auto-pair/allow'))}>Allow automatic connection</Button></div>}
        <div className="mt-4 flex flex-wrap gap-2"><Button variant="outline" disabled={busy || !workspaceReady || !connected || !supported || !data.controller_configured} onClick={()=>act(()=>apiPost("/browser/test"))}>Test Gemini + ChatGPT</Button><Button variant="outline" disabled={busy} onClick={()=>act(async()=>{await apiPost('/browser/disconnect');setCode('');})}>Disconnect browser</Button></div>
        <details className="mt-4 rounded-lg border border-slate-200 bg-slate-50/70 px-3 py-2"><summary className="cursor-pointer text-xs font-medium text-slate-700">Advanced · first-time install or manual pairing</summary>
          <ol className="mt-2 list-decimal space-y-1.5 pl-5 text-xs text-slate-600"><li>First install only: <a className="text-navy-600 underline decoration-sky-300 underline-offset-4" href="/api/browser/download">download the extension</a>, extract it, then in <strong>chrome://extensions</strong> enable Developer mode and choose <strong>Load unpacked</strong>.</li><li>Sign in to Gemini and ChatGPT in Chrome. It connects automatically within a minute.</li><li>Only if it does not connect: generate a code and paste it into the extension popup under Advanced.</li></ol>
          <Button className="mt-2" size="sm" variant="outline" disabled={busy} onClick={()=>act(async()=>{const r=await apiPost<{code:string}>('/browser/pair-code');setCode(r.code);})}>Generate manual pairing code</Button>
          {code&&<label className="mt-2 block text-xs text-slate-600">One-use pairing code · expires in 10 minutes<input readOnly value={code} className="mt-1 block w-full rounded-lg border border-slate-300 bg-white p-2.5 font-mono text-slate-900" onFocus={e=>e.target.select()}/></label>}
        </details>
        <p className="mt-3 text-xs text-slate-500">Connects to this computer at 127.0.0.1:8001. Screenshots used to choose page steps are kept in memory only.</p>
      </section>
    </div>

    <section className="surface rounded-2xl border border-slate-200 p-5">
      <SectionLabel>Browser jobs</SectionLabel>
      <div className="mt-3 space-y-2">{data.jobs.length===0?<p className="text-slate-500">No browser jobs yet.</p>:data.jobs.map(job=><div key={job.id} className="rounded-xl border border-slate-200 bg-white p-3">
        <div className="flex flex-wrap items-center justify-between gap-2"><a className="font-medium text-navy-600 hover:underline" href={'/articles?open='+job.article_id}>{JOB_LABEL[job.kind] ?? job.kind}</a><span className={cn('rounded-full border px-2.5 py-0.5 text-[11px] font-medium', STATUS_TONE[job.status] ?? STATUS_TONE.queued)}>{job.status}</span></div>
        <p className="mt-1.5 text-slate-600">{job.message}</p>
        <div className="mt-2 flex flex-wrap items-center gap-3 text-xs">
          {job.last_observation && Date.now() - new Date(job.last_observation.at).getTime() < 300000 && <a className="text-navy-600 underline decoration-sky-300 underline-offset-4" href={"/api/browser/jobs/"+job.id+"/page"} target="_blank" rel="noopener noreferrer">View browser job page</a>}
          {job.status === "completed" && <a className="text-navy-600 underline decoration-sky-300 underline-offset-4" href={"/api/browser/jobs/"+job.id+"/result"} target="_blank" rel="noreferrer">View returned result</a>}
          {['queued','running','attention'].includes(job.status)&&<Button size="sm" variant="outline" disabled={busy} onClick={()=>act(()=>apiPost('/browser/jobs/'+job.id+'/cancel'))}>Stop this browser job</Button>}
        </div>
        {!!job.activity?.length && <details className="mt-2"><summary className="cursor-pointer text-xs text-slate-500">Browser activity · {job.activity.length} steps</summary><ol className="mt-2 max-h-64 space-y-1.5 overflow-auto text-xs">{job.activity.map((event,i)=><li key={i}><span className="font-medium text-sky-700">{event.action}</span> · {event.note} <span className="text-slate-400">{new Date(event.at).toLocaleTimeString()}</span></li>)}</ol></details>}
      </div>)}</div>
    </section>
  </div>;
}
