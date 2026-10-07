// Manual Editorial Workbench (owner request, 28 Sep 2026): one Topic ID → one research prompt → one external research →
// one report link → one imported report. The Excel workbook is the bridge; see backend/lib/manual_research.py. The link
// box, Proceed and research actions are shared with the Editorial Workbench (components/ResearchLink.tsx).
import { useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, CircleDashed, ClipboardCopy, Clock, Download, Eye, FileSpreadsheet, Loader2, RefreshCw, Undo2, Upload, X, XCircle } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { apiGet, apiPost } from "@/lib/api";
import { useStats } from "@/lib/hooks";
import { EmptyState, fmtTime, SectionLabel, SiteBadge, SiteSwitch, StageBadge } from "@/lib/ui";
import { cn } from "@/lib/utils";
import {
  canFetch, canPaste, canProceedImported, type ManualRow, PROBLEM, PromptPreview, ResearchFollowUps, ResearchLinkInput, ResearchPasteUpload, StatusPill,
  useResearchActions,
} from "@/components/ResearchLink";

type Row = ManualRow;
type BatchRow = { row: number; topic_id: string; title: string; link: string; link_state: string; result: string; message?: string; error?: boolean; status?: string };
type Batch = { id: string; filename: string; errors: string[]; rows: BatchRow[]; counts: Record<string, number> };
type Report = { id: string; title: string | null; link: string | null; report: string; source: string | null };

const RESERVED = ["excel_exported", "link_added", "ready_to_import", "link_invalid", "access_denied", "report_not_found", "import_failed"];

// Owner request (29 Sep 2026): Task Completion Status. Completed once the post is in WordPress (scheduled, published or a
// WordPress draft: the scheduler's DONE stages); In Process until then; a rejected topic is neither.
const COMPLETED = ["scheduled", "published", "verified", "wordpress_draft"];
const TASK_STATES = [
  { key: "in_process", label: "In Process" }, { key: "completed", label: "Completed" }, { key: "rejected", label: "Rejected" },
] as const;
const taskState = (stage: string) => (COMPLETED.includes(stage) ? "completed" : stage === "rejected" ? "rejected" : "in_process");
function TaskStatus({ stage }: { stage: string }) {
  const state = taskState(stage);
  const [label, tone, Icon] = state === "completed" ? ["Completed", "border-emerald-200 bg-emerald-50 text-emerald-800", CheckCircle2]
    : state === "rejected" ? ["Rejected", "border-slate-200 bg-slate-50 text-slate-600", XCircle]
    : ["In Process", "border-sky-200 bg-sky-50 text-sky-800", CircleDashed];
  return <span data-testid="task-status" className={cn("inline-flex items-center gap-1 whitespace-nowrap rounded-full border px-2 py-0.5 text-[11px] font-medium", tone)}>
    <Icon className="h-3 w-3" />{label}
  </span>;
}

// Owner request (29 Sep 2026): a filter on every column. Search boxes for text columns, pick lists for the rest.
type Filters = { topic: string; prompt: string; link: string; research: string; task: string; imported: string; action: string };
const NO_FILTERS: Filters = { topic: "", prompt: "", link: "all", research: "all", task: "all", imported: "", action: "all" };
const LINK_KINDS = [
  { key: "with", label: "Has a link" }, { key: "none", label: "No link yet" },
  { key: "gemini", label: "Gemini conversation" }, { key: "other", label: "Other web link" },
] as const;
// Mirrors the Actions column below and the shared rules in components/ResearchLink.tsx.
const ACTIONS: { key: string; label: string; test: (r: Row) => boolean }[] = [
  { key: "paste", label: "Paste link & Proceed", test: canPaste },
  { key: "proceed", label: "Proceed (SEO, thumbnail, schedule)", test: canProceedImported },
  { key: "fetch", label: "Fetch Research", test: canFetch },
  { key: "replace", label: "Replace Existing Research", test: (r) => r.status === "research_exists" },
  { key: "view", label: "View Imported Research", test: (r) => r.status === "research_imported" },
  { key: "reimport", label: "Re-import Research", test: (r) => r.status === "research_imported" && !r.closed },
  { key: "release", label: "Research automatically instead", test: (r) => RESERVED.includes(r.status) && !r.has_research },
  { key: "paste_doc", label: "Paste / Upload Research", test: (r) => !r.closed && !r.auto_running && r.status !== "importing" && r.status !== "ready_to_import" },
];

const contains = (text: string, query: string) => !query.trim() || text.toLowerCase().includes(query.trim().toLowerCase());
function linkKind(r: Row): "none" | "gemini" | "other" {
  const link = r.pending_link || r.link;
  return !link ? "none" : /^https?:\/\/gemini\.google\.com\//i.test(link) ? "gemini" : "other";
}
function matchesLink(r: Row, filter: string) {
  const kind = linkKind(r);
  return filter === "all" || (filter === "with" ? kind !== "none" : kind === filter);
}
function matches(r: Row, f: Filters) {
  return contains([r.title, r.id, r.category, r.website, r.language].join(" "), f.topic)
    && contains(r.prompt ?? "", f.prompt)
    && matchesLink(r, f.link)
    && (f.research === "all" || r.status === f.research)
    && (f.task === "all" || taskState(r.stage) === f.task)
    && contains([r.message, r.source].filter(Boolean).join(" "), f.imported)
    && (f.action === "all" || !!ACTIONS.find((a) => a.key === f.action)?.test(r));
}

const FILTER_FIELD = "h-7 w-full min-w-0 rounded-md border border-slate-200 bg-white/80 px-1.5 text-xs font-normal text-slate-700";
function PickFilter({ label, value, onChange, options }: {
  label: string; value: string; onChange: (value: string) => void; options: { key: string; label: string; count: number }[];
}) {
  return <select aria-label={`Filter by ${label}`} className={cn(FILTER_FIELD, value !== "all" && "border-sky-400 bg-sky-50/60 text-sky-900")}
    value={value} onChange={(e) => onChange(e.target.value)}>
    <option value="all">All</option>
    {options.map((o) => <option key={o.key} value={o.key}>{o.label} ({o.count})</option>)}
  </select>;
}
function TextFilter({ label, value, onChange }: { label: string; value: string; onChange: (value: string) => void }) {
  return <Input aria-label={`Filter by ${label}`} placeholder="Search…" value={value} onChange={(e) => onChange(e.target.value)}
    className={cn("h-7 text-xs font-normal", value.trim() && "border-sky-400 bg-sky-50/60")} />;
}

function toBase64(buffer: ArrayBuffer): string {
  const bytes = new Uint8Array(buffer);
  let binary = "";
  for (let i = 0; i < bytes.length; i += 0x8000) binary += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
  return btoa(binary);
}

// Imported reports are shown as text only (never as page markup).
function reportText(content: string): string {
  const doc = new DOMParser().parseFromString(content, "text/html");
  doc.querySelectorAll("script,style").forEach(e => e.remove());
  return (doc.body.innerText || doc.body.textContent || "").trim();
}

function Summary({ batch }: { batch: Batch }) {
  const c = batch.counts;
  const figures: [string, number][] = [
    ["Total rows", c.total_rows], ["Matched topics", c.matched], ["Research links found", c.links_found],
    ["Reports imported", c.imported], ["Importing now", c.in_progress], ["Invalid links", c.invalid_links],
    ["Access denied", c.access_denied], ["Report not found", c.not_found], ["Import failed", c.failed],
    ["Already have research", c.already_exists], ["Without links", c.without_links], ["Row errors", c.row_errors],
  ];
  return (
    <Card className="surface space-y-3 border-slate-200 p-4" data-testid="manual-import-summary">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="font-medium text-slate-900">Research Excel Import Summary <span className="font-normal text-slate-500">· {batch.filename}</span></div>
        {c.in_progress > 0 && <span className="inline-flex items-center gap-1.5 text-xs text-indigo-700"><Loader2 className="h-3.5 w-3.5 animate-spin" /> Fetching reports one topic at a time…</span>}
      </div>
      {batch.errors.length > 0 && <div className={cn("rounded-lg border p-3 text-sm", PROBLEM)}>{batch.errors.map(e => <div key={e}>{e}</div>)}</div>}
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4 lg:grid-cols-6">
        {figures.map(([label, value]) => <div key={label} className="rounded-lg border border-slate-200 bg-white/60 px-3 py-2">
          <div className="text-[11px] text-slate-500">{label}</div><div className="font-mono text-lg text-slate-900">{value ?? 0}</div>
        </div>)}
      </div>
      {batch.rows.length > 0 && <div className="overflow-x-auto">
        <table className="w-full text-left text-sm">
          <thead className="text-xs text-slate-500"><tr><th className="py-1 pr-3">Row</th><th className="py-1 pr-3">Topic</th><th className="py-1 pr-3">Research Link</th><th className="py-1">Import Result</th></tr></thead>
          <tbody>{batch.rows.map(r => <tr key={`${r.row}-${r.topic_id}`} className="border-t border-slate-100 align-top">
            <td className="py-1.5 pr-3 font-mono text-xs text-slate-500">{r.row}</td>
            <td className="py-1.5 pr-3"><div className="text-slate-900">{r.title || "—"}</div><div className="font-mono text-[10.5px] text-slate-500">{r.topic_id || "no Topic ID"}</div></td>
            <td className="py-1.5 pr-3 text-slate-700">{r.link_state}</td>
            <td className={cn("py-1.5", r.error ? "text-rose-700" : "text-slate-800")}>{r.result}{r.message && <div className="text-xs text-slate-500">{r.message}</div>}</td>
          </tr>)}</tbody>
        </table>
      </div>}
    </Card>
  );
}

const IST = "Asia/Kolkata";
const NY  = "America/New_York";

function fmtTz(ts: string | null | undefined, tz: string, short = false): string {
  if (!ts) return "—";
  try {
    return new Date(ts).toLocaleString("en-IN", {
      timeZone: tz, month: "short", day: "numeric",
      hour: "2-digit", minute: "2-digit", hour12: true,
    });
  } catch { return "—"; }
}

function TimingCell({ row }: { row: Row }) {
  const ts = row.proceed_at || row.imported_at;
  if (!ts) return <span className="text-slate-400">—</span>;
  const label = row.proceed_at ? "Proceeds" : "Imported";
  return (
    <div className="space-y-0.5 text-[11px]">
      <div className="font-medium text-slate-500 uppercase tracking-wide" style={{ fontSize: "10px" }}>{label}</div>
      <div className="flex items-center gap-1 text-slate-700"><span className="rounded bg-violet-50 px-1 py-px text-violet-800">IST</span>{fmtTz(ts, IST)}</div>
      <div className="flex items-center gap-1 text-slate-700"><span className="rounded bg-cyan-50 px-1 py-px text-cyan-800">NY</span>{fmtTz(ts, NY)}</div>
    </div>
  );
}

export default function ManualWorkbench() {
  const qc = useQueryClient();
  const fileInput = useRef<HTMLInputElement>(null);
  const [site, setSite] = useState<"all" | "kannadiga" | "human">("all");
  const [downloading, setDownloading] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [batchId, setBatchId] = useState<string | null>(null);
  const [report, setReport] = useState<Report | null>(null);
  const [filters, setFilters] = useState<Filters>(NO_FILTERS);
  const actions = useResearchActions();

  const { data, isLoading } = useQuery({
    queryKey: ["manual-research"], queryFn: () => apiGet<{ rows: Row[] }>("/manual-research"), refetchInterval: 8000,
  });
  const { data: batch } = useQuery({
    queryKey: ["manual-import", batchId], enabled: !!batchId,
    queryFn: () => apiGet<Batch>(`/manual-research/imports/${batchId}`),
    refetchInterval: (query) => ((query.state.data as Batch | undefined)?.counts?.in_progress ? 4000 : false),
  });
  const { data: stats } = useStats();
  const { data: todayCounts = {} } = useQuery<Record<string, number>>({
    queryKey: ["manual-today-stats"],
    queryFn: () => apiGet<Record<string, number>>("/manual-research/today-stats"),
    refetchInterval: 30_000,
  });
  const autoOff = stats?.system?.auto_research === false;
  const rows = (data?.rows ?? []).filter(r => site === "all" || r.site_key === site);
  const shown = rows.filter(r => matches(r, filters));
  const filtering = (Object.keys(NO_FILTERS) as (keyof Filters)[]).some(k => filters[k] !== NO_FILTERS[k]);
  const filterBy = (key: keyof Filters) => (value: string) => setFilters(f => ({ ...f, [key]: value }));
  const count = (test: (r: Row) => boolean) => rows.filter(test).length;
  const researchOptions = [...new Map(rows.map(r => [r.status, r.status_label])).entries()]
    .map(([key, label]) => ({ key, label, count: count(r => r.status === key) }));

  const download = async () => {
    setDownloading(true);
    try {
      const res = await fetch("/api/manual-research/export", { credentials: "same-origin" });
      if (!res.ok) throw new Error((await res.json().catch(() => null))?.detail ?? `Download failed (${res.status})`);
      const count = res.headers.get("X-Topic-Count") ?? "0";
      const name = /filename="([^"]+)"/.exec(res.headers.get("Content-Disposition") ?? "")?.[1] ?? "research-topics.xlsx";
      const url = URL.createObjectURL(await res.blob());
      const link = document.createElement("a");
      link.href = url; link.download = name; document.body.appendChild(link); link.click(); link.remove();
      setTimeout(() => URL.revokeObjectURL(url), 5000);
      toast.success(`Research Excel downloaded · ${count} topic(s)`, { description: "These topics are reserved for your manual research; the app will not research them itself." });
      actions.refresh();
    } catch (e) { toast.error(e instanceof Error ? e.message : "Download failed"); }
    finally { setDownloading(false); }
  };

  const upload = async (file: File | undefined) => {
    if (!file) return;
    if (!/\.xlsx$/i.test(file.name)) { toast.error("Choose the .xlsx workbook downloaded from this page"); return; }
    setUploading(true);
    try {
      const result = await apiPost<Batch>("/manual-research/import", { filename: file.name, content_b64: toBase64(await file.arrayBuffer()) });
      setBatchId(result.id);
      qc.setQueryData(["manual-import", result.id], result);
      if (result.errors.length) toast.error(result.errors[0]);
      else toast.success(`Uploaded · ${result.counts.links_found} research link(s) found`, { description: "Reports are fetched one topic at a time." });
      actions.refresh();
    } catch (e) { toast.error(e instanceof Error ? e.message : "Upload failed"); }
    finally { setUploading(false); if (fileInput.current) fileInput.current.value = ""; }
  };

  const viewReport = async (row: Row) => {
    try { setReport(await apiGet<Report>(`/manual-research/${row.id}/report`)); }
    catch (e) { toast.error(e instanceof Error ? e.message : "Could not load the report"); }
  };

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <SectionLabel>Manual Editorial Workbench</SectionLabel>
          <h1 className="page-title">Manual Research</h1>
          <p className="page-lede">One Topic ID → one research prompt → one external research → one report link → one imported report. For one topic, paste its research link in its row (or on the post in the Editorial Workbench) and press Proceed; for many, download the workbook, paste each link into its row, then upload it.</p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button onClick={download} disabled={downloading} className="gap-1.5" data-testid="manual-download">
            {downloading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Download className="h-4 w-4" />} Download Research Excel
          </Button>
          <Button variant="outline" onClick={() => fileInput.current?.click()} disabled={uploading} className="gap-1.5" data-testid="manual-upload">
            {uploading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Upload className="h-4 w-4" />} Upload Research Excel
          </Button>
          <input ref={fileInput} type="file" accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" className="hidden"
            onChange={(e) => upload(e.target.files?.[0])} />
        </div>
      </div>

      <div className={cn("rounded-lg border px-4 py-2.5 text-sm", autoOff ? "border-amber-200/70 bg-amber-50/40 text-amber-900" : "border-slate-200 bg-white/50 text-slate-600")}>
        {autoOff ? <><strong>Automatic research is off</strong> (Editorial Workbench switch): every topic here waits for its research link.</>
          : <>Automatic research is on: topics you have not downloaded are researched by the app in turn. Downloaded topics are reserved for you.</>}
      </div>

      {batch && <Summary batch={batch} />}

      <div className="flex flex-wrap items-center justify-between gap-2">
        <SiteSwitch value={site} onChange={setSite} allLabel="All" />
        {filtering && <div className="flex items-center gap-2 text-xs text-slate-600" data-testid="manual-filter-summary">
          Showing {shown.length} of {rows.length} topic(s)
          <Button size="sm" variant="ghost" className="h-7 gap-1 text-xs" onClick={() => setFilters(NO_FILTERS)}><X className="h-3 w-3" /> Clear filters</Button>
        </div>}
      </div>

      {isLoading ? <div className="flex items-center gap-2 text-sm text-slate-600"><Loader2 className="h-4 w-4 animate-spin" /> Loading topics…</div>
        : rows.length === 0 ? <EmptyState title="No topics are waiting for research" hint="Topics queued in the Editorial Workbench appear here until their research is in." />
        : <Card className="surface overflow-x-auto border-slate-200 p-0">
          <table className="w-full min-w-[1440px] text-left text-sm">
            <thead className="border-b border-slate-200 text-xs text-slate-500">
              <tr><th className="px-3 py-2">Topic</th><th className="px-3 py-2">Research Prompt</th><th className="px-3 py-2">Research Report Link</th><th className="px-3 py-2">Research Content</th><th className="px-3 py-2">Research Status</th><th className="px-3 py-2">Task Completion Status</th><th className="px-3 py-2 whitespace-nowrap">Posted Today (IST)</th><th className="px-3 py-2 whitespace-nowrap">IST / US Time</th><th className="px-3 py-2">Import Status</th><th className="px-3 py-2">Actions</th></tr>
              <tr className="border-t border-slate-100 bg-slate-50/50" data-testid="manual-filters">
                <th className="px-3 py-1.5"><TextFilter label="topic" value={filters.topic} onChange={filterBy("topic")} /></th>
                <th className="px-3 py-1.5"><TextFilter label="research prompt" value={filters.prompt} onChange={filterBy("prompt")} /></th>
                <th className="px-3 py-1.5"><PickFilter label="research report link" value={filters.link} onChange={filterBy("link")}
                  options={LINK_KINDS.map(k => ({ key: k.key, label: k.label, count: count(r => matchesLink(r, k.key)) }))} /></th>
                <th className="px-3 py-1.5" />
                <th className="px-3 py-1.5"><PickFilter label="research status" value={filters.research} onChange={filterBy("research")} options={researchOptions} /></th>
                <th className="px-3 py-1.5"><PickFilter label="task completion status" value={filters.task} onChange={filterBy("task")}
                  options={TASK_STATES.map(s => ({ key: s.key, label: s.label, count: count(r => taskState(r.stage) === s.key) }))} /></th>
                <th className="px-3 py-1.5" />
                <th className="px-3 py-1.5" />
                <th className="px-3 py-1.5"><TextFilter label="import status" value={filters.imported} onChange={filterBy("imported")} /></th>
                <th className="px-3 py-1.5"><PickFilter label="available action" value={filters.action} onChange={filterBy("action")}
                  options={ACTIONS.map(a => ({ key: a.key, label: a.label, count: count(a.test) }))} /></th>
              </tr>
            </thead>
            <tbody>{shown.map(r => {
              const busy = actions.busyId === r.id;
              return <tr key={r.id} className="border-b border-slate-100 align-top" data-testid={`manual-row-${r.id}`}>
                <td className="max-w-[320px] px-3 py-2.5">
                  <div className="font-medium text-slate-900">{r.title}</div>
                  <div className="mt-1 flex flex-wrap items-center gap-1.5 text-[11px] text-slate-500"><SiteBadge siteKey={r.site_key} small />{r.language}{r.category && <span>· {r.category}</span>}</div>
                  <div className="mt-1 break-all font-mono text-[10.5px] text-slate-400" title="Topic ID">{r.id}</div>
                </td>
                <td className="max-w-[300px] px-3 py-2.5">
                  {r.prompt ? <PromptPreview prompt={r.prompt} compact /> : <div className="text-xs text-slate-600">—</div>}
                  {r.prompt && <button type="button" className="mt-1 inline-flex items-center gap-1 text-xs text-sky-700 hover:underline" onClick={() => actions.copyPrompt(r)}><ClipboardCopy className="h-3 w-3" /> Copy Research Prompt</button>}
                </td>
                <td className="max-w-[300px] px-3 py-2.5 text-xs">
                  <ResearchLinkInput row={r} disabled={busy} onProceed={actions.proceed} />
                </td>
                <td className="px-3 py-2.5">
                  <ResearchPasteUpload row={r} onDone={actions.refresh} />
                </td>
                <td className="px-3 py-2.5">
                  <StatusPill status={r.status} label={r.status_label} />
                  {r.auto_running && <div className="mt-1 text-[11px] text-slate-500">The app is researching it now</div>}
                  {(r.has_research || r.closed) && <div className="mt-1.5"><StageBadge stage={r.stage} heldReason={r.held_reason} /></div>}
                  {r.proceed_at && !r.closed && <div className="mt-1 text-[11px] font-medium text-indigo-700">Goes next · Proceed {fmtTime(r.proceed_at)}</div>}
                </td>
                <td className="px-3 py-2.5"><TaskStatus stage={r.stage} /></td>
                <td className="px-3 py-2.5">
                  <div className="space-y-1">
                    {todayCounts[r.site_key] != null ? (
                      <div className="inline-flex items-center gap-1 rounded-full border border-emerald-200 bg-emerald-50 px-2 py-0.5 text-[11px] font-medium text-emerald-800">
                        <Clock className="h-2.5 w-2.5" />{todayCounts[r.site_key]} posted today
                      </div>
                    ) : <span className="text-[11px] text-slate-400">0 today</span>}
                    <div className="text-[10px] text-slate-400">
                      {new Date().toLocaleDateString("en-IN", { timeZone: IST, weekday: "short", month: "short", day: "numeric" })}
                    </div>
                  </div>
                </td>
                <td className="px-3 py-2.5"><TimingCell row={r} /></td>
                <td className="max-w-[240px] px-3 py-2.5 text-xs text-slate-600">{r.message || "—"}{r.imported_at && <div className="text-[11px] text-slate-400">{fmtTime(r.imported_at)}</div>}</td>
                <td className="px-3 py-2.5">
                  <div className="flex flex-col items-start gap-1 text-xs">
                    <a className="inline-flex items-center gap-1 text-sky-700 hover:underline" href={`/articles?open=${r.id}`}><Eye className="h-3 w-3" /> View Topic</a>
                    <ResearchFollowUps row={r} busy={busy} actions={actions} className="flex-col items-start" />
                    {r.status === "research_imported" && <>
                      <button type="button" className="inline-flex items-center gap-1 text-sky-700 hover:underline" onClick={() => viewReport(r)}><FileSpreadsheet className="h-3 w-3" /> View Imported Research</button>
                      {!r.closed && <button type="button" disabled={busy} className="inline-flex items-center gap-1 text-slate-600 hover:underline" onClick={() => actions.fetchResearch(r, true)}><RefreshCw className="h-3 w-3" /> Re-import Research</button>}
                    </>}
                    {RESERVED.includes(r.status) && !r.has_research && <button type="button" disabled={busy} className="inline-flex items-center gap-1 text-slate-500 hover:underline"
                      onClick={() => actions.release(r)}><Undo2 className="h-3 w-3" /> Research automatically instead</button>}
                  </div>
                </td>
              </tr>;
            })}
            {shown.length === 0 && <tr><td colSpan={10} className="px-3 py-8 text-center text-sm text-slate-500">
              No topics match these filters. <button type="button" className="text-sky-700 hover:underline" onClick={() => setFilters(NO_FILTERS)}>Clear filters</button>
            </td></tr>}</tbody>
          </table>
        </Card>}

      <Dialog open={!!report} onOpenChange={(open) => !open && setReport(null)}>
        <DialogContent className="max-w-3xl">
          <DialogHeader>
            <DialogTitle>Imported research</DialogTitle>
            <DialogDescription>{report?.title}{report?.link && /^https?:\/\//i.test(report.link) && <> · <a className="text-sky-700 underline" href={report.link} target="_blank" rel="noreferrer">source link</a></>}</DialogDescription>
          </DialogHeader>
          <div className="max-h-[60vh] overflow-y-auto whitespace-pre-wrap rounded-lg border border-slate-200 bg-white/70 p-3 text-sm text-slate-800">{report ? reportText(report.report).slice(0, 60000) || "No report content is stored." : ""}</div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
