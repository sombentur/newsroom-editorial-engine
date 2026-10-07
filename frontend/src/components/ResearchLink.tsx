// One research-link box for both workbenches (owner request, 29 Sep 2026): a Manual Workbench row and an Editorial
// Workbench post show the same research prompt copy, link box, Proceed and follow-up actions, on the same endpoints
// (backend/routers/manual_research.py).
import { useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowRight, ClipboardPaste, ClipboardCopy, ExternalLink, FileUp, Loader2, RefreshCw } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { apiGet, apiPost } from "@/lib/api";
import { fmtTime, SectionLabel } from "@/lib/ui";
import { cn } from "@/lib/utils";

export type ManualRow = {
  id: string; title: string; site_key: string; website: string; language: string; category: string; prompt: string;
  link: string; pending_link: string; status: string; status_label: string; message: string; imported_at: string | null;
  chars: number | null; source: string | null; stage: string; has_research: boolean; auto_running: boolean; exportable: boolean;
  held_reason: string | null; proceed_at: string | null; closed: boolean;
};

export const PROBLEM = "border-rose-200 bg-rose-50 text-rose-800";
const TONE: Record<string, string> = {
  pending: "border-slate-200 bg-slate-50 text-slate-700",
  excel_exported: "border-sky-200 bg-sky-50 text-sky-800",
  link_added: "border-sky-200 bg-sky-50 text-sky-800",
  ready_to_import: "border-indigo-200 bg-indigo-50 text-indigo-800",
  importing: "border-indigo-200 bg-indigo-50 text-indigo-800",
  research_imported: "border-emerald-200 bg-emerald-50 text-emerald-800",
  research_exists: "border-amber-200 bg-amber-50 text-amber-800",
  link_invalid: PROBLEM, access_denied: PROBLEM, report_not_found: PROBLEM, import_failed: PROBLEM,
};
const WEB_LINK = /^https?:\/\/\S+$/i;
const IN_FLIGHT = ["importing", "ready_to_import"];

// When each research action is offered (the Manual Workbench's Actions filter uses these same rules).
export const canPaste = (row: ManualRow) => !row.has_research && !row.closed && !row.auto_running && !IN_FLIGHT.includes(row.status);
export const canFetch = (row: ManualRow) => !!row.link && !row.has_research && !row.closed && !IN_FLIGHT.includes(row.status);
export const canProceedImported = (row: ManualRow) =>
  row.status === "research_imported" && !row.closed && !row.proceed_at && ["selected", "held_review", "researching"].includes(row.stage);

export function StatusPill({ status, label }: { status: string; label: string }) {
  return <span className={cn("inline-flex items-center gap-1 whitespace-nowrap rounded-full border px-2 py-0.5 text-[11px] font-medium", TONE[status] ?? TONE.pending)}>
    {status === "importing" && <Loader2 className="h-3 w-3 animate-spin" />}{label}
  </span>;
}

// The research prompt, read only (owner request, 29 Sep 2026: check the pasted link belongs to this prompt).
export function PromptPreview({ prompt, compact }: { prompt: string; compact?: boolean }) {
  const [open, setOpen] = useState(false);
  const long = prompt.length > (compact ? 180 : 600);
  return (
    <div>
      <div data-testid="research-prompt-text" className={cn("whitespace-pre-wrap break-words text-xs",
        compact ? "text-slate-600" : "rounded-md border border-slate-200 bg-white/70 p-2.5 leading-relaxed text-slate-700",
        open ? "max-h-80 overflow-y-auto" : long && (compact ? "line-clamp-3" : "line-clamp-6"))}>{prompt}</div>
      {long && <button type="button" className="mt-0.5 text-[11px] text-slate-500 hover:text-slate-800 hover:underline" onClick={() => setOpen(!open)}>
        {open ? "Show less" : "Show full prompt"}
      </button>}
    </div>
  );
}

// The link (when there is one) and, while the post still needs its research, the paste box with Proceed.
export function ResearchLinkInput({ row, disabled, onProceed }: { row: ManualRow; disabled: boolean; onProceed: (row: ManualRow, url?: string) => void }) {
  const [value, setValue] = useState("");
  const link = row.pending_link || row.link;
  const pasteBox = canPaste(row);
  const valid = WEB_LINK.test(value.trim());
  return (
    <div className="space-y-1.5">
      {link && (WEB_LINK.test(link)
        ? <a className="inline-flex items-center gap-1 break-all text-sky-700 hover:underline" href={link} target="_blank" rel="noreferrer"><ExternalLink className="h-3 w-3 shrink-0" />{link}</a>
        : /^(?:uploaded|pasted)\b/i.test(link)
          ? <span className="inline-flex items-start gap-1 break-all text-slate-700"><FileUp className="mt-0.5 h-3 w-3 shrink-0 text-slate-500" />{/^uploaded:/i.test(link) ? "Uploaded document · " + link.replace(/^uploaded:\s*/i, "") : "Pasted research"}</span>
          : <span className="break-all text-rose-700">{link}</span>)}
      {!link && !pasteBox && <span className="text-slate-400">—</span>}
      {pasteBox && <div className="flex items-center gap-1.5">
        <Input className="h-8 min-w-[180px] text-xs" aria-label={`Research report link for ${row.title}`} value={value}
          placeholder={link ? "Paste a new link…" : "Paste the research link…"} onChange={(e) => setValue(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter" && valid) { onProceed(row, value.trim()); setValue(""); } }} />
        <Button size="sm" className="h-8 gap-1" disabled={disabled || !(valid || (link && !value.trim()))}
          onClick={() => { onProceed(row, value.trim() || undefined); setValue(""); }} data-testid={`research-proceed-${row.id}`}>
          Proceed <ArrowRight className="h-3 w-3" />
        </Button>
      </div>}
      {pasteBox && value.trim() && !valid && <div className="text-[11px] text-rose-700">Paste a full link starting with https://</div>}
    </div>
  );
}

// The research actions, identical wherever they are offered.
export function useResearchActions() {
  const qc = useQueryClient();
  const [busyId, setBusyId] = useState<string | null>(null);
  const refresh = () => {
    for (const key of ["manual-research", "manual-row", "manual-import", "articles", "article"]) qc.invalidateQueries({ queryKey: [key] });
  };
  const run = async (row: ManualRow, path: string, body: unknown, done: string, description?: string) => {
    setBusyId(row.id);
    try { await apiPost(path, body); toast.success(done, description ? { description } : undefined); refresh(); }
    catch (e) { toast.error(e instanceof Error ? e.message : "Action failed"); }
    finally { setBusyId(null); }
  };
  const proceed = (row: ManualRow, url?: string) => run(row, `/manual-research/${row.id}/proceed`, url ? { url } : {},
    row.has_research ? "Proceeding: SEO, thumbnail and scheduling follow" : "Fetching the report; then SEO, thumbnail and scheduling follow",
    "This topic goes first in line (it starts as soon as no other article is in production).");
  const fetchResearch = (row: ManualRow, replace: boolean) => {
    if (replace && !window.confirm(`Replace the existing research of “${row.title}” with the report at this link?\n\n${row.pending_link || row.link}\n\nIts article, SEO and thumbnail are made again from the new report.`)) return;
    run(row, `/manual-research/${row.id}/fetch`, { replace }, replace ? "Replacing the research: fetching the report" : "Fetching the research report");
  };
  const release = (row: ManualRow) => {
    if (!window.confirm(`Let the app research “${row.title}” automatically instead?`)) return;
    run(row, `/manual-research/${row.id}/release`, {}, "Returned to automatic research");
  };
  const copyPrompt = async (row: ManualRow) => {
    try { await navigator.clipboard.writeText(row.prompt); toast.success("Research prompt copied"); }
    catch { toast.error("Copying is not allowed here; select the prompt text instead"); }
  };
  return { busyId, proceed, fetchResearch, release, copyPrompt, refresh };
}

// The buttons that follow the link: Replace, Fetch again, and Proceed for a report that came in without one.
export function ResearchFollowUps({ row, busy, actions, className }: {
  row: ManualRow; busy: boolean; actions: ReturnType<typeof useResearchActions>; className?: string;
}) {
  const button = "inline-flex items-center gap-1 hover:underline disabled:opacity-50";
  return <div className={cn("flex flex-wrap items-center gap-x-3 gap-y-1 text-xs", className)}>
    {row.status === "research_exists" && <button type="button" disabled={busy} className={cn(button, "text-amber-800")} onClick={() => actions.fetchResearch(row, true)}><RefreshCw className="h-3 w-3" /> Replace Existing Research</button>}
    {canFetch(row) && <button type="button" disabled={busy} className={cn(button, "text-sky-700")} onClick={() => actions.fetchResearch(row, false)}><RefreshCw className="h-3 w-3" /> Fetch Research</button>}
    {canProceedImported(row) &&
      <button type="button" disabled={busy} className={cn(button, "font-medium text-indigo-700")} onClick={() => actions.proceed(row)}><ArrowRight className="h-3 w-3" /> Proceed (SEO, thumbnail, schedule)</button>}
  </div>;
}

function toBase64(buffer: ArrayBuffer): string {
  const bytes = new Uint8Array(buffer);
  let binary = "";
  for (let i = 0; i < bytes.length; i += 0x8000) binary += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
  return btoa(binary);
}

// Paste / Upload Research popup — Manual Workbench column + Editorial Workbench panel.
export function ResearchPasteUpload({ row, onDone }: { row: ManualRow; onDone: () => void }) {
  const [open, setOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const editorRef = useRef<HTMLDivElement>(null);
  const [hasContent, setHasContent] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  if (row.closed || row.auto_running || IN_FLIGHT.includes(row.status)) return null;

  const confirmReplace = (label: string) =>
    !row.has_research || window.confirm(`Replace the existing research for "${row.title}" with ${label}?`);

  const handleSave = async () => {
    const html = editorRef.current?.innerHTML ?? "";
    if (!html.trim() || html === "<br>") { toast.error("Paste or type research content first."); return; }
    if (!confirmReplace("this pasted content")) return;
    setSaving(true);
    try {
      await apiPost(`/manual-research/${row.id}/paste-content`, { html, replace: row.has_research });
      toast.success("Research saved — SEO, thumbnail and scheduling follow");
      setOpen(false); onDone();
    } catch (e) { toast.error(e instanceof Error ? e.message : "Save failed"); }
    finally { setSaving(false); }
  };

  const fileToDataUrl = (file: File): Promise<string> =>
    new Promise((res, rej) => { const r = new FileReader(); r.onload = () => res(r.result as string); r.onerror = rej; r.readAsDataURL(file); });

  const insertNodeAtCursor = (node: Node) => {
    const sel = window.getSelection();
    if (!sel || !sel.rangeCount) { editorRef.current?.appendChild(node); return; }
    const range = sel.getRangeAt(0);
    range.deleteContents();
    range.insertNode(node);
    range.setStartAfter(node);
    range.collapse(true);
    sel.removeAllRanges();
    sel.addRange(range);
  };

  const handlePaste = async (e: React.ClipboardEvent<HTMLDivElement>) => {
    const items = Array.from(e.clipboardData.items);
    const hasHtml = items.some(i => i.type === "text/html");
    const imgItems = items.filter(i => i.type.startsWith("image/"));
    // Raw image only (screenshot, no HTML wrapper) — convert to data URI and insert
    if (!hasHtml && imgItems.length > 0) {
      e.preventDefault();
      for (const imgItem of imgItems) {
        const file = imgItem.getAsFile();
        if (!file) continue;
        const dataUrl = await fileToDataUrl(file);
        const img = document.createElement("img");
        img.src = dataUrl;
        img.style.cssText = "max-width:100%;height:auto;display:block;margin:.5rem 0";
        insertNodeAtCursor(img);
      }
      setHasContent(true);
      return;
    }
    // HTML paste (Google Docs / Word): browser pastes HTML natively preserving tables/formatting.
    // If clipboard also carries image blobs (one per img tag), inline them as data URIs so they
    // survive outside Google's CDN.
    if (hasHtml && imgItems.length > 0) {
      e.preventDefault();
      const htmlStr = await new Promise<string>(res => items.find(i => i.type === "text/html")!.getAsString(res));
      const files = imgItems.map(i => i.getAsFile()).filter(Boolean) as File[];
      const dataUrls = await Promise.all(files.map(fileToDataUrl));
      const doc = new DOMParser().parseFromString(htmlStr, "text/html");
      doc.querySelectorAll("img").forEach((img, idx) => {
        if (dataUrls[idx]) { img.src = dataUrls[idx]; img.style.maxWidth = "100%"; }
      });
      const cleaned = doc.body.innerHTML;
      const range = window.getSelection()?.getRangeAt(0);
      if (range) {
        range.deleteContents();
        const frag = range.createContextualFragment(cleaned);
        range.insertNode(frag);
        range.collapse(false);
      } else {
        editorRef.current?.insertAdjacentHTML("beforeend", cleaned);
      }
      setHasContent(!!(editorRef.current?.textContent?.trim()));
      return;
    }
    // No images — let the browser's default paste handle it (plain text or HTML without images)
  };

  const handleFile = async (file: File | undefined) => {
    if (!file) return;
    if (!/\.(docx|pdf)$/i.test(file.name)) { toast.error("Choose a Word (.docx) or PDF (.pdf) file"); return; }
    if (!confirmReplace(`"${file.name}"`)) return;
    setSaving(true);
    try {
      const b64 = toBase64(await file.arrayBuffer());
      await apiPost(`/manual-research/${row.id}/upload-document`, { filename: file.name, content_b64: b64, replace: row.has_research });
      toast.success("Document imported — SEO, thumbnail and scheduling follow");
      setOpen(false); onDone();
    } catch (e) { toast.error(e instanceof Error ? e.message : "Upload failed"); }
    finally { setSaving(false); if (fileRef.current) fileRef.current.value = ""; }
  };

  return (
    <>
      <div className="flex flex-col items-start gap-1">
        <button type="button" className="inline-flex items-center gap-1 text-xs text-indigo-700 hover:underline" onClick={() => setOpen(true)}>
          <ClipboardPaste className="h-3 w-3" /> Paste Research
        </button>
        <button type="button" className="inline-flex items-center gap-1 text-xs text-slate-600 hover:underline" onClick={() => fileRef.current?.click()}>
          <FileUp className="h-3 w-3" /> Upload Word / PDF
        </button>
        <input ref={fileRef} type="file"
          accept=".docx,.pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document,application/pdf"
          className="hidden" onChange={(e) => { handleFile(e.target.files?.[0]); }} />
      </div>

      <Dialog open={open} onOpenChange={(v) => { if (!saving) setOpen(v); }}>
        <DialogContent className="flex max-h-[90vh] w-[90vw] max-w-5xl flex-col gap-0 p-0">
          <DialogHeader className="border-b border-slate-200 px-6 pb-3 pt-5">
            <DialogTitle className="flex items-center gap-2">
              <ClipboardPaste className="h-4 w-4 text-indigo-600" /> Paste Research
            </DialogTitle>
            <DialogDescription className="text-xs">
              {row.title} — paste from Google Docs, Word, or any document. Tables and formatting are preserved.
            </DialogDescription>
          </DialogHeader>
          <div className="flex-1 overflow-y-auto bg-slate-50 p-4">
            <style>{`
              .doc-editor table{border-collapse:collapse;width:100%;margin:.5rem 0}
              .doc-editor td,.doc-editor th{border:1px solid #cbd5e1;padding:.35rem .6rem;vertical-align:top}
              .doc-editor th{background:#f1f5f9;font-weight:600}
              .doc-editor h1{font-size:1.4rem;font-weight:700;margin:.7rem 0 .3rem}
              .doc-editor h2{font-size:1.2rem;font-weight:700;margin:.5rem 0 .2rem}
              .doc-editor h3{font-size:1.05rem;font-weight:600;margin:.4rem 0 .2rem}
              .doc-editor p{margin:.3rem 0}
              .doc-editor ul,.doc-editor ol{padding-left:1.5rem;margin:.3rem 0}
              .doc-editor img{max-width:100%;height:auto;display:block;margin:.5rem 0;border-radius:4px}
            `}</style>
            <div className="relative">
              {!hasContent && (
                <div className="pointer-events-none absolute left-8 top-8 text-[15px] leading-relaxed text-slate-400">
                  Paste your research here (Ctrl+V from Google Docs or Word) — text, tables and images are all preserved…
                </div>
              )}
              <div
                ref={editorRef}
                contentEditable
                suppressContentEditableWarning
                className="doc-editor min-h-[52vh] rounded-md bg-white px-8 py-8 text-[15px] leading-relaxed text-slate-900 shadow-sm outline-none"
                style={{ fontFamily: "Georgia, 'Times New Roman', serif" }}
                onPaste={handlePaste}
                onInput={() => setHasContent(!!(editorRef.current?.textContent?.trim()))}
              />
            </div>
          </div>
          <div className="flex items-center justify-between gap-3 border-t border-slate-200 px-6 py-3">
            <div className="flex items-center gap-2">
              <Button size="sm" variant="outline" className="gap-1.5 text-xs" onClick={() => fileRef.current?.click()} disabled={saving}>
                <FileUp className="h-3.5 w-3.5" /> Upload Word / PDF
              </Button>
              <span className="text-[11px] text-slate-400">or paste content above</span>
            </div>
            <div className="flex gap-2">
              <Button size="sm" variant="ghost" onClick={() => setOpen(false)} disabled={saving}>Cancel</Button>
              <Button size="sm" className="gap-1.5" onClick={handleSave} disabled={saving || !hasContent}>
                {saving ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <ArrowRight className="h-3.5 w-3.5" />} Save Research
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </>
  );
}

// The Editorial Workbench's box for a post that still needs its research: the same as its Manual Workbench row.
export function ResearchPanel({ articleId }: { articleId: string }) {
  const { data: row } = useQuery({
    queryKey: ["manual-row", articleId], queryFn: () => apiGet<ManualRow>(`/manual-research/${articleId}`), refetchInterval: 6000,
  });
  const actions = useResearchActions();
  if (!row || row.closed) return null;
  const busy = actions.busyId === row.id;
  return (
    <div className="space-y-2 rounded-lg border border-sky-200/70 bg-sky-50/20 p-3" data-testid="research-link-panel">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <SectionLabel>Research link</SectionLabel>
        <StatusPill status={row.status} label={row.status_label} />
      </div>
      {row.auto_running && <p className="text-xs text-slate-600">The app is researching this post now.</p>}
      {row.message && <p className="text-xs text-slate-600">{row.message}{row.imported_at && <span className="text-slate-400"> · {fmtTime(row.imported_at)}</span>}</p>}
      {row.prompt && <div className="space-y-1">
        <div className="text-[11px] font-medium uppercase tracking-wide text-slate-500">Research prompt</div>
        <PromptPreview prompt={row.prompt} />
      </div>}
      <div className="flex flex-wrap items-center gap-2">
        {row.prompt && <Button size="sm" variant="outline" className="h-8 gap-1.5" onClick={() => actions.copyPrompt(row)}><ClipboardCopy className="h-3.5 w-3.5" /> Copy Research Prompt</Button>}
        <ResearchFollowUps row={row} busy={busy} actions={actions} />
      </div>
      <ResearchLinkInput row={row} disabled={busy} onProceed={actions.proceed} />
      {row.proceed_at && <p className="text-[11px] font-medium text-indigo-700">Goes next · Proceed {fmtTime(row.proceed_at)}</p>}
      <div className="border-t border-slate-100 pt-2">
        <div className="mb-1 text-[11px] font-medium uppercase tracking-wide text-slate-500">Paste or Upload Research</div>
        <ResearchPasteUpload row={row} onDone={actions.refresh} />
      </div>
      <p className="text-[11px] text-slate-500">Same as the Manual Workbench: run the research prompt on its own, paste the finished report's link (a Gemini conversation, or a document shared with anyone who has the link) and press Proceed. The report is fetched, then SEO, thumbnail and scheduling follow.</p>
    </div>
  );
}
