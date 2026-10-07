import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { CheckSquare, ChevronDown, DatabaseZap, Download, Filter, Grid3x3, LayoutGrid, Loader2, PlayCircle, ShieldX, Sparkles, Square, Target, X } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { apiPost } from "@/lib/api";
import { useArticles, useDiscover, useImportPosts, usePublished, useTopics, useSelectTopic, useStats } from "@/lib/hooks";
import { EmptyState, RiskBadge, SectionLabel, SiteBadge, SiteSwitch, StageBadge } from "@/lib/ui";
import type { Article, Topic } from "@/lib/types";
import { cn } from "@/lib/utils";

const STATUS_TABS = [
  { key: "pending", label: "Pending · not in Workbench" },
  { key: "workbench", label: "In Workbench" },
  { key: "scheduled", label: "Scheduled" },
  { key: "published", label: "Published" },
  { key: "rejected", label: "Rejected" },
  { key: "all", label: "All" },
] as const;
type StatusTab = (typeof STATUS_TABS)[number]["key"];

const DUPES_OPEN = "newsroom-duplicate-guard-open";
function readDupesOpen() {
  try { return localStorage.getItem(DUPES_OPEN) === "1"; } catch { return false; }
}

function topicGroup(t: Topic, article?: Article): Exclude<StatusTab, "all"> {
  if (t.status === "rejected" || article?.stage === "rejected") return "rejected";
  if (article) {
    if (article.stage === "scheduled") return "scheduled";
    if (["published", "verified"].includes(article.stage)) return "published";
    return "workbench";
  }
  return t.status === "used" ? "workbench" : "pending";
}

function ScoreRing({ score }: { score: number }) {
  const color = score >= 70 ? "text-emerald-600" : score >= 55 ? "text-sky-600" : "text-amber-600";
  return (
    <div className="flex flex-col items-center">
      <div className={cn("font-mono text-2xl font-bold tabular-nums", color)}>{score}</div>
      <div className="text-[9px] font-mono uppercase tracking-wider text-slate-400">/ 100</div>
    </div>
  );
}

function Bar({ label, value, max }: { label: string; value: number; max: number }) {
  return (
    <div className="flex items-center gap-2">
      <span className="w-16 shrink-0 font-mono text-[10px] uppercase text-slate-500">{label}</span>
      <div className="h-1.5 flex-1 overflow-hidden rounded bg-slate-200">
        <div className="h-full rounded bg-sky-500" style={{ width: `${(value / max) * 100}%` }} />
      </div>
      <span className="w-8 text-right font-mono text-[10px] text-slate-600">{value}/{max}</span>
    </div>
  );
}

function TopicCard({
  t, article, isSelected, onToggleSelect,
}: {
  t: Topic; article?: Article; isSelected?: boolean; onToggleSelect?: () => void;
}) {
  const nav = useNavigate();
  const select = useSelectTopic();
  const [rejected, setRejected] = useState(false);
  const [rejecting, setRejecting] = useState(false);
  const kn = t.site_key === "kannadiga";
  const b = t.score_breakdown;

  const doSelect = () =>
    select.mutate(t.id, {
      onSuccess: (art) => toast.success("Added to Editorial Workbench", {
        description: t.topic.slice(0, 90),
        action: { label: "Open", onClick: () => nav(`/articles?open=${art.id}&site=${t.site_key}`) },
      }),
      onError: () => toast.error("Could not select topic"),
    });

  const doReject = async () => {
    if (rejecting || rejected || t.status === "rejected" || article?.stage === "rejected") return;
    setRejecting(true);
    try { await apiPost(`/topics/${t.id}/reject`, { reason: "Rejected by editor" }); setRejected(true); toast("Topic rejected"); }
    catch { toast.error("Could not reject topic. Please try again."); }
    finally { setRejecting(false); }
  };

  if (rejected) return null;

  return (
    <Card
      data-testid={`topic-card-${t.id}`}
      className={cn(
        "surface-hover border-slate-200 surface p-4 relative",
        isSelected && "ring-2 ring-sky-400 border-sky-300",
      )}
    >
      {onToggleSelect && (
        <button
          type="button"
          onClick={onToggleSelect}
          className="absolute left-2 top-2 z-10 rounded p-0.5 text-slate-400 hover:text-sky-600 transition-colors"
        >
          {isSelected
            ? <CheckSquare className="h-4 w-4 text-sky-600" />
            : <Square className="h-4 w-4" />}
        </button>
      )}
      <div className={cn("flex items-start gap-4", onToggleSelect && "pl-5")}>
        <ScoreRing score={t.score} />
        <div className="min-w-0 flex-1">
          <div className="mb-1 flex flex-wrap items-center gap-2">
            <SiteBadge siteKey={t.site_key} small />
            <span className="rounded border border-slate-300 bg-slate-200/60 px-1.5 py-0.5 text-[10px] font-mono uppercase text-slate-600">{t.category}</span>
            <RiskBadge flags={t.risk_flags} />
            {article ? <StageBadge stage={article.stage} heldReason={article.held_reason} />
              : t.status === "used" ? <span className="text-[10px] font-mono uppercase text-slate-600">In Workbench</span>
              : t.status === "selected" ? <span className="text-[10px] font-mono uppercase text-emerald-600">Top pick</span>
              : <span className="text-[10px] font-mono uppercase text-sky-600">Add to Workbench</span>}
          </div>
          <h3 className={cn("font-heading text-base font-semibold leading-snug text-slate-900", kn && "font-kannada")}>{t.topic}</h3>
          <p className={cn("mt-1 text-sm text-slate-600", kn && "font-kannada")}>{t.angle}</p>
          <div className="mt-1 font-mono text-[11px] text-slate-400">{t.geography} · {t.why_trending}</div>
        </div>
      </div>

      {b.engagement !== undefined ? (
        <div className="mt-3 border-t border-slate-200 pt-3">
          <Bar label="Engagement" value={b.engagement} max={100} />
        </div>
      ) : (
        <div className="mt-3 grid grid-cols-1 gap-1.5 border-t border-slate-200 pt-3 sm:grid-cols-2">
          <Bar label="Relevance" value={b.relevance ?? 0} max={25} />
          <Bar label="Impact" value={b.impact ?? 0} max={20} />
          <Bar label="Trend" value={b.trend ?? 0} max={15} />
          <Bar label="Fresh" value={b.freshness ?? 0} max={15} />
          <Bar label="Sources" value={b.source ?? 0} max={15} />
          <Bar label="SEO" value={b.seo ?? 0} max={10} />
        </div>
      )}

      {t.selection_reason && (
        <div className="mt-2 rounded bg-slate-100/60 px-2 py-1.5 text-[11px] text-slate-600">
          <span className="font-mono uppercase text-slate-400">reason · </span>{t.selection_reason}
        </div>
      )}

      <div className="mt-3 flex flex-wrap items-center gap-2">
        <Button
          size="sm" className="gap-1.5 flex-1"
          data-testid={`topic-select-${t.id}`}
          disabled={select.isPending || (t.status === "used" && !article)}
          onClick={article ? () => nav(`/articles?open=${article.id}&site=${t.site_key}`) : doSelect}
        >
          {select.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Target className="h-3.5 w-3.5" />}
          {article ? "View in Workbench" : t.status === "used" ? "In Workbench" : "Add to Workbench"}
        </Button>
        {article && <div className="flex items-center gap-2" role="status" aria-live="polite" data-testid={`topic-workflow-stage-${t.id}`}>
          <span className="text-xs text-slate-600">Current stage:</span>
          <StageBadge stage={article.stage} heldReason={article.held_reason} />
        </div>}
        <Button size="sm" variant="ghost" data-testid={`topic-reject-${t.id}`} disabled={rejecting || rejected || t.status === "rejected" || article?.stage === "rejected"} onClick={doReject} className="gap-1 text-slate-600">
          <X className="h-3.5 w-3.5" /> Reject
        </Button>
      </div>
    </Card>
  );
}

function TopicGrid({
  topics, articlesByTopic, selectedIds, onToggleSelect, allSelected, onSelectAll,
}: {
  topics: Topic[];
  articlesByTopic: Map<string, Article>;
  selectedIds: Set<string>;
  onToggleSelect: (id: string) => void;
  allSelected: boolean;
  onSelectAll: () => void;
}) {
  const nav = useNavigate();
  const select = useSelectTopic();
  const [localRejected, setLocalRejected] = useState(new Set<string>());

  const doSelect = (t: Topic) => {
    const art = articlesByTopic.get(t.id);
    if (art) { nav(`/articles?open=${art.id}&site=${t.site_key}`); return; }
    select.mutate(t.id, {
      onSuccess: (a) => toast.success("Added to Workbench", { description: t.topic.slice(0, 80), action: { label: "Open", onClick: () => nav(`/articles?open=${a.id}&site=${t.site_key}`) } }),
      onError: () => toast.error("Could not select topic"),
    });
  };

  const doReject = async (t: Topic) => {
    try { await apiPost(`/topics/${t.id}/reject`, { reason: "Rejected by editor" }); setLocalRejected(p => new Set([...p, t.id])); toast("Topic rejected"); }
    catch { toast.error("Could not reject"); }
  };

  return (
    <div className="overflow-x-auto rounded-lg border border-slate-200">
      <table className="w-full min-w-[900px] text-left text-sm">
        <thead className="border-b border-slate-200 bg-slate-50 text-[11px] font-mono uppercase text-slate-500">
          <tr>
            <th className="w-8 px-3 py-2">
              <button type="button" onClick={onSelectAll} className="text-slate-400 hover:text-sky-600">
                {allSelected ? <CheckSquare className="h-4 w-4 text-sky-600" /> : <Square className="h-4 w-4" />}
              </button>
            </th>
            <th className="px-3 py-2">Score</th>
            <th className="px-3 py-2">Site</th>
            <th className="px-3 py-2">Category</th>
            <th className="px-3 py-2">Topic</th>
            <th className="px-3 py-2 text-center">Rel</th>
            <th className="px-3 py-2 text-center">Imp</th>
            <th className="px-3 py-2 text-center">Trend</th>
            <th className="px-3 py-2 text-center">Fresh</th>
            <th className="px-3 py-2 text-center">Src</th>
            <th className="px-3 py-2 text-center">SEO</th>
            <th className="px-3 py-2">Risk</th>
            <th className="px-3 py-2">Status</th>
            <th className="px-3 py-2">Actions</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {topics.filter(t => !localRejected.has(t.id)).map((t) => {
            const art = articlesByTopic.get(t.id);
            const b = t.score_breakdown;
            const kn = t.site_key === "kannadiga";
            const scoreColor = t.score >= 70 ? "text-emerald-700 bg-emerald-50" : t.score >= 55 ? "text-sky-700 bg-sky-50" : "text-amber-700 bg-amber-50";
            return (
              <tr key={t.id} className={cn("hover:bg-slate-50/60 transition-colors", selectedIds.has(t.id) && "bg-sky-50/40")}>
                <td className="px-3 py-2.5">
                  <button type="button" onClick={() => onToggleSelect(t.id)} className="text-slate-400 hover:text-sky-600">
                    {selectedIds.has(t.id) ? <CheckSquare className="h-4 w-4 text-sky-600" /> : <Square className="h-4 w-4" />}
                  </button>
                </td>
                <td className="px-3 py-2.5">
                  <span className={cn("inline-block rounded px-1.5 py-0.5 font-mono text-xs font-bold", scoreColor)}>{t.score}</span>
                </td>
                <td className="px-3 py-2.5"><SiteBadge siteKey={t.site_key} small /></td>
                <td className="px-3 py-2.5 font-mono text-[11px] text-slate-500 whitespace-nowrap">{t.category}</td>
                <td className="max-w-[260px] px-3 py-2.5">
                  <div className={cn("font-medium leading-snug text-slate-900 line-clamp-2", kn && "font-kannada")}>{t.topic}</div>
                  <div className={cn("mt-0.5 text-[11px] text-slate-500 line-clamp-1", kn && "font-kannada")}>{t.angle}</div>
                </td>
                <td className="px-3 py-2.5 text-center font-mono text-xs text-slate-600">{b.relevance ?? (b.engagement != null ? '—' : 0)}</td>
                <td className="px-3 py-2.5 text-center font-mono text-xs text-slate-600">{b.impact ?? (b.engagement != null ? '—' : 0)}</td>
                <td className="px-3 py-2.5 text-center font-mono text-xs text-slate-600">{b.trend ?? (b.engagement != null ? '—' : 0)}</td>
                <td className="px-3 py-2.5 text-center font-mono text-xs text-slate-600">{b.freshness ?? (b.engagement != null ? '—' : 0)}</td>
                <td className="px-3 py-2.5 text-center font-mono text-xs text-slate-600">{b.source ?? (b.engagement != null ? '—' : 0)}</td>
                <td className="px-3 py-2.5 text-center font-mono text-xs text-slate-600">{b.seo ?? (b.engagement != null ? b.engagement : 0)}</td>
                <td className="px-3 py-2.5"><RiskBadge flags={t.risk_flags} /></td>
                <td className="px-3 py-2.5">
                  {art ? <StageBadge stage={art.stage} heldReason={art.held_reason} /> : (
                    <span className={cn("font-mono text-[10px] uppercase", t.status === "rejected" ? "text-red-600" : t.status === "used" ? "text-slate-500" : "text-sky-600")}>
                      {t.status === "rejected" ? "Rejected" : t.status === "used" ? "In WB" : "Pending"}
                    </span>
                  )}
                </td>
                <td className="px-3 py-2.5">
                  <div className="flex items-center gap-1">
                    <Button size="sm" variant="outline" className="h-6 px-2 text-[11px] gap-1" disabled={select.isPending || t.status === "rejected"} onClick={() => doSelect(t)}>
                      <Target className="h-3 w-3" />{art ? "View" : "Add"}
                    </Button>
                    <Button size="sm" variant="ghost" className="h-6 px-2 text-[11px] gap-1 text-slate-500" disabled={t.status === "rejected"} onClick={() => doReject(t)}>
                      <X className="h-3 w-3" />
                    </Button>
                  </div>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

export default function Topics() {
  const nav = useNavigate();
  const [filter, setFilter] = useState("all");
  const [statusTab, setStatusTab] = useState<StatusTab>("pending");
  const [dupesOpen, setDupesOpen] = useState(readDupesOpen);
  const [viewMode, setViewMode] = useState<"card" | "grid">("card");
  const [selectedIds, setSelectedIds] = useState(new Set<string>());
  const [filtersOpen, setFiltersOpen] = useState(false);
  const [minScore, setMinScore] = useState(0);
  const [minRelevance, setMinRelevance] = useState(0);
  const [minImpact, setMinImpact] = useState(0);
  const [categoryFilter, setCategoryFilter] = useState("all");
  const [riskFilter, setRiskFilter] = useState("all");
  const [bulkAdding, setBulkAdding] = useState(false);
  const [bulkRejecting, setBulkRejecting] = useState(false);
  const [discovering, setDiscovering] = useState(false);

  const toggleDupes = () => setDupesOpen((open) => {
    try { localStorage.setItem(DUPES_OPEN, open ? "0" : "1"); } catch { /* storage unavailable */ }
    return !open;
  });

  const { data: topics, isLoading } = useTopics(filter === "all" ? undefined : filter);
  const { data: articles } = useArticles(filter === "all" ? undefined : filter);
  const { data: published } = usePublished(filter === "all" ? undefined : filter);
  const discover = useDiscover();
  const importPosts = useImportPosts();
  const select = useSelectTopic();
  const { data: stats } = useStats();
  const discoveryBlocked = !stats || stats.system.global_paused || stats.system.killswitch;

  const articlesByTopic = useMemo(() => new Map((articles ?? []).map((article) => [article.topic_id, article])), [articles]);

  const counts = useMemo(() => {
    const tally: Record<string, number> = { pending: 0, workbench: 0, scheduled: 0, published: 0, rejected: 0, all: 0 };
    for (const t of topics ?? []) {
      const group = topicGroup(t, articlesByTopic.get(t.id));
      tally[group] += 1;
      if (group !== "rejected") tally.all += 1;
    }
    return tally;
  }, [topics, articlesByTopic]);

  const sorted = useMemo(
    () => [...(topics ?? [])].filter((t) => {
      const group = topicGroup(t, articlesByTopic.get(t.id));
      return statusTab === "all" ? group !== "rejected" : group === statusTab;
    }).sort((a, b) => b.score - a.score),
    [topics, articlesByTopic, statusTab],
  );

  const categories = useMemo(() =>
    [...new Set((topics ?? []).map((t) => t.category).filter(Boolean))].sort(),
    [topics],
  );

  const displayed = useMemo(() =>
    sorted.filter((t) => {
      if (t.score < minScore) return false;
      if (categoryFilter !== "all" && t.category !== categoryFilter) return false;
      if (riskFilter === "low" && (t.risk_flags?.length ?? 0) > 0) return false;
      if (riskFilter === "flagged" && (t.risk_flags?.length ?? 0) === 0) return false;
      const b = t.score_breakdown;
      if (minRelevance > 0 && (b.relevance ?? 0) < minRelevance) return false;
      if (minImpact > 0 && (b.impact ?? 0) < minImpact) return false;
      return true;
    }),
    [sorted, minScore, categoryFilter, riskFilter, minRelevance, minImpact],
  );

  const allSelected = displayed.length > 0 && displayed.every((t) => selectedIds.has(t.id));
  const hasActiveFilters = minScore > 0 || minRelevance > 0 || minImpact > 0 || categoryFilter !== "all" || riskFilter !== "all";

  const rejectedDupes = useMemo(
    () => [...(topics ?? [])].filter((t) => t.status === "rejected" && t.similarity >= 0.5),
    [topics],
  );

  const toggleSelect = (id: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  };

  const toggleSelectAll = () => {
    if (allSelected) setSelectedIds(new Set());
    else setSelectedIds(new Set(displayed.map((t) => t.id)));
  };

  const resetFilters = () => {
    setMinScore(0); setMinRelevance(0); setMinImpact(0);
    setCategoryFilter("all"); setRiskFilter("all");
  };

  const bulkAddToWorkbench = async () => {
    const ids = [...selectedIds];
    setBulkAdding(true);
    let added = 0, failed = 0;
    for (const id of ids) {
      try { await select.mutateAsync(id); added++; }
      catch { failed++; }
    }
    setBulkAdding(false);
    setSelectedIds(new Set());
    if (added > 0) toast.success(`${added} topic${added > 1 ? "s" : ""} added to Workbench`);
    if (failed > 0) toast.error(`${failed} could not be added`);
  };

  const bulkReject = async () => {
    const ids = [...selectedIds];
    setBulkRejecting(true);
    let done = 0, failed = 0;
    for (const id of ids) {
      try { await apiPost(`/topics/${id}/reject`, { reason: "Bulk rejected by editor" }); done++; }
      catch { failed++; }
    }
    setBulkRejecting(false);
    setSelectedIds(new Set());
    if (done > 0) toast(`${done} topic${done > 1 ? "s" : ""} rejected`);
    if (failed > 0) toast.error(`${failed} could not be rejected`);
  };

  const doExport = () => {
    const toExport = selectedIds.size > 0 ? displayed.filter((t) => selectedIds.has(t.id)) : displayed;
    if (toExport.length === 0) { toast("Nothing to export"); return; }
    const headers = [
      "Score", "Site", "Category", "Topic", "Angle", "Geography", "Why Trending",
      "Risk Flags", "Status", "Relevance /25", "Impact /20", "Trend /15",
      "Freshness /15", "Sources /15", "SEO /10", "Engagement /100", "Focus Keyword",
    ];
    const rows = toExport.map((t) => {
      const b = t.score_breakdown;
      return [
        t.score, t.site_key, t.category, t.topic, t.angle, t.geography, t.why_trending,
        (t.risk_flags?.join("; ") ?? ""), t.status,
        b.relevance ?? "", b.impact ?? "", b.trend ?? "", b.freshness ?? "",
        b.source ?? "", b.seo ?? "", b.engagement ?? "", t.focus_keyword ?? "",
      ];
    });
    const csv = [headers, ...rows].map((row) =>
      row.map((c) => `"${String(c ?? "").replace(/"/g, '""')}"`).join(","),
    ).join("\n");
    const blob = new Blob(["\ufeff" + csv], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url; a.download = `topics-${new Date().toISOString().slice(0, 10)}.csv`;
    document.body.appendChild(a); a.click(); a.remove();
    URL.revokeObjectURL(url);
    toast.success(`Exported ${toExport.length} topic${toExport.length > 1 ? "s" : ""}`);
  };

  const runDiscover = async () => {
    const targets = filter === "all" ? ["kannadiga", "human"] : [filter];
    setDiscovering(true);
    try {
      for (const key of targets) {
        try {
          const r = await discover.mutateAsync(key);
          toast.success(`${key}: ${r.count} new topics · ${r.queued ?? 0} moved to the Workbench (70+) · ${r.rejected_duplicates} duplicates`);
        } catch (error) {
          toast.error(`${key}: ${error instanceof Error ? error.message : "Discovery failed"}`);
        }
      }
    } finally {
      setDiscovering(false);
    }
  };

  const runImport = () => {
    const targets = filter === "all" ? ["kannadiga", "human"] : [filter];
    targets.forEach((k) => importPosts.mutate(k, {
      onSuccess: (r) => toast.success(`${k}: imported ${r.count} published posts (last ${r.lookback_days}d)${r.simulated ? " · simulated" : ""}`),
    }));
  };

  return (
    <div className="space-y-5">
      {/* Header */}
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <SectionLabel>Topic Intelligence Matrix</SectionLabel>
          <h1 className="page-title">Discovered Candidates</h1>
          <p className="page-lede">Fresh news that fits each site&apos;s editorial brief, scored 0&ndash;100 by the AI editor. Topics scoring 70+ move to the Editorial Workbench automatically (up to the day&apos;s 18 per site); new topics are added every 2 hours.</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Button variant="outline" onClick={doExport} className="gap-2" title="Download filtered topics as CSV (opens in Excel)">
            <Download className="h-4 w-4" />
            {selectedIds.size > 0 ? `Export ${selectedIds.size} Selected` : "Export CSV"}
          </Button>
          <Button variant="outline" data-testid="topics-import-button" onClick={runImport} disabled={importPosts.isPending || !stats || stats.system.dry_run || stats.system.repair_lock} title="Published-post import is not enabled in local review" className="gap-2">
            {importPosts.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <DatabaseZap className="h-4 w-4" />}
            Import Published (90d)
          </Button>
          <Button data-testid="topics-discover-button" onClick={runDiscover} disabled={discovering || discoveryBlocked} className="gap-2">
            {discovering ? <Loader2 className="h-4 w-4 animate-spin" /> : <PlayCircle className="h-4 w-4" />}
            Discover Trends
          </Button>
        </div>
      </div>

      <p className="text-sm text-slate-600">{stats?.system.killswitch ? "Release Stop to allow discovery." : stats?.system.global_paused ? "Select Resume at the top to allow discovery." : !stats?.system.dry_run && stats?.system.mode === "auto" ? "Automatic service advances selected topics through research, writing, images, quality gates, and the publishing schedule." : stats?.system.manual_ai_enabled ? "Select a topic, then use Deep Research → Generate → Image in Editorial Workbench." : "Discovery collects topics only. AI research, writing, images and publishing are disabled in local review."}</p>

      {/* Site filters + view toggle */}
      <div className="flex flex-wrap items-center justify-between gap-2">
        <SiteSwitch value={filter} onChange={setFilter} testidPrefix="site-filter" />
        <div className="flex items-center gap-2">
          <div data-testid="published-count" className="inline-flex items-center gap-1.5 rounded-md border border-slate-200 bg-slate-100/40 px-3 py-1.5 font-mono text-xs text-slate-600">
            <DatabaseZap className="h-3.5 w-3.5 text-sky-600" /> {published?.length ?? 0} published posts indexed for dedupe
          </div>
          {/* View toggle */}
          <div className="flex items-center overflow-hidden rounded-md border border-slate-200 bg-slate-100/40">
            <button
              type="button" onClick={() => setViewMode("card")}
              className={cn("flex items-center gap-1 px-2.5 py-1.5 text-xs transition-colors", viewMode === "card" ? "bg-white text-slate-900 shadow-sm" : "text-slate-500 hover:text-slate-800")}
            >
              <LayoutGrid className="h-3.5 w-3.5" /> Cards
            </button>
            <button
              type="button" onClick={() => setViewMode("grid")}
              className={cn("flex items-center gap-1 px-2.5 py-1.5 text-xs transition-colors", viewMode === "grid" ? "bg-white text-slate-900 shadow-sm" : "text-slate-500 hover:text-slate-800")}
            >
              <Grid3x3 className="h-3.5 w-3.5" /> Grid
            </button>
          </div>
        </div>
      </div>

      {/* Status tabs */}
      <div className="flex flex-wrap items-center gap-2" role="tablist" aria-label="Topic status" data-testid="topic-status-tabs">
        {STATUS_TABS.map((s) => (
          <button key={s.key} type="button" role="tab" aria-selected={statusTab === s.key} data-testid={`topic-status-${s.key}`} onClick={() => setStatusTab(s.key)}
            className={cn("inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-xs font-medium transition-colors duration-150",
              statusTab === s.key ? "border-navy-800 bg-navy-800 text-white shadow-[0_6px_14px_-8px_rgb(1_27_75/0.6)]" : "border-slate-200 bg-white/70 text-slate-600 hover:border-amber-300 hover:text-navy-900")}>
            {s.label}
            <span className={cn("rounded-full px-1.5 font-mono text-[10.5px]", statusTab === s.key ? "bg-white/20" : "bg-slate-100 text-slate-500")}>{counts[s.key] ?? 0}</span>
          </button>
        ))}
      </div>

      {/* Score filters (collapsible) */}
      <Card className="border-slate-200 p-3">
        <button
          type="button"
          onClick={() => setFiltersOpen((o) => !o)}
          className="flex w-full items-center gap-2 text-left"
        >
          <Filter className="h-4 w-4 text-slate-400" />
          <SectionLabel>Score Filters{hasActiveFilters ? " · Active" : ""}</SectionLabel>
          <span className="ml-auto inline-flex shrink-0 items-center gap-2 text-xs text-slate-500">
            {hasActiveFilters && (
              <span
                role="button"
                tabIndex={0}
                onClick={(e) => { e.stopPropagation(); resetFilters(); }}
                onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.stopPropagation(); resetFilters(); } }}
                className="cursor-pointer rounded px-1.5 py-0.5 text-red-600 hover:bg-red-50"
              >Reset</span>
            )}
            <ChevronDown className={cn("h-3.5 w-3.5 transition-transform duration-150", filtersOpen && "rotate-180")} />
          </span>
        </button>
        {filtersOpen && (
          <div className="mt-3 grid grid-cols-2 gap-4 border-t border-slate-100 pt-3 sm:grid-cols-3 lg:grid-cols-6">
            <div>
              <label className="mb-1 block text-[11px] font-mono uppercase text-slate-500">Min Score</label>
              <div className="flex items-center gap-1.5">
                <input type="range" min={0} max={100} step={5} value={minScore} onChange={(e) => setMinScore(+e.target.value)} className="flex-1" />
                <span className="w-8 text-right font-mono text-xs font-medium text-slate-700">{minScore > 0 ? `${minScore}+` : "Off"}</span>
              </div>
            </div>
            <div>
              <label className="mb-1 block text-[11px] font-mono uppercase text-slate-500">Relevance</label>
              <div className="flex items-center gap-1.5">
                <input type="range" min={0} max={25} step={1} value={minRelevance} onChange={(e) => setMinRelevance(+e.target.value)} className="flex-1" />
                <span className="w-8 text-right font-mono text-xs font-medium text-slate-700">{minRelevance > 0 ? `${minRelevance}+` : "Off"}</span>
              </div>
            </div>
            <div>
              <label className="mb-1 block text-[11px] font-mono uppercase text-slate-500">Impact</label>
              <div className="flex items-center gap-1.5">
                <input type="range" min={0} max={20} step={1} value={minImpact} onChange={(e) => setMinImpact(+e.target.value)} className="flex-1" />
                <span className="w-8 text-right font-mono text-xs font-medium text-slate-700">{minImpact > 0 ? `${minImpact}+` : "Off"}</span>
              </div>
            </div>
            <div>
              <label className="mb-1 block text-[11px] font-mono uppercase text-slate-500">Category</label>
              <select
                value={categoryFilter}
                onChange={(e) => setCategoryFilter(e.target.value)}
                className="w-full rounded border border-slate-200 bg-white px-2 py-1 text-xs text-slate-700 focus:outline-none focus:ring-1 focus:ring-sky-400"
              >
                <option value="all">All categories</option>
                {categories.map((c) => <option key={c} value={c}>{c}</option>)}
              </select>
            </div>
            <div>
              <label className="mb-1 block text-[11px] font-mono uppercase text-slate-500">Risk</label>
              <select
                value={riskFilter}
                onChange={(e) => setRiskFilter(e.target.value)}
                className="w-full rounded border border-slate-200 bg-white px-2 py-1 text-xs text-slate-700 focus:outline-none focus:ring-1 focus:ring-sky-400"
              >
                <option value="all">All topics</option>
                <option value="low">Low risk only</option>
                <option value="flagged">Has risk flags</option>
              </select>
            </div>
            <div className="flex items-end pb-1">
              <span className="font-mono text-sm text-slate-500">
                <span className="font-semibold text-slate-800">{displayed.length}</span> / {sorted.length} shown
              </span>
            </div>
          </div>
        )}
      </Card>

      {/* Bulk action bar */}
      {selectedIds.size > 0 && (
        <div className="sticky top-2 z-10 flex flex-wrap items-center gap-3 rounded-lg border border-sky-200 bg-sky-50/95 px-4 py-2.5 shadow-sm backdrop-blur-sm">
          <CheckSquare className="h-4 w-4 text-sky-600 shrink-0" />
          <span className="font-medium text-sky-900 text-sm">{selectedIds.size} selected</span>
          <Button size="sm" className="gap-1.5" disabled={bulkAdding} onClick={bulkAddToWorkbench}>
            {bulkAdding ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Target className="h-3.5 w-3.5" />}
            Add to Workbench
          </Button>
          <Button size="sm" variant="outline" className="gap-1.5 border-red-200 text-red-700 hover:bg-red-50" disabled={bulkRejecting} onClick={bulkReject}>
            {bulkRejecting ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <X className="h-3.5 w-3.5" />}
            Reject All
          </Button>
          <Button size="sm" variant="outline" className="gap-1.5" onClick={doExport}>
            <Download className="h-3.5 w-3.5" /> Export
          </Button>
          <button type="button" className="ml-auto text-xs text-slate-500 hover:text-slate-800" onClick={() => setSelectedIds(new Set())}>
            Clear selection
          </button>
        </div>
      )}

      {/* Select all / deselect all row */}
      {displayed.length > 0 && (
        <div className="flex items-center gap-3">
          <button
            type="button" onClick={toggleSelectAll}
            className="flex items-center gap-1.5 rounded border border-slate-200 bg-white px-2.5 py-1 text-xs text-slate-600 hover:bg-slate-50 transition-colors"
          >
            {allSelected
              ? <CheckSquare className="h-3.5 w-3.5 text-sky-600" />
              : <Square className="h-3.5 w-3.5 text-slate-400" />}
            {allSelected ? "Deselect All" : `Select All (${displayed.length})`}
          </button>
          {selectedIds.size > 0 && <span className="text-xs text-slate-500">{selectedIds.size} selected</span>}
        </div>
      )}

      {/* Dupe guard */}
      {rejectedDupes.length > 0 && (
        <Card className="border-red-100/50 bg-red-50/20 p-4" data-testid="duplicate-guard">
          <button type="button" onClick={toggleDupes} aria-expanded={dupesOpen} aria-controls="duplicate-guard-list" data-testid="duplicate-guard-toggle"
            className="flex w-full items-center gap-2 text-left">
            <ShieldX className="h-4 w-4 shrink-0 text-red-600" />
            <SectionLabel>Duplicate Guard &mdash; {rejectedDupes.length} candidate(s) rejected as near-duplicates</SectionLabel>
            <span className="ml-auto inline-flex shrink-0 items-center gap-1 text-xs font-medium text-slate-600 hover:text-slate-900">
              {dupesOpen ? "Hide" : "Expand"}
              <ChevronDown className={cn("h-3.5 w-3.5 transition-transform duration-150", dupesOpen && "rotate-180")} />
            </span>
          </button>
          {dupesOpen && <div id="duplicate-guard-list" className="mt-2 space-y-1.5">
            {rejectedDupes.map((t) => (
              <div key={t.id} data-testid={`rejected-dupe-${t.id}`} className="flex items-start gap-2 rounded border border-red-100/40 bg-slate-50/40 px-3 py-1.5">
                <SiteBadge siteKey={t.site_key} small />
                <div className="min-w-0">
                  <div className={cn("truncate text-sm text-slate-700", t.site_key === "kannadiga" && "font-kannada")}>{t.topic}</div>
                  <div className="text-[11px] text-red-700/80">{t.selection_reason}</div>
                </div>
              </div>
            ))}
          </div>}
        </Card>
      )}

      {/* Main content */}
      {isLoading ? (
        <div className="flex justify-center py-20"><Loader2 className="h-6 w-6 animate-spin text-slate-500" /></div>
      ) : displayed.length === 0 ? (
        (topics ?? []).length === 0
          ? <EmptyState title="No candidates yet" hint="Run trend discovery to populate the queue for each site." />
          : <EmptyState title="No topics match the current filters" hint="Adjust the score filters or status tab above." />
      ) : viewMode === "card" ? (
        <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
          {displayed.map((t) => (
            <TopicCard key={t.id} t={t} article={articlesByTopic.get(t.id)} isSelected={selectedIds.has(t.id)} onToggleSelect={() => toggleSelect(t.id)} />
          ))}
        </div>
      ) : (
        <TopicGrid
          topics={displayed}
          articlesByTopic={articlesByTopic}
          selectedIds={selectedIds}
          onToggleSelect={toggleSelect}
          allSelected={allSelected}
          onSelectAll={toggleSelectAll}
        />
      )}
    </div>
  );
}
