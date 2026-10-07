// MAINTAINER NOTE (2026-09-27): WORKBENCH UI: Status filters constrain bulk actions to visible eligible items; hidden/terminal/running work must not be accidentally approved. Go ahead applies to research warnings only. Browser failures need job recovery, not editorial approval. Independent desktop scroll panels preserve list position.
import DOMPurify from "dompurify";
import { useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import {
  BadgeCheck, CheckCircle2, Download, FileText, ImageIcon, Loader2, RefreshCw, Rocket, Save,
  Send, ShieldAlert, Sparkles, Square, ThumbsDown, ThumbsUp, Upload, XCircle,
} from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { apiPatch, apiPost } from "@/lib/api";
import { useQueryClient } from "@tanstack/react-query";
import { useArticle, useArticleAction, useArticles, useStats, useUpdateSystem } from "@/lib/hooks";
import { EmptyState, RiskBadge, SectionLabel, SiteBadge, SiteSwitch, SITE_META, StageBadge, workflowStageLabel, TECHNICAL_HOLD, fmtTime } from "@/lib/ui";
import type { Article, GateCheck, SystemSettings } from "@/lib/types";
import { cn } from "@/lib/utils";
import { ResearchPanel } from "@/components/ResearchLink";

const LIVE_STAGES: Record<string, { label: string; detail: string; step: number }> = {
  researching: { label: "Deep Research in progress", detail: "The selected research provider is gathering sources or the saved report is being formatted. You can leave this page.", step: 1 },
  research_validated: { label: "Research validated", detail: "Research is ready. Waiting for an article-writing slot; writing and images continue automatically.", step: 2 },
  writing_article: { label: "Writing and auditing article", detail: "The selected writing provider is preparing the article and running its language checks.", step: 2 },
  article_validated: { label: "Article validated", detail: "The draft passed its checks; thumbnail generation starts next.", step: 3 },
  generating_image: { label: "Generating featured image", detail: "The selected image provider is creating the 16:9 thumbnail and the app will attach it automatically.", step: 3 },
  image_ready: { label: "Workflow complete", detail: "Research, article, and featured image are ready for your review.", step: 4 },
};

function GateList({ checks, title }: { checks: GateCheck[]; title: string }) {
  return (
    <div>
      <SectionLabel>{title}</SectionLabel>
      <div className="mt-2 space-y-1.5">
        {checks.map((c) => (
          <div key={c.name} className="flex items-start justify-between gap-2 rounded border border-slate-200 bg-slate-50/40 px-3 py-1.5">
            <div className="min-w-0">
              <div className="font-mono text-xs text-slate-700">{c.name}</div>
              {c.note && <div className="truncate text-[11px] text-slate-500">{c.note}</div>}
            </div>
            {c.passed ? <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-emerald-600" /> : <XCircle className="mt-0.5 h-4 w-4 shrink-0 text-red-600" />}
          </div>
        ))}
      </div>
    </div>
  );
}

function ProcessMonitor({ a, system }: { a: Article; system?: SystemSettings }) {
  const [now, setNow] = useState(Date.now());
  useEffect(() => { const timer = setInterval(() => setNow(Date.now()), 1000); return () => clearInterval(timer); }, []);
  const flow = [["selected", "Topic queued"], ["research_validated", "Research validated"], ["article_validated", "Article validated"], ["image_ready", "Image attached"]] as const;
  const rank: Record<string, number> = { selected: 0, researching: 1, research_validated: 2, writing_article: 2, article_generated: 2, article_validated: 3, generating_image: 3, image_ready: 4 };
  const currentRank = rank[a.stage] ?? (a.image ? 4 : a.article ? 3 : a.dossier ? 2 : 0);
  const restrictions = [
    system?.dry_run && "Local launcher has DRY_RUN enabled, so WordPress writes are blocked.",
    system?.repair_lock && "The persistent repair lock has not been released.",
    !system?.scheduler_enabled && "The background scheduler is disabled.",
    system?.mode !== "auto" && `Operating mode is ${system?.mode ?? "loading"}; publishing requires Auto mode.`,
    system?.global_paused && "The app is paused.", system?.killswitch && "Stop All is active.",
    !a.article && "The article has not been generated.",
    !a.quality_gate?.passed && "The article quality gate has not passed.",
    !a.image && "A featured image has not been attached.",
  ].filter(Boolean) as string[];
  const events = [...(a.history ?? [])].reverse();
  const activeStages = ["researching", "writing_article", "generating_image"];
  const activelyRunning = activeStages.includes(a.stage);
  const activeEvent = events.find(event => event.stage === a.stage);
  const elapsedSeconds = activeEvent ? Math.max(0, Math.floor((now - new Date(activeEvent.at).getTime()) / 1000)) : 0;
  const elapsed = `${Math.floor(elapsedSeconds / 60)}m ${elapsedSeconds % 60}s`;

  return <div className="space-y-4" data-testid="process-monitor">
    <div><SectionLabel>Live workflow</SectionLabel><div className="mt-2 grid gap-2 sm:grid-cols-2 xl:grid-cols-4">{flow.map(([stage, label], index) => {
      const complete = currentRank > index;
      const active = currentRank === index && currentRank < 4 && activelyRunning;
      const blocked = currentRank === index && a.stage === "held_review";
      const shownLabel = blocked && index === 2 ? "Article blocked" : blocked && index === 3 ? "Image blocked" : label;
      return <div key={stage} className={cn("rounded-lg border p-3", complete ? "border-emerald-200/60 bg-emerald-50/20" : active ? "border-sky-300 bg-sky-50/20" : blocked ? "border-amber-200/60 bg-amber-50/20" : "border-slate-200 bg-slate-50/30")}><div className="flex items-center gap-2">{complete ? <CheckCircle2 className="h-4 w-4 text-emerald-600" /> : active ? <Loader2 className="h-4 w-4 animate-spin text-sky-600" /> : blocked ? <XCircle className="h-4 w-4 text-amber-600" /> : <span className="h-4 w-4 rounded-full border border-slate-300" />}<span className="text-xs font-medium text-slate-800">{shownLabel}</span></div><div className="mt-1 font-mono text-[10px] uppercase text-slate-500">Step {index + 1}{active ? ` · ${elapsed}` : ""}</div></div>;
    })}</div></div>
    <div className="grid gap-4 lg:grid-cols-2">
      <div className="rounded-lg border border-slate-200 bg-slate-50/30 p-3"><SectionLabel>Backend activity</SectionLabel><div className="mt-2 max-h-72 space-y-2 overflow-auto">{events.length ? events.map((event, i) => <div key={`${event.at}-${i}`} className="border-l-2 border-slate-300 pl-3"><div className="flex flex-wrap items-center gap-2"><StageBadge stage={event.stage} /><span className="font-mono text-[10px] text-slate-500">{new Date(event.at).toLocaleString()}</span></div><div className="mt-1 text-xs text-slate-700">{event.note || "Stage saved"}</div><div className="text-[10px] text-slate-400">actor: {event.actor}</div></div>) : <div className="text-xs text-slate-500">No saved events yet.</div>}</div></div>
      <div className="space-y-3">
        <div className="rounded-lg border border-slate-200 bg-slate-50/30 p-3"><SectionLabel>Frontend monitor</SectionLabel><div className="mt-2 space-y-1 text-xs text-slate-700"><div>Connection: <span className="text-emerald-600">connected</span></div><div>Article status refresh: every 5 seconds</div><div>Current saved stage: <span className="font-mono text-sky-700">{a.stage}</span></div>{a.stage === "researching" && <div>Research process: <span className="font-mono text-sky-700">{a.dossier_meta?.status === "formatting" ? "Formatting saved report" : a.dossier_meta?.status ?? "Preparing provider request"}</span></div>}{activelyRunning && <div>Current-stage elapsed time: <span className="font-mono text-sky-700">{elapsed}</span></div>}<div>Article-writing timeout: 3 minutes</div><div>Image-generation timeout: 2 minutes</div><div>Last backend update: {new Date(a.updated_at).toLocaleString()}</div></div></div>
        <div className={cn("rounded-lg border p-3", restrictions.length ? "border-amber-200/60 bg-amber-50/20" : "border-emerald-200/60 bg-emerald-50/20")}><SectionLabel>Scheduling & publishing</SectionLabel>{restrictions.length ? <ul className="mt-2 list-disc space-y-1 pl-4 text-xs text-amber-800">{restrictions.map((reason, i) => <li key={i}>{reason}</li>)}</ul> : <div className="mt-2 text-xs text-emerald-700">All publication prerequisites are ready.</div>}</div>
      </div>
    </div>
  </div>;
}

function Dossier({ a }: { a: Article }) {
  const d = a.dossier;
  if (!d) return <EmptyState title="No research yet" hint="Run Deep Research to build a source-grounded dossier." />;
  return (
    <div className="space-y-4">
      {a.validation && (
        <div className={cn("rounded-lg border p-3", a.validation.passed ? "border-emerald-200/60 bg-emerald-50/30" : "border-amber-200/60 bg-amber-50/30")}>
          <div className="flex items-center gap-2 text-sm font-medium">
            {a.validation.passed ? <BadgeCheck className="h-4 w-4 text-emerald-600" /> : <ShieldAlert className="h-4 w-4 text-amber-600" />}
            Research validation gate: {a.validation.passed ? "PASSED" : "HELD"}
            <span className="ml-auto font-mono text-[11px] text-slate-500">via {a.dossier_meta?.model}</span>
          </div>
          {!a.validation.passed && <div className="mt-1 text-xs text-amber-800/80">{a.validation.failed_reasons.join("; ")}</div>}
        </div>
      )}
      <div className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-slate-200 bg-slate-50/30 p-3">
        <div><div className="text-sm font-medium text-slate-800">Complete research document</div><div className="text-xs text-slate-500">Formatted dossier, evidence tables, sources, and original report.</div></div>
        <a href={`/api/articles/${a.id}/research.docx`} className="inline-flex h-9 items-center gap-1.5 rounded-md border border-slate-300 bg-transparent px-3 text-sm font-medium text-slate-800 transition-colors hover:bg-slate-200"><Download className="h-3.5 w-3.5" /> Download Word</a>
      </div>
      <div><SectionLabel>Executive summary</SectionLabel><p className="mt-1 text-sm text-slate-700">{d.executive_summary}</p></div>
      <div><SectionLabel>Verified facts</SectionLabel><ul className="mt-1 list-disc space-y-1 pl-5 text-sm text-slate-700">{d.verified_facts?.map((f, i) => <li key={i}>{f}</li>)}</ul></div>

      {d.timeline?.length > 0 && <div><SectionLabel>Timeline</SectionLabel><div className="mt-2 overflow-x-auto rounded-lg border border-slate-200"><table className="w-full min-w-[560px] text-left text-xs"><thead className="bg-slate-100 text-slate-700"><tr><th className="w-32 p-2.5">Date</th><th className="p-2.5">Development</th></tr></thead><tbody>{d.timeline.map((x, i) => <tr key={i} className="border-t border-slate-200"><td className="p-2.5 font-mono text-sky-700">{x.date}</td><td className="p-2.5 text-slate-700">{x.event}</td></tr>)}</tbody></table></div></div>}

      {d.key_statistics?.length > 0 && <div><SectionLabel>Key statistics</SectionLabel><div className="mt-2 overflow-x-auto rounded-lg border border-slate-200"><table className="w-full min-w-[640px] text-left text-xs"><thead className="bg-slate-100 text-slate-700"><tr><th className="p-2.5">Metric</th><th className="p-2.5">Value</th><th className="p-2.5">Period</th><th className="p-2.5">Source</th></tr></thead><tbody>{d.key_statistics.map((x, i) => <tr key={i} className="border-t border-slate-200"><td className="p-2.5 text-slate-700">{x.metric}</td><td className="p-2.5 font-medium text-slate-900">{x.value}</td><td className="p-2.5 text-slate-600">{x.period || "—"}</td><td className="p-2.5 text-slate-600">{x.source || "—"}</td></tr>)}</tbody></table></div></div>}

      <div>
        <SectionLabel>Claim → source evidence table</SectionLabel>
        <div className="mt-2 overflow-x-auto rounded-lg border border-slate-200"><table className="w-full min-w-[760px] text-left text-xs"><thead className="bg-slate-100 text-slate-700"><tr><th className="w-24 p-2.5">Status</th><th className="p-2.5">Claim</th><th className="p-2.5">Evidence note</th><th className="w-24 p-2.5">Source</th></tr></thead><tbody>{d.claim_evidence?.map((c, i) => <tr key={i} data-testid={`evidence-table-row-${i}`} className={cn("border-t border-slate-200", c.verified ? "bg-emerald-50/10" : "bg-amber-50/10")}><td className="p-2.5">{c.verified ? <span className="inline-flex items-center gap-1 text-emerald-700"><CheckCircle2 className="h-3.5 w-3.5" /> Verified</span> : <span className="inline-flex items-center gap-1 text-amber-700"><ShieldAlert className="h-3.5 w-3.5" /> Review</span>}</td><td className="p-2.5 text-slate-800">{c.claim}</td><td className="p-2.5 text-slate-600">{c.note || "—"}</td><td className="p-2.5">{c.source_url ? <a href={c.source_url} target="_blank" rel="noreferrer" className="text-sky-600 underline">Open source</a> : "—"}</td></tr>)}</tbody></table></div>
      </div>

      <div>
        <SectionLabel>Sources</SectionLabel>
        <div className="mt-2 overflow-x-auto rounded-lg border border-slate-200"><table className="w-full min-w-[760px] text-left text-xs"><thead className="bg-slate-100 text-slate-700"><tr><th className="w-10 p-2.5">#</th><th className="p-2.5">Source</th><th className="p-2.5">Publisher / date</th><th className="p-2.5">Type / reliability</th><th className="w-20 p-2.5">Link</th></tr></thead><tbody>{d.sources?.map((s, i) => <tr key={i} className="border-t border-slate-200"><td className="p-2.5 font-mono text-slate-500">{i + 1}</td><td className="p-2.5 text-slate-800">{s.title}</td><td className="p-2.5 text-slate-600">{s.publisher}{s.published ? ` · ${s.published}` : ""}</td><td className="p-2.5 text-slate-600"><span className="uppercase">{s.type}</span> · {s.reliability}</td><td className="p-2.5">{s.url ? <a href={s.url} target="_blank" rel="noreferrer" className="text-sky-600 underline">Open</a> : "—"}</td></tr>)}</tbody></table></div>
      </div>

      {a.dossier_meta?.report && <details className="rounded border border-slate-200 p-3"><summary className="cursor-pointer text-sm text-slate-700">View original raw report</summary><div className="mt-3 max-h-[520px] overflow-auto whitespace-pre-wrap rounded bg-slate-50/60 p-3 text-xs leading-relaxed text-slate-600">{a.dossier_meta.report}</div></details>}

      {d.risk_review && (
        <div className="rounded border border-slate-200 bg-slate-50/40 p-3">
          <SectionLabel>Risk & sensitivity review</SectionLabel>
          <div className="mt-1 text-sm text-slate-700">Level: <span className="uppercase">{d.risk_review.level}</span> · {d.risk_review.explanation}</div>
          {d.risk_review.flags?.length > 0 && <div className="mt-1 text-xs text-amber-700">Flags: {d.risk_review.flags.join(", ")}</div>}
        </div>
      )}
    </div>
  );
}

// Plain words for a technical stop: what happened and exactly what to do. Editorial holds keep their review panel.
function holdGuide(a: Article): { title: string; what: string } | null {
  const reason = a.held_reason ?? "";
  if (a.stage !== "held_review" && a.stage !== "failed") return null;
  if (!TECHNICAL_HOLD.test(reason) && a.stage !== "failed") return null;
  const tab = /^research\b/i.test(reason) ? "Gemini" : "ChatGPT";
  if (/work tab contains a draft/i.test(reason)) return {
    title: `Paused — the ${tab} work tab has unsent text in its message box`,
    what: `Open the ${tab} tab in the Newsroom tab group, clear the text in the message box (the app never deletes text it did not type), then press Retry.` };
  if (/work tab was closed/i.test(reason)) return {
    title: "Paused — a work tab was closed while it was working", what: "Press Retry to run this step again." };
  if (/failed \((?:auth|quota|rate_limit)\)/i.test(reason)) return {
    title: "Paused — the AI provider refused the request", what: "Check the key or quota in Settings → AI Providers, then press Retry." };
  if (/^WordPress/i.test(reason)) return {
    title: "Paused — WordPress did not accept the post", what: "Check the WordPress connection on the Health page, then press Retry." };
  if (/ChatGPT's image generation failed/i.test(reason)) return {
    title: "Paused — ChatGPT could not create the thumbnail",
    what: (/failed in \d+ ChatGPT chats/i.test(reason) ? "ChatGPT's image tool failed in three fresh chats, tried automatically. " : "ChatGPT's image tool failed. ")
      + "Press Retry to try again (up to three new chats), or choose a new thumbnail prompt." };
  if (/was sent in this work tab/i.test(reason)) return {
    title: `Paused — the ${tab} work tab shows your own conversation`, what: "Press Retry to continue in a new chat." };
  if (/existing draft is present/i.test(reason)) return {
    title: `Paused — the ${tab} message box holds text the app did not type`,
    what: `Usually an unsent message you started in ${tab} (it reappears in every new chat). Send it or clear it in ${tab}, then press Retry.` };
  if (/^research failed/i.test(reason) && a.dossier_meta?.report_mode) return {
    title: "Paused — Deep Research did not hand over its report",
    what: "If the Gemini tab shows the finished report, press “Copy report again from Gemini” below (no new research). Otherwise press Research again." };
  return { title: "Paused — a step did not finish", what: "Press Retry to run it again. If it stops again, look at the Chrome work tabs." };
}

function SeoChecklist({ a }: { a: Article }) {
  const art = a.article;
  const browserImagePending = !a.image && !!a.held_reason?.includes("featured image failed (browser)");
  if (!art) return null;
  const items = [
    { label: "Focus keyword", ok: !!art.focus_keyword, val: art.focus_keyword },
    { label: `SEO title (${art.seo_title.length}/60)`, ok: art.seo_title.length > 0 && art.seo_title.length <= 60, val: art.seo_title },
    { label: `Meta description (${art.meta_description.length}/160)`, ok: art.meta_description.length >= 50 && art.meta_description.length <= 160, val: art.meta_description },
    { label: "Slug", ok: !!art.slug, val: art.slug },
    { label: "Menu category", ok: !!art.menu_categories?.length, val: art.menu_categories?.map((m) => m.name).join(" + ") || "Chosen when publishing" },
    { label: "Topic category", ok: !!art.category, val: art.category },
    { label: `Tags (${art.tags.length})`, ok: art.tags.length > 0, val: art.tags.join(", ") },
    { label: "Open Graph", ok: !!art.og_title && !!art.og_description, val: art.og_title },
    { label: "Schema type", ok: !!art.schema_type, val: art.schema_type },
    { label: "Image alt text", ok: !!art.featured_image_alt_text, val: art.featured_image_alt_text },
  ];
  return (
    <div data-testid="seo-checklist-container" className="space-y-1.5">
      {items.map((it) => (
        <div key={it.label} className="flex items-start justify-between gap-2 rounded border border-slate-200 bg-slate-50/40 px-3 py-1.5">
          <div className="min-w-0"><div className="text-xs text-slate-700">{it.label}</div><div className="truncate text-[11px] text-slate-500">{it.val || "—"}</div></div>
          {it.ok ? <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-emerald-600" /> : <XCircle className="mt-0.5 h-4 w-4 shrink-0 text-amber-600" />}
        </div>
      ))}
    </div>
  );
}

// Owner request (28 Sep 2026): automatic research on/off. Off, the app starts no research itself; topics wait for their
// report links from the Manual Workbench, then continue with SEO, thumbnail and scheduling.
function AutoResearchSwitch() {
  const { data: stats } = useStats();
  const update = useUpdateSystem();
  const on = stats?.system?.auto_research !== false;
  const toggle = () => {
    const next = !on;
    if (!next && !window.confirm("Turn automatic research off?\n\nThe app will not research any topic by itself. Topics wait until their research report links are uploaded in the Manual Workbench; then they continue with SEO, thumbnail and scheduling.")) return;
    update.mutate({ auto_research: next }, {
      onSuccess: () => toast.success(next ? "Automatic research is on" : "Automatic research is off: topics wait for their research links"),
      onError: (e) => toast.error(e instanceof Error ? e.message : "Could not change automatic research"),
    });
  };
  return (
    <button type="button" role="switch" aria-checked={on} disabled={!stats || update.isPending} onClick={toggle} data-testid="auto-research-switch"
      className={cn("inline-flex items-center gap-2 rounded-md border px-3 py-1.5 text-sm transition-colors", on ? "border-emerald-300 bg-emerald-50/50 text-emerald-900" : "border-amber-300 bg-amber-50/60 text-amber-900")}>
      <span className={cn("relative inline-block h-5 w-9 rounded-full transition-colors", on ? "bg-emerald-500" : "bg-slate-300")}>
        <span className={cn("absolute top-0.5 h-4 w-4 rounded-full bg-white shadow transition-transform", on ? "translate-x-[18px]" : "translate-x-0.5")} />
      </span>
      Automatic research: <strong>{on ? "On" : "Off"}</strong>
    </button>
  );
}

// Which website this post belongs to and where it stands in publishing, at the top of the open post.
function ArticleContext({ a }: { a: Article }) {
  const kn = a.site_key === "kannadiga";
  const site = SITE_META[kn ? "kannadiga" : "human"];
  const live = a.wp?.status === "publish";
  return (
    <header data-site={kn ? "kannadiga" : "human"} className="site-ribbon" data-testid="article-context">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5">
        <span className="inline-flex items-center gap-2 text-[13px] font-semibold text-slate-900"><span className="site-dot" aria-hidden="true" />{site.name}</span>
        <span className="text-xs text-slate-500">{site.language}</span>
        <span className="ml-auto flex flex-wrap items-center gap-2">
          <StageBadge stage={a.stage} heldReason={a.held_reason} />
          {a.stage === "scheduled" && a.scheduled_time && <span className="font-mono text-[11px] text-navy-700">{fmtTime(a.scheduled_time)}</span>}
          {live && a.wp?.public_url && <a href={a.wp.public_url} target="_blank" rel="noreferrer" className="text-xs font-medium text-navy-700 underline decoration-amber-400 underline-offset-4 hover:decoration-amber-600">View live post</a>}
        </span>
      </div>
      <h2 lang={kn ? "kn" : "en"} className={cn("mt-2 font-heading text-lg font-semibold leading-snug text-slate-950 sm:text-xl", kn && "font-kannada")}>{a.article?.headline ?? (a.topic_snapshot.topic as string)}</h2>
    </header>
  );
}

function ArticleView({ a, onAction }: { a: Article; onAction: (path: string, label: string, body?: unknown) => void }) {
  const { data: stats } = useStats();
  const aiBlocked = !stats?.system.manual_ai_enabled || stats.system.global_paused || stats.system.killswitch;
  const publishingBlocked = !stats || stats.system.dry_run || stats.system.repair_lock;
  const kn = a.site_key === "kannadiga";
  const art = a.article;
  const imgFileRef = useRef<HTMLInputElement>(null);
  const [imgUrl, setImgUrl] = useState("");
  const [imgUploading, setImgUploading] = useState(false);

  const doSetImage = async (body: { url?: string; data_uri?: string; source?: string }) => {
    setImgUploading(true);
    try {
      await apiPost(`/articles/${a.id}/set-image`, body);
      toast.success("Image saved — article is ready for publishing");
      setImgUrl("");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Could not set image. Check the URL or file and try again.");
    } finally {
      setImgUploading(false);
    }
  };

  const doSetImageFile = (file: File) => {
    const reader = new FileReader();
    reader.onload = () => doSetImage({ data_uri: reader.result as string, source: "upload" });
    reader.onerror = () => toast.error("Could not read image file");
    reader.readAsDataURL(file);
  };

  const browserImagePending = !a.image && !!a.held_reason?.includes("featured image failed (browser)");
  const guide = holdGuide(a);
  const live = LIVE_STAGES[a.stage];
  // Validated stages are completed checkpoints, not active jobs. Treating them
  // as running left the Image button disabled forever after an interrupted worker.
  const pipelineRunning = ["researching", "writing_article", "generating_image"].includes(a.stage);
  const publishedLocked = ["wordpress_draft", "scheduled", "published", "verified"].includes(a.stage) || !!a.wp?.post_id;
  const qc = useQueryClient();
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState({ headline: "", content_html: "", seo_title: "", meta_description: "" });
  const [busy, setBusy] = useState<string | null>(null);
  const [when, setWhen] = useState("");
  const [headlines, setHeadlines] = useState<string[]>([]);
  useEffect(() => { setHeadlines(art?.thumbnail_headlines ?? Array(kn ? 3 : 2).fill("")); }, [art?.thumbnail_headlines, kn]);

  useEffect(() => {
    if (art) setDraft({ headline: art.headline, content_html: art.content_html, seo_title: art.seo_title, meta_description: art.meta_description });
  }, [art]);

  const run = async (fn: () => Promise<unknown>, key: string) => {
    setBusy(key);
    try { await fn(); } catch (e) { toast.error(e instanceof Error ? e.message : "Action failed"); } finally { setBusy(null); }
  };

  const paidAction = (action: string, label: string, key: string) => run(async () => {
    const result = await apiPost<Article>(`/articles/${a.id}/${action}`, {});
    for (const query of ["article", "articles", "stats", "audit"]) qc.invalidateQueries({ queryKey: query === "article" ? [query, a.id] : [query] });
    if (result.held_reason) toast.error(result.held_reason); else toast.success(label);
  }, key);

  const saveHeadlines = () => run(async () => {
    await apiPatch(`/articles/${a.id}/thumbnail-headlines`, { headlines });
    qc.invalidateQueries({ queryKey: ["article", a.id] });
    qc.invalidateQueries({ queryKey: ["articles"] });
    toast.success("Thumbnail headlines saved; the post title now matches them");
  }, "headlines");

  const saveEdit = () => run(async () => {
    await apiPatch(`/articles/${a.id}`, draft);
    qc.invalidateQueries({ queryKey: ["article", a.id] });
    qc.invalidateQueries({ queryKey: ["articles"] });
    setEditing(false); toast.success("Article updated");
  }, "save");

  const schedule = () => {
    if (!when) { toast.error("Pick a time"); return; }
    onAction(`/articles/${a.id}/schedule`, "Scheduled", { scheduled_time: new Date(when).toISOString() });
  };

  return (
    <div className="space-y-4">
      <ArticleContext a={a} />
      {/* action bar */}
      <div className="flex flex-wrap items-center gap-2 rounded-xl border border-slate-200 bg-slate-50/80 p-2">
        <Button size="sm" variant="outline" disabled={!!busy || aiBlocked || !!a.dossier || pipelineRunning} onClick={() => paidAction("research", "Full workflow started in the background", "research")} data-testid={`article-research-button-${a.id}`} className="gap-1.5">
          {busy === "research" || pipelineRunning ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Sparkles className="h-3.5 w-3.5" />} {pipelineRunning ? "Workflow running" : "Start Workflow"}
        </Button>
        <Button size="sm" variant="outline" disabled={!a.validation?.passed || !!busy || aiBlocked || pipelineRunning || publishedLocked} onClick={() => paidAction("generate", "Article generation started", "gen")} data-testid={`article-generate-button-${a.id}`} className="gap-1.5" title={publishedLocked ? "Published and scheduled articles are locked" : undefined}>
          {busy === "gen" ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <FileText className="h-3.5 w-3.5" />} Generate
        </Button>
        <Button size="sm" variant="outline" disabled={!a.article || !!busy || aiBlocked || pipelineRunning || publishedLocked} onClick={() => paidAction("image", "Image generation started", "img")} data-testid={`regenerate-image-button-${a.id}`} className="gap-1.5" title={publishedLocked ? "Published and scheduled articles are locked" : undefined}>
          {busy === "img" ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <ImageIcon className="h-3.5 w-3.5" />} {a.image ? "Regenerate Image" : "Image"}
        </Button>
        <div className="mx-1 h-6 w-px bg-slate-300" />
        <Button size="sm" disabled={!a.image || !!a.approval || busy === "approve"} onClick={() => onAction(`/articles/${a.id}/approve`, "Approved locally")} data-testid={`article-approve-button-${a.id}`} className="gap-1.5 bg-none bg-emerald-600 text-white hover:bg-emerald-700">
          <ThumbsUp className="h-3.5 w-3.5" /> {a.approval ? "Approved locally" : "Approve locally"}
        </Button>
        <Button size="sm" disabled={!a.image || publishingBlocked || !!busy || publishedLocked} onClick={() => onAction(`/articles/${a.id}/publish`, "Publish attempt")} data-testid={`article-publish-now-button-${a.id}`} className="gap-1.5" title={publishedLocked ? "This article is already published or scheduled" : undefined}>
          <Rocket className="h-3.5 w-3.5" /> Publish Now
        </Button>
        <Button size="sm" variant="ghost" disabled={publishedLocked || a.stage === "rejected"} onClick={() => onAction(`/articles/${a.id}/reject`, "Rejected", { reason: "Rejected by editor" })} data-testid={`article-reject-button-${a.id}`} className="gap-1.5 text-slate-600">
          <ThumbsDown className="h-3.5 w-3.5" /> Reject
        </Button>
        {pipelineRunning && (
          <Button size="sm" variant="destructive" disabled={busy === "stop"} onClick={() => paidAction("stop", "Current article action stopped", "stop")} data-testid={`article-stop-button-${a.id}`} className="gap-1.5">
            <Square className="h-3.5 w-3.5" /> Stop
          </Button>
        )}
        {(a.stage === "held_review" || a.stage === "failed") && (
          <Button size="sm" variant={guide ? "default" : "outline"} disabled={!!busy || aiBlocked} onClick={() => paidAction("retry", "Workflow resumed in the background", "research")} data-testid={`article-retry-button-${a.id}`} className="gap-1.5">
            <RefreshCw className="h-3.5 w-3.5" /> Retry
          </Button>
        )}
      </div>

      <p className="text-xs text-slate-600">Start Workflow runs Deep Research (the article), SEO assets and the thumbnail through the generation route chosen on the Command Center — Chrome Bridge (your subscriptions) or API keys (paid credits). {publishingBlocked ? "Publishing is currently restricted by the runtime controls." : "Auto mode can schedule and publish articles that pass the automatic gates."}</p>
      {live && <div role="status" className={cn("rounded-lg border p-3", a.stage === "image_ready" ? "border-emerald-200/60 bg-emerald-50/20" : "border-sky-200/60 bg-sky-50/20")}>
        <div className="flex items-center gap-2 text-sm font-medium text-slate-900">{pipelineRunning ? <Loader2 className="h-4 w-4 animate-spin text-sky-600" /> : <CheckCircle2 className="h-4 w-4 text-emerald-600" />}{live.label}<span className="ml-auto font-mono text-[11px] text-slate-600">Step {live.step} of 4</span></div>
        <div className="mt-1 text-xs text-slate-600">{live.detail}</div>
        <div className="mt-2 grid grid-cols-4 gap-1">{[1, 2, 3, 4].map(step => <div key={step} className={cn("h-1.5 rounded-full", step <= live.step ? (a.stage === "image_ready" ? "bg-emerald-500" : "bg-sky-500") : "bg-slate-200", pipelineRunning && step === live.step && "progress-active")} />)}</div>
      </div>}
      {!a.article && !publishedLocked && a.stage !== "rejected" && <ResearchPanel articleId={a.id} />}
      {art && <div className="space-y-2 rounded-lg border border-slate-200 p-3">
        <SectionLabel>Thumbnail headlines — top only, second line largest</SectionLabel>
        {headlines.map((line, i) => <Input key={i} aria-label={`Thumbnail headline ${i + 1}`} value={line} onChange={(e) => setHeadlines(headlines.map((v, j) => j === i ? e.target.value : v))} placeholder={kn ? "ಕನ್ನಡ ಶೀರ್ಷಿಕೆ" : "Short English headline"} />)}
        <p className="text-xs text-slate-500">Read top to bottom, these lines are also the post title.</p>
        <Button size="sm" variant="outline" disabled={!!busy || publishedLocked} onClick={saveHeadlines}>Save thumbnail headlines</Button>
      </div>}
      {a.stage === "held_review" && !a.dossier && !!a.dossier_meta?.report_mode && /^research failed/i.test(a.held_reason ?? "") && !publishedLocked && <div className="flex flex-wrap items-center gap-2 rounded-lg border border-amber-300 p-3" data-testid="research-recovery">
        <Button disabled={!!busy} onClick={() => onAction(`/browser/articles/${a.id}/recopy`, "Copying the finished report again from Gemini")}>Copy report again from Gemini</Button>
        <Button variant="outline" disabled={!!busy} onClick={() => onAction(`/browser/articles/${a.id}/research-again`, "Deep Research will run again for this article")}>Research again</Button>
        <span className="basis-full text-xs text-slate-600">Copy again reopens the report's Gemini conversation and takes the finished report (no new research). Research again runs a new Deep Research.</span>
      </div>}
      {a.stage === "held_review" && !!a.dossier && !!a.validation && !a.validation.passed && !a.article && !publishedLocked && <div className="space-y-2 rounded-lg border border-amber-300 p-3">
        <p className="text-sm text-amber-800">Waiting for you, the editor. Review the Research and Gates tabs, then approve the saved research to continue.</p>
        <Button disabled={!!busy || aiBlocked || pipelineRunning} onClick={() => paidAction("research/go-ahead", "Research approved — continuing article and image generation", "research-approval")}>Go ahead — approve research</Button>
        <p className="text-xs text-slate-600">Records your acceptance of the research warnings and starts article writing and image generation using your configured AI. Article, Kannada, image and publishing checks still apply.</p>
        {!!a.dossier?.report_mode && <div className="flex flex-wrap items-center gap-2 border-t border-amber-200 pt-2">
          <Button variant="outline" disabled={!!busy} onClick={() => onAction(`/browser/articles/${a.id}/recopy`, "Copying the finished report again from Gemini")}>Copy report again from Gemini</Button>
          <Button variant="outline" disabled={!!busy} onClick={() => onAction(`/browser/articles/${a.id}/research-again`, "Deep Research will run again for this article")}>Research again</Button>
          <span className="basis-full text-xs text-slate-600">Copy again reopens the report's Gemini conversation (no new research). Research again runs a new Deep Research in its turn.</span>
        </div>}
        {aiBlocked && <p className="text-xs text-amber-800">Resume the app and enable AI actions to continue.</p>}
      </div>}
      {browserImagePending && (
        <div className="space-y-3 rounded-lg border border-sky-200 bg-sky-50/20 p-3">
          <div className="text-sm text-sky-800">
            <p className="font-medium">Browser image job needs attention</p>
            <p className="mt-0.5 text-slate-600">
              If you already generated the image in ChatGPT, use one of the options below — no need to retry from scratch.
            </p>
          </div>

          {/* Option 1: paste URL */}
          <div className="space-y-1.5">
            <p className="text-[11px] font-mono uppercase text-slate-500">
              Option 1 — paste image URL (right-click image in ChatGPT → Copy image address)
            </p>
            <div className="flex gap-2">
              <Input
                value={imgUrl}
                onChange={(e) => setImgUrl(e.target.value)}
                placeholder="https://..."
                className="bg-white text-sm"
                disabled={imgUploading}
                onKeyDown={(e) => { if (e.key === "Enter" && imgUrl.trim()) doSetImage({ url: imgUrl.trim(), source: "url" }); }}
              />
              <Button
                size="sm"
                disabled={!imgUrl.trim() || imgUploading}
                onClick={() => doSetImage({ url: imgUrl.trim(), source: "url" })}
                className="gap-1.5 shrink-0"
              >
                {imgUploading ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <ImageIcon className="h-3.5 w-3.5" />}
                Use this image
              </Button>
            </div>
          </div>

          {/* Option 2: upload file */}
          <div className="space-y-1.5">
            <p className="text-[11px] font-mono uppercase text-slate-500">
              Option 2 — upload image from computer (save from ChatGPT → right-click → Save image as)
            </p>
            <div className="flex gap-2">
              <input
                ref={imgFileRef}
                type="file"
                accept="image/*"
                className="hidden"
                onChange={(e) => { const f = e.target.files?.[0]; if (f) doSetImageFile(f); e.target.value = ""; }}
              />
              <Button
                size="sm"
                variant="outline"
                disabled={imgUploading}
                onClick={() => imgFileRef.current?.click()}
                className="gap-1.5"
              >
                {imgUploading ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Upload className="h-3.5 w-3.5" />}
                Choose image file…
              </Button>
            </div>
          </div>

          <p className="border-t border-sky-100 pt-2 text-xs text-slate-500">
            Prefer to re-run from scratch? Press <strong>Retry</strong> above, or{" "}
            <a className="underline" href="/wizard">open the Browser Extension wizard</a>.
          </p>
        </div>
      )}
      {a.held_reason && (
        <div className="flex items-start gap-2 rounded-lg border border-amber-200/60 bg-amber-50/30 p-3 text-sm text-amber-800">
          <ShieldAlert className="mt-0.5 h-4 w-4 shrink-0" />{guide
            ? <div><div className="font-medium">{guide.title}</div><div className="mt-1">{guide.what}</div><div className="mt-1 text-xs text-amber-700/80">Details: {a.held_reason}</div></div>
            : <div><span className="font-medium">{browserImagePending ? "Browser image needs attention — " : "Held for human review — "}</span>{a.held_reason}</div>}
        </div>
      )}

      <Tabs defaultValue="process">
        <TabsList>
          <TabsTrigger value="process" data-testid={`tab-process-${a.id}`}>Process</TabsTrigger>
          <TabsTrigger value="preview" data-testid={`tab-preview-${a.id}`}>Preview</TabsTrigger>
          <TabsTrigger value="dossier" data-testid={`tab-dossier-${a.id}`}>Research</TabsTrigger>
          <TabsTrigger value="seo" data-testid={`tab-seo-${a.id}`}>SEO</TabsTrigger>
          <TabsTrigger value="gates" data-testid={`tab-gates-${a.id}`}>Gates</TabsTrigger>
        </TabsList>

        <TabsContent value="process" className="mt-4"><ProcessMonitor a={a} system={stats?.system} /></TabsContent>

        <TabsContent value="preview" className="mt-4 space-y-4">
          {!art ? <EmptyState title="No article yet" hint="Run Research then Generate." /> : editing ? (
            <div className="space-y-3">
              <Input value={draft.headline} onChange={(e) => setDraft({ ...draft, headline: e.target.value })} className="h-11 bg-white font-heading text-base font-medium" />
              <Input value={draft.seo_title} onChange={(e) => setDraft({ ...draft, seo_title: e.target.value })} placeholder="SEO title" className="bg-slate-50/60" />
              <Input value={draft.meta_description} onChange={(e) => setDraft({ ...draft, meta_description: e.target.value })} placeholder="Meta description" className="bg-slate-50/60" />
              <Textarea value={draft.content_html} onChange={(e) => setDraft({ ...draft, content_html: e.target.value })} className="writing-area min-h-[420px] font-mono text-[13px]" />
              <div className="flex gap-2">
                <Button size="sm" onClick={saveEdit} disabled={busy === "save"} data-testid={`article-save-edit-${a.id}`} className="gap-1.5">{busy === "save" ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Save className="h-3.5 w-3.5" />} Save</Button>
                <Button size="sm" variant="ghost" onClick={() => setEditing(false)}>Cancel</Button>
              </div>
            </div>
          ) : (
            <div className="reading-column">
              <div className="mb-3 flex items-center justify-between">
                <SectionLabel>WordPress preview {a.site_key === "kannadiga" ? "· ಕನ್ನಡ" : ""}</SectionLabel>
                <Button size="xs" variant="outline" disabled={publishedLocked} onClick={() => setEditing(true)} data-testid={`article-edit-button-${a.id}`}>Edit</Button>
              </div>
              {a.image?.data_uri && (
                <img data-testid="featured-image-preview" src={a.image.data_uri} alt={a.image.alt_text} className="mb-4 aspect-video w-full rounded-lg border border-slate-200 object-cover" />
              )}
              <h1 lang={kn ? "kn" : "en"} className={cn("article-headline", kn && "font-kannada")}>{art.headline}</h1>
              <p lang={kn ? "kn" : "en"} className={cn("article-dek", kn && "font-kannada")}>{art.dek}</p>
              <div lang={kn ? "kn" : "en"} className={cn("article-body mt-6", kn && "font-kannada")} dangerouslySetInnerHTML={{ __html: DOMPurify.sanitize(art.content_html) }} />
              {art.key_takeaways?.length > 0 && (
                <div className="mt-4 rounded-lg border border-slate-200 bg-slate-100/40 p-3">
                  <SectionLabel>Key takeaways</SectionLabel>
                  <ul className={cn("mt-2 list-disc space-y-1 pl-5 text-sm text-slate-700", kn && "font-kannada")}>{art.key_takeaways.map((k, i) => <li key={i}>{k}</li>)}</ul>
                </div>
              )}
            </div>
          )}
        </TabsContent>

        <TabsContent value="dossier" className="mt-4"><Dossier a={a} /></TabsContent>

        <TabsContent value="seo" className="mt-4 space-y-4">
          <SeoChecklist a={a} />
          {a.image && (
            <div className="rounded-lg border border-slate-200 bg-slate-100/40 p-3">
              <SectionLabel>Featured image</SectionLabel>
              <div className="mt-2 flex items-center gap-3">
                {a.image.data_uri && <img src={a.image.data_uri} alt={a.image.alt_text} className="h-20 w-36 rounded border border-slate-200 object-cover" />}
                <div className="text-xs text-slate-600">
                  <div className="font-mono">{a.image.filename}</div>
                  <div>alt: {a.image.alt_text}</div>
                  <div>Editorial thumbnail · {a.image.aspect_ratio}</div>
                </div>
              </div>
            </div>
          )}
        </TabsContent>

        <TabsContent value="gates" className="mt-4 space-y-4">
          {a.validation && <GateList checks={a.validation.checks} title="Research validation gate" />}
          {a.quality_gate && <GateList checks={a.quality_gate.checks} title="Article quality gate" />}
          {a.wp && (
            <div className="rounded-lg border border-slate-200 bg-slate-100/40 p-3">
              <SectionLabel>WordPress result {a.wp.simulated && "· SIMULATED"}</SectionLabel>
              <div className="mt-2 space-y-1 text-xs text-slate-600">
                <div>Status: <span className="text-slate-800">{a.wp.status}</span> · Post #{a.wp.post_id}</div>
                <div>Public: <a href={a.wp.public_url} target="_blank" rel="noreferrer" className="text-sky-600 underline">{a.wp.public_url}</a></div>
                <div>SEO plugin: {a.wp.seo_plugin} · persisted: {String(a.wp.seo_persisted)}</div>
              </div>
            </div>
          )}
          <div className="rounded-lg border border-slate-200 bg-slate-100/40 p-3">
            <SectionLabel>Schedule for later</SectionLabel>
            <div className="mt-2 flex items-center gap-2">
              <Input type="datetime-local" value={when} onChange={(e) => setWhen(e.target.value)} className="h-9 w-56 bg-slate-50/60 text-xs" data-testid={`article-schedule-input-${a.id}`} />
              <Button size="sm" disabled={!a.image || publishingBlocked || !!busy || publishedLocked} onClick={schedule} data-testid={`article-schedule-button-${a.id}`} className="gap-1.5"><Send className="h-3.5 w-3.5" /> Schedule</Button>
            </div>
          </div>
        </TabsContent>
      </Tabs>
    </div>
  );
}

function AutoResearchOffNotice() {
  const { data: stats } = useStats();
  if (stats?.system?.auto_research !== false) return null;
  return (
    <div className="rounded-lg border border-amber-200/70 bg-amber-50/40 px-4 py-3 text-sm text-amber-900" data-testid="auto-research-off">
      <strong>Automatic research is off.</strong> The app researches no topic by itself: topics wait until their research report links are uploaded in the <a className="underline underline-offset-4" href="/manual">Manual Workbench</a>, then continue with SEO, thumbnail and scheduling as usual.
    </div>
  );
}

export default function Articles() {
  const [params, setParams] = useSearchParams();
  const site = params.get("site") ?? "all";
  const openId = params.get("open");
  const detailPanel = useRef<HTMLDivElement>(null);
  useEffect(() => { detailPanel.current?.scrollTo({ top: 0 }); }, [openId]);
  const { data: articles, isLoading } = useArticles(site === "all" ? undefined : site);
  const { data: active } = useArticle(openId);
  const action = useArticleAction();
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [bulkRunning, setBulkRunning] = useState(false);
  const [bulkResults, setBulkResults] = useState<{ id: string; title: string; message: string }[]>([]);

  const [statusFilters, setStatusFilters] = useState<Set<string>>(new Set());
  const list = useMemo(() => articles ?? [], [articles]);
  const statusOptions = useMemo(() => {
    const counts = new Map<string, number>();
    for (const item of list) {
      const label = workflowStageLabel(item.stage, item.held_reason);
      counts.set(label, (counts.get(label) ?? 0) + 1);
    }
    return [...counts.entries()].sort(([a], [b]) => a.localeCompare(b));
  }, [list]);
  const visibleList = list.filter((a) => !statusFilters.size || statusFilters.has(workflowStageLabel(a.stage, a.held_reason)));
  const toggleStatus = (label: string) => {
    setStatusFilters(previous => { const next = new Set(previous); if (next.has(label)) next.delete(label); else next.add(label); return next; });
    setSelectedIds(new Set());
  };
  const eligible = visibleList.filter((a) => !a.wp?.post_id
    && ["selected", "held_review", "failed", "research_validated", "article_generated", "article_validated"].includes(a.stage)
    && (!a.dossier || !a.validation?.passed || !a.article || !a.image));
  const selected = eligible.filter((a) => selectedIds.has(a.id));
  const toggleSelection = (id: string) => setSelectedIds((previous) => {
    const next = new Set(previous);
    if (next.has(id)) next.delete(id); else next.add(id);
    return next;
  });
  const researchApprovable = (a: Article) => a.stage === "held_review" && !!a.dossier && !!a.validation && !a.validation.passed && !a.article && !a.wp?.post_id;
  const approvalCount = selected.filter(researchApprovable).length;
  const retrySelected = async (approveResearch = false) => {
    const batch = [...selected];
    setBulkRunning(true);
    setBulkResults([]);
    try {
      for (const article of batch) {
        let message: string;
        try {
          if (approveResearch && !researchApprovable(article)) {
            setBulkResults((previous) => [...previous, { id: article.id, title: article.article?.headline ?? article.topic_snapshot.topic, message: "Skipped — this item is not waiting for research approval. Use Start / Retry for missing research or provider errors." }]);
            continue;
          }
          const result = await action.mutateAsync({ path: `/articles/${article.id}/${approveResearch ? "research/go-ahead" : "retry"}` });
          message = result.stage === "held_review" ? `Needs review: ${result.held_reason ?? "Check the article"}` : "Workflow started — follow its live status below";
          setSelectedIds((previous) => { const next = new Set(previous); next.delete(article.id); return next; });
        } catch (error) {
          message = (error as Error & { body?: { detail?: string } }).body?.detail ?? "Could not start. Try this item again.";
        }
        setBulkResults((previous) => [...previous, { id: article.id, title: article.article?.headline ?? article.topic_snapshot.topic, message }]);
      }
    } finally {
      setBulkRunning(false);
    }
  };
  useEffect(() => {
    if (!openId && list.length > 0) setParams((p) => { p.set("open", list[0].id); return p; }, { replace: true });
  }, [openId, list, setParams]);

  const runAction = (path: string, label: string, body?: unknown) =>
    action.mutate({ path, body }, {
      onSuccess: (art) => {
        if (art.stage === "held_review") toast.warning(`Held for review: ${art.held_reason ?? ""}`);
        else toast.success(label);
      },
      onError: (e) => toast.error((e as Error & { body?: { detail?: string } }).body?.detail ?? "Action failed"),
    });

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <SectionLabel>Editorial Workbench</SectionLabel>
          <h1 className="page-title">Research · Write · Publish</h1>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <AutoResearchSwitch />
          <SiteSwitch value={site} onChange={(key) => setParams((p) => { p.set("site", key); return p; })} testidPrefix="articles-filter" allLabel="All" />
        </div>
      </div>

      <AutoResearchOffNotice />

      <Card className="space-y-3 border-slate-200 surface p-4" data-testid="bulk-workflow-actions">
        <div className="flex flex-wrap items-center gap-2">
          <span className="mr-2 text-sm text-slate-800">{selected.length} selected</span>
          <Button size="sm" variant="outline" disabled={bulkRunning || !eligible.length} onClick={() => setSelectedIds(new Set(eligible.map((a) => a.id)))}>Select all matching eligible</Button>
          <Button size="sm" variant="outline" disabled={bulkRunning || !eligible.some((a) => a.stage === "held_review")} onClick={() => setSelectedIds(new Set(eligible.filter((a) => a.stage === "held_review").map((a) => a.id)))}>Select held items</Button>
          <Button size="sm" variant="outline" disabled={bulkRunning || !eligible.some(researchApprovable)} onClick={() => setSelectedIds(new Set(eligible.filter(researchApprovable).map((a) => a.id)))}>Select research awaiting approval</Button>
          <Button size="sm" className="bg-none bg-emerald-600 text-white hover:bg-emerald-700" disabled={bulkRunning || !approvalCount} onClick={() => retrySelected(true)}>Go ahead — approve selected research ({approvalCount})</Button>
          <Button size="sm" variant="ghost" disabled={bulkRunning || !selectedIds.size} onClick={() => setSelectedIds(new Set())}>Clear selection</Button>
          <Button size="sm" disabled={bulkRunning || !selected.length} onClick={() => retrySelected()} className="gap-2">
            {bulkRunning ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
            {bulkRunning ? "Processing selected items…" : "Start / Retry selected"}
          </Button>
        </div>
        <p className="text-xs text-slate-600">Selection applies to the current site and status filters. Resume saved research and continue through SEO and thumbnails on the chosen generation route. Published, scheduled and running items cannot be selected.</p>
        <p className="text-xs text-slate-600">Go ahead records your approval of the selected research warnings and continues writing and images. Other holds are skipped and reported below; later quality and publishing checks still apply.</p>
        {bulkResults.length > 0 && <div aria-live="polite" className="max-h-40 space-y-2 overflow-auto text-xs text-slate-700">{bulkResults.map((result) => <div key={result.id}><span className="font-medium">{result.title}</span><div className="text-slate-600">{result.message}</div></div>)}</div>}
      </Card>

      <div className="grid grid-cols-1 items-start gap-6 lg:grid-cols-12">
        <div className="min-w-0 lg:sticky lg:top-20 lg:col-span-4 xl:col-span-3">
          <Card className="max-h-[52vh] overflow-y-auto overscroll-contain border-slate-200 surface p-2 lg:max-h-[calc(100dvh-6rem)]" role="region" aria-label="Research topic list" tabIndex={0}>
            <div className="sticky -top-2 z-10 space-y-2 border-b border-slate-200 surface px-1 pb-3 pt-2">
              <details>
                <summary className="cursor-pointer rounded border border-slate-300 px-3 py-2 text-sm text-slate-800">Filter by status · {statusFilters.size ? `${statusFilters.size} selected` : "All statuses"}</summary>
                <div className="mt-2 max-h-56 space-y-2 overflow-y-auto rounded border border-slate-300 p-3">
                  {statusOptions.map(([label, count]) => <label key={label} className="flex items-center gap-2 text-xs text-slate-800"><input type="checkbox" disabled={bulkRunning} checked={statusFilters.has(label)} onChange={() => toggleStatus(label)} className="accent-sky-500" /><span>{label}</span><span className="ml-auto text-slate-600">{count}</span></label>)}
                  <Button size="sm" variant="ghost" disabled={bulkRunning || !statusFilters.size} onClick={() => { setStatusFilters(new Set()); setSelectedIds(new Set()); }}>Clear status filter</Button>
                </div>
              </details>
              <p className="text-xs text-slate-600" aria-live="polite">{visibleList.length} of {list.length} posts shown · Choose one or multiple statuses</p>
            </div>
            {isLoading ? (
              <div className="flex justify-center py-10"><Loader2 className="h-5 w-5 animate-spin text-slate-500" /></div>
            ) : visibleList.length === 0 ? (
              <div className="p-3"><EmptyState title="No matching articles" hint="Change the status filter or select a topic from Topic Intelligence." /></div>
            ) : (
              <div className="space-y-1.5">
                {visibleList.map((a) => (
                  <div key={a.id} className="flex items-start gap-2">
                    <input type="checkbox" className="mt-4 h-4 w-4 shrink-0 accent-sky-500"
                      aria-label={`Select ${a.article?.headline ?? a.topic_snapshot.topic}`}
                      checked={selectedIds.has(a.id) && eligible.some((item) => item.id === a.id)}
                      disabled={bulkRunning || !eligible.some((item) => item.id === a.id)}
                      onChange={() => toggleSelection(a.id)} />
                  <button
                    key={a.id} data-testid={`article-list-item-${a.id}`}
                    onClick={() => {
                      setParams((p) => { p.set("open", a.id); return p; });
                      // Stacked layout (phones): bring the opened post into view.
                      if (window.innerWidth < 1024) requestAnimationFrame(() => detailPanel.current?.scrollIntoView({
                        block: "start", behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth" }));
                    }}
                    aria-current={openId === a.id ? "true" : undefined}
                    className={cn("w-full rounded-xl border p-3 text-left transition-all duration-200",
                      openId === a.id ? "border-navy-300 bg-white shadow-[inset_3px_0_0_var(--color-amber-500),0_8px_18px_-12px_rgb(1_27_75/0.4)]" : "border-slate-200 bg-white/50 hover:border-amber-300 hover:bg-amber-50/40")}
                  >
                    <div className="mb-1.5 flex flex-wrap items-center gap-1.5"><SiteBadge siteKey={a.site_key} small /><StageBadge stage={a.stage} heldReason={a.held_reason} />{a.queue === "current"
                      ? <span className="rounded-full border border-emerald-300 bg-emerald-50 px-2 py-0.5 text-[10px] font-medium text-emerald-700" title="The article the app is working on now" data-testid="current-chip">Now working</span>
                      : a.queue === "next"
                      ? <span className="rounded-full border border-sky-300 bg-sky-50 px-2 py-0.5 text-[10px] font-medium text-sky-700" title="Next in line: its research runs while the current article is on its thumbnail" data-testid="next-chip">{a.stage === "researching" ? "Next · researching ahead" : "Next in line"}</span>
                      : (a.queue === "queued" || a.turn_wait) && <span className="rounded-full border border-slate-300 px-2 py-0.5 text-[10px] font-medium text-slate-600" title="Waiting in line: it starts once the article before it is scheduled for publishing" data-testid="queued-chip">{a.queue_position ? `Queued #${a.queue_position}` : "Queued"}</span>}</div>
                    <div className={cn("line-clamp-2 text-sm text-slate-800", a.site_key === "kannadiga" && "font-kannada")}>{a.article?.headline ?? (a.topic_snapshot.topic as string)}</div>
                    <div className="mt-1.5 flex flex-wrap items-center gap-2"><RiskBadge flags={a.review_flags} /><span className="font-mono text-[10px] text-slate-500">{fmtTime(a.updated_at)}</span></div>
                  </button>
                  </div>
                ))}
              </div>
            )}
          </Card>
        </div>

        <div ref={detailPanel} role="region" aria-label="Selected research dashboard" tabIndex={0} className="min-w-0 scroll-mt-20 lg:sticky lg:top-20 lg:col-span-8 lg:max-h-[calc(100dvh-6rem)] lg:overflow-y-auto lg:overscroll-contain xl:col-span-9">
          <Card className="border-slate-200 surface p-5" data-testid="article-editor-workbench">
            {active ? <ArticleView a={active} onAction={runAction} /> : <EmptyState title="Select an article" hint="Pick an item from the queue, or select a topic to begin." />}
          </Card>
        </div>
      </div>
    </div>
  );
}
