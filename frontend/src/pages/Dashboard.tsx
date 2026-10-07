import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { motion } from "motion/react";
import {
  ArrowRight, CheckCircle2, Clock, FileEdit, Loader2, PlayCircle, Radar, ShieldAlert, XCircle,
} from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import RouteSelector from "@/components/RouteSelector";
import { Metric, SectionLabel, SiteBadge, StageBadge } from "@/lib/ui";
import { useDiscover, useStats, useUpdateSite, useUpdateSystem } from "@/lib/hooks";
import type { SiteStat } from "@/lib/types";
import { cn } from "@/lib/utils";

const STAGES = [
  "Discover", "Deduplicate", "Score & Select", "Research",
  "Generate + Image", "Quality Gate", "WordPress Publish",
];

function PipelineBar() {
  return (
    <Card className="border-slate-200 surface p-5">
      <SectionLabel>Editorial Pipeline · 7 stages · automatic quality gates</SectionLabel>
      <div className="mt-4 flex flex-wrap items-center gap-2">
        {STAGES.map((s, i) => (
          <div key={s} className="flex items-center gap-2">
            <div className="flex items-center gap-2 rounded-md border border-slate-200 bg-slate-100/50 px-3 py-1.5">
              <span className="font-mono text-[10px] font-semibold text-amber-700">{String(i + 1).padStart(2, "0")}</span>
              <span className="text-xs text-slate-700">{s}</span>
            </div>
            {i < STAGES.length - 1 && <ArrowRight className="h-3.5 w-3.5 text-slate-400" />}
          </div>
        ))}
      </div>
    </Card>
  );
}

function SiteCard({ s }: { s: SiteStat }) {
  const nav = useNavigate();
  const updateSite = useUpdateSite();
  const kn = s.key === "kannadiga";

  const toggle = (field: "auto_publish" | "paused", val: boolean, label: string) =>
    updateSite.mutate({ key: s.key, body: { [field]: val } }, { onSuccess: () => toast(label) });

  return (
    <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.25 }}>
      <Card className={cn("surface-hover relative overflow-hidden border-slate-200 surface before:absolute before:inset-x-6 before:top-0 before:h-px before:bg-gradient-to-r before:from-transparent before:to-transparent after:pointer-events-none after:absolute after:-top-24 after:left-1/2 after:h-40 after:w-2/3 after:-translate-x-1/2 after:rounded-full after:blur-3xl", kn ? "before:via-violet-600/80 after:bg-violet-500/10" : "before:via-cyan-700/80 after:bg-cyan-500/10")}>
        <div className="flex items-start justify-between p-5 pb-3">
          <div>
            <div className="flex items-center gap-2">
              <SiteBadge siteKey={s.key} />
              {s.connected ? (
                <span className="inline-flex items-center gap-1 text-[10px] font-mono uppercase text-emerald-600"><CheckCircle2 className="h-3 w-3" /> connected</span>
              ) : (
                <span className="inline-flex items-center gap-1 text-[10px] font-mono uppercase text-slate-500"><XCircle className="h-3 w-3" /> not connected</span>
              )}
            </div>
            <h3 className={cn("mt-2 font-heading text-lg font-semibold text-slate-900", kn && "font-kannada")}>{s.name}</h3>
            <div className="font-mono text-xs text-slate-500">{s.domain} · {s.timezone}</div>
          </div>
          <div className="text-right">
            <div className="font-mono text-[10px] uppercase tracking-wider text-slate-500">Daily Target</div>
            <div className="font-mono text-2xl font-bold text-slate-950">{s.published_today + s.scheduled}<span className="text-slate-400">/{s.daily_quota}</span></div>
          </div>
        </div>

        <div className="grid grid-cols-2 gap-2 px-5 sm:grid-cols-4 md:grid-cols-2 xl:grid-cols-4">
          <Metric label="Published" value={s.published_today} accent="text-emerald-600" />
          <Metric label="Scheduled" value={s.scheduled} accent="text-sky-600" />
          <Metric label="Drafts" value={s.drafts} accent="text-indigo-700" />
          <Metric label="Held" value={s.held_review} accent={s.held_review ? "text-amber-600" : "text-slate-600"} />
        </div>

        <div className="mt-4 flex flex-wrap items-center justify-between gap-2 border-t border-slate-200 bg-slate-100/30 px-5 py-3">
          <div className="flex items-center gap-2 font-mono text-[11px] text-slate-600">
            <Clock className="h-3.5 w-3.5" /> next {s.next_run ? new Date(s.next_run).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) : "—"}
            <span className="text-slate-400">· {s.remaining} slots left</span>
          </div>
          <div className="flex items-center gap-1.5">
            <Button
              size="xs" variant={s.auto_publish ? "default" : "outline"}
              data-testid={`site-auto-toggle-${s.key}`}
              title={s.auto_publish ? "Automatic publishing is enabled" : "Enable automatic publishing for this website"}
              onClick={() => toggle("auto_publish", !s.auto_publish, s.auto_publish ? "Auto-publish OFF" : "Auto-publish ON")}
            >
              Auto {s.auto_publish ? "On" : "Off"}
            </Button>
            <Button
              size="xs" variant={s.paused ? "secondary" : "outline"}
              data-testid={`site-pause-toggle-${s.key}`}
              onClick={() => toggle("paused", !s.paused, s.paused ? `${s.name} resumed` : `${s.name} paused`)}
            >
              {s.paused ? "Paused" : "Active"}
            </Button>
            <Button size="xs" variant="ghost" data-testid={`site-open-${s.key}`} onClick={() => nav(`/articles?site=${s.key}`)} className="gap-1">
              Open <ArrowRight className="h-3 w-3" />
            </Button>
          </div>
        </div>
      </Card>
    </motion.div>
  );
}

export default function Dashboard() {
  const { data: stats, isLoading } = useStats();
  const discover = useDiscover();
  const updateSystem = useUpdateSystem();
  const nav = useNavigate();

  const [discovering, setDiscovering] = useState(false);
  const discoveryBlocked = !stats || stats.system.global_paused || stats.system.killswitch;
  const runBoth = async () => {
    setDiscovering(true);
    let completed = false;
    try {
      for (const key of ["kannadiga", "human"]) {
        try {
          const r = await discover.mutateAsync(key);
          toast.success(`${key}: ${r.count} candidates discovered`);
          completed = true;
        } catch (error) {
          toast.error(`${key}: ${error instanceof Error ? error.message : "Discovery failed"}`);
        }
      }
    } finally {
      setDiscovering(false);
    }
    if (completed) nav("/topics");
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <SectionLabel>Command Center</SectionLabel>
          <h1 className="page-title">Editorial Newsroom</h1>
          <p className="page-lede">
            Source-grounded research, original news analysis, editorial thumbnails, and SEO — routed to two distinct audiences.
            Currently in <span className="font-mono uppercase text-sky-600">{stats?.system.mode?.replace("_", " ")}</span> mode.
          </p>
        </div>
        <Button data-testid="run-pipeline-now-button" onClick={runBoth} disabled={discovering || discoveryBlocked} className="gap-2">
          {discovering ? <Loader2 className="h-4 w-4 animate-spin" /> : <PlayCircle className="h-4 w-4" />}
          Run Discovery — Both Sites
        </Button>
      </div>

      <p className="text-sm text-slate-600">{stats?.system.killswitch ? "Release Stop to allow discovery." : stats?.system.global_paused ? "Select Resume at the top to allow discovery." : "Run Discovery reads public news feeds for both sites. No AI API key is needed and no articles are published."}</p>

      <PipelineBar />

      <Card className="border-slate-200 surface p-5">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div className="flex items-start gap-3">
            <Radar className={cn("mt-0.5 h-5 w-5", stats?.system.scheduler_enabled ? "text-emerald-600 animate-pulse" : "text-slate-500")} />
            <div>
              <SectionLabel>Auto Scheduler</SectionLabel>
              <p className="mt-1 max-w-xl text-sm text-slate-600">
                Runs discovery, research, article writing, thumbnail creation, and WordPress scheduling for both websites.
              </p>
            </div>
          </div>
          <Button
            data-testid="scheduler-toggle-button" disabled={stats?.system.dry_run || stats?.system.repair_lock}
            variant={stats?.system.scheduler_enabled ? "default" : "outline"}
            onClick={() =>
              updateSystem.mutate(
                { scheduler_enabled: !stats?.system.scheduler_enabled },
                { onSuccess: () => toast(stats?.system.scheduler_enabled ? "Auto scheduler stopped" : "Auto scheduler running") },
              )
            }
            className="gap-2"
          >
            <Radar className="h-4 w-4" />
            {stats?.system.scheduler_enabled ? "Scheduler: ON" : "Scheduler: OFF"}
          </Button>
        </div>
        <div className="mt-4 flex flex-wrap items-center gap-2 border-t border-slate-200 pt-3 text-sm" data-testid="now-producing">
          <span className="text-[11px] font-medium uppercase tracking-[0.14em] text-slate-500">Now producing</span>
          {stats?.producing ? (
            <>
              <SiteBadge siteKey={stats.producing.site_key} small />
              <StageBadge stage={stats.producing.stage} heldReason={stats.producing.held_reason} />
              <a href={`/articles?open=${stats.producing.id}&site=${stats.producing.site_key}`}
                 className={cn("min-w-0 flex-1 truncate text-slate-800 hover:underline", stats.producing.site_key === "kannadiga" && "font-kannada leading-snug")}>
                {stats.producing.topic}
              </a>
            </>
          ) : (
            <span className="text-slate-600">Idle · next turn: {stats?.next_site === "human" ? "the English site" : "the Kannada site"}</span>
          )}
          {stats?.next_article && (
            <div className="flex min-w-0 basis-full items-center gap-2" data-testid="next-article">
              <span className="text-[11px] font-medium uppercase tracking-[0.14em] text-slate-500">Next</span>
              <SiteBadge siteKey={stats.next_article.site_key} small />
              <StageBadge stage={stats.next_article.stage} heldReason={stats.next_article.held_reason} />
              <a href={`/articles?open=${stats.next_article.id}&site=${stats.next_article.site_key}`}
                 className={cn("min-w-0 flex-1 truncate text-slate-800 hover:underline", stats.next_article.site_key === "kannadiga" && "font-kannada leading-snug")}>
                {stats.next_article.topic}
              </a>
            </div>
          )}
          <span className="basis-full text-xs text-slate-500">One article at a time, alternating sites: Kannada → English → Kannada → English. {stats?.system.research_ahead ? "The next article's Deep Research starts once the current one is on its thumbnail." : "The next article starts once the current one is scheduled for publishing."}</span>
        </div>
      </Card>

      <RouteSelector compact />

      {isLoading ? (
        <div className="flex justify-center py-20"><Loader2 className="h-6 w-6 animate-spin text-slate-500" /></div>
      ) : (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:gap-6">
          {stats?.sites.map((s) => <SiteCard key={s.key} s={s} />)}
        </div>
      )}

      <Card className="border-slate-200 surface p-5">
        <div className="flex items-center gap-2">
          <ShieldAlert className="h-4 w-4 text-amber-600" />
          <SectionLabel>Editorial safeguards active</SectionLabel>
        </div>
        <div className="mt-3 grid grid-cols-1 gap-3 text-sm text-slate-600 sm:grid-cols-3">
          <div className="flex items-start gap-2"><FileEdit className="mt-0.5 h-4 w-4 text-sky-600" /> Sources, claims, formatting, and SEO are checked automatically before publication.</div>
          <div className="flex items-start gap-2"><ShieldAlert className="mt-0.5 h-4 w-4 text-amber-600" /> {stats?.system.high_risk_review_required ? "Failed checks, provider errors, and high-risk subjects stop for attention." : "Only failed automatic checks and provider errors stop for attention; high-risk labels do not pause automation."}</div>
          <div className="flex items-start gap-2"><CheckCircle2 className="mt-0.5 h-4 w-4 text-emerald-600" /> WordPress writes are live and verified by reading the saved post back from the website.</div>
        </div>
      </Card>
    </div>
  );
}
