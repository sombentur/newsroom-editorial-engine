// MAINTAINER NOTE (2026-09-27): GLOBAL ALERTS: /ai-alerts polls active held articles. Older records lack original provider identity, so their banner labels the current configuration explicitly. Do not present inferred provider identity or an ambiguous 429 as confirmed exhausted credits. See docs/MAINTAINER_HANDOFF.md.
import { useIsMutating, useQuery } from "@tanstack/react-query";
import { apiGet } from "@/lib/api";
import { useEffect, useState, type ReactNode } from "react";
import { NavLink, Outlet, useLocation } from "react-router-dom";
import {
  Activity, AlertOctagon, AlertTriangle, CalendarClock, ChevronDown, FileSpreadsheet, FileText, Gauge, Info, LayoutDashboard,
  ListChecks, LogOut, Menu, PauseCircle, PlayCircle, ScrollText, Settings2, ShieldAlert, Sparkles,
} from "lucide-react";
import { toast } from "sonner";
import { Toaster } from "@/components/ui/sonner";
import { Button } from "@/components/ui/button";
import {
  Dialog, DialogClose, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle, DialogTrigger,
} from "@/components/ui/dialog";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle, SheetTrigger } from "@/components/ui/sheet";
import { BrandLogo } from "@/components/Brand";
import { useStats, useUpdateSystem } from "@/lib/hooks";
import type { SiteStat, SystemSettings } from "@/lib/types";
import { cn } from "@/lib/utils";
import { endSession } from "@/lib/session";

type Alert = { article_id: string; task: string; kind: string; provider: string };
type SignOff = { article_id: string; site_key: string; title: string; flags: string[]; since: string };
const SEEN_SIGN_OFFS = "newsroom-sign-off-seen";

function alertAdvice(kind: string) {
  return kind === "quota" ? "API credits or quota exhausted. Check the provider’s billing and usage limits."
    : kind === "auth" ? "API authentication failed. Check the configured key."
    : kind === "model_unavailable" ? "The selected model is unavailable. Choose an accessible model."
    : "Rate or quota limit reached. Exhausted credits are not confirmed. Check usage limits; wait before retrying a temporary limit.";
}

function Notice({ tone, icon, title, children, action }: {
  tone: "info" | "success" | "warning"; icon: ReactNode; title: ReactNode; children?: ReactNode; action?: ReactNode;
}) {
  const tones = {
    info: "border-sky-200 bg-sky-50/80 text-sky-900 [&_.notice-icon]:text-sky-600",
    success: "border-emerald-200/80 bg-emerald-50/70 text-emerald-900 [&_.notice-icon]:text-emerald-600",
    warning: "border-amber-300/70 bg-amber-50/85 text-amber-900 [&_.notice-icon]:text-amber-600",
  };
  return (
    <div role={tone === "warning" ? "alert" : undefined}
      className={cn("mb-4 rounded-2xl border px-4 py-3 text-sm shadow-[0_1px_2px_rgb(1_27_75/0.04)] backdrop-blur-sm", tones[tone])}>
      <div className="flex items-start gap-3">
        <span className="notice-icon mt-0.5 shrink-0">{icon}</span>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-1">
            <div className="font-medium">{title}</div>
            {action}
          </div>
          {children && <div className="mt-1 text-[13px] leading-relaxed opacity-90">{children}</div>}
        </div>
      </div>
    </div>
  );
}

function AIAlerts() {
  const { data = [] } = useQuery({ queryKey: ["ai-alerts"], queryFn: () => apiGet<Alert[]>("/ai-alerts"), refetchInterval: 10000 });
  const [open, setOpen] = useState(false);
  if (!data.length) return null;
  const groups = [...new Map(data.map(a => [`${a.provider}:${a.task}:${a.kind}`, a])).values()];
  return (
    <Notice
      tone="warning"
      icon={<AlertTriangle className="h-4 w-4" />}
      title={<>AI provider needs attention <span className="font-normal opacity-75">· {data.length} affected post(s)</span></>}
      action={
        <div className="flex items-center gap-3 text-[13px]">
          <a className="underline decoration-amber-400 underline-offset-4 hover:decoration-amber-700" href="/wizard?tab=ai">Open AI provider settings</a>
          <button type="button" onClick={() => setOpen(o => !o)} aria-expanded={open} className="inline-flex items-center gap-1 text-amber-800 hover:text-amber-900">
            {open ? "Hide" : "Details"} <ChevronDown className={cn("h-3.5 w-3.5 transition-transform", open && "rotate-180")} />
          </button>
        </div>
      }
    >
      <div className="text-amber-900/90">
        <strong>{groups[0].provider}</strong> · {groups[0].task}{groups.length > 1 && ` and ${groups.length - 1} more`}
      </div>
      {open && (
        <div className="mt-3 space-y-3 border-t border-amber-200/60 pt-3">
          {groups.map(a => (
            <div key={`${a.provider}:${a.task}:${a.kind}`}>
              <strong>{a.provider}</strong> · {a.task}
              <p>{alertAdvice(a.kind)}</p>
              <a className="underline underline-offset-4" href={`/articles?open=${a.article_id}`}>View affected post</a>
            </div>
          ))}
          <p className="text-xs opacity-75">After correcting the provider setting or quota, retry affected posts. Notices clear when the posts leave the hold.</p>
        </div>
      )}
    </Notice>
  );
}

// Owner rule (28 Sep 2026): a high-risk article waits for the owner's approval while production moves on. A popup
// names it once (remembered in this browser), and a banner lists every such article until it is approved or rejected.
function SignOffAlerts() {
  const { data = [] } = useQuery({ queryKey: ["sign-off-alerts"], queryFn: () => apiGet<SignOff[]>("/sign-off-alerts"), refetchInterval: 15000 });
  useEffect(() => {
    let seen: string[] = [];
    try { seen = JSON.parse(localStorage.getItem(SEEN_SIGN_OFFS) || "[]"); } catch { seen = []; }
    const fresh = data.filter(a => !seen.includes(a.article_id));
    for (const a of fresh) {
      toast.warning(`“${a.title}” is awaiting your editorial approval`, {
        description: `High-risk subject (${a.flags.join(", ") || "flagged"}). The next article has started meanwhile.`,
        duration: 60000,
        action: { label: "Review", onClick: () => { window.location.href = `/articles?open=${a.article_id}`; } },
      });
    }
    if (fresh.length) {
      try { localStorage.setItem(SEEN_SIGN_OFFS, JSON.stringify([...seen, ...fresh.map(a => a.article_id)].slice(-200))); } catch { /* storage unavailable */ }
    }
  }, [data]);
  if (!data.length) return null;
  return (
    <Notice tone="warning" icon={<ShieldAlert className="h-4 w-4" />}
      title={<>Awaiting your editorial approval <span className="font-normal opacity-75">· {data.length} post{data.length > 1 ? "s" : ""}</span></>}>
      <ul className="space-y-1">
        {data.map(a => (
          <li key={a.article_id}>
            <a className="underline decoration-amber-400 underline-offset-4 hover:decoration-amber-700" href={`/articles?open=${a.article_id}`}>{a.title}</a>
            <span className="opacity-75"> · {a.site_key === "kannadiga" ? "Kannada" : "English"} · {a.flags.join(", ")}</span>
          </li>
        ))}
      </ul>
      <p className="mt-1 text-xs opacity-75">High-risk subjects wait for your Approve locally; production continues with the next article meanwhile. Approved posts take the next free publishing slot.</p>
    </Notice>
  );
}

const NAV_GROUPS = [
  { label: "Newsroom", items: [
    { to: "/", label: "Command Center", icon: LayoutDashboard, testid: "nav-dashboard" },
    { to: "/topics", label: "Topic Intelligence", icon: ListChecks, testid: "nav-topics" },
    { to: "/articles", label: "Editorial Workbench", icon: FileText, testid: "nav-articles" },
    { to: "/manual", label: "Manual Workbench", icon: FileSpreadsheet, testid: "nav-manual" },
    { to: "/schedule", label: "Broadcast Schedule", icon: CalendarClock, testid: "nav-schedule" },
  ] },
  { label: "Studio", items: [
    { to: "/prompts", label: "Prompt Studio", icon: Sparkles, testid: "nav-prompts" },
    { to: "/wizard", label: "Setup Wizard", icon: Settings2, testid: "nav-wizard" },
  ] },
  { label: "System", items: [
    { to: "/health", label: "Integration Health", icon: Gauge, testid: "nav-health" },
    { to: "/audit", label: "Audit Log", icon: ScrollText, testid: "nav-audit" },
  ] },
];
const NAV = NAV_GROUPS.flatMap(g => g.items);

const MODES = [
  { key: "research_only", label: "Research" },
  { key: "review", label: "Review" },
  { key: "auto", label: "Auto" },
] as const;

function Clock() {
  const [now, setNow] = useState(new Date());
  useEffect(() => {
    const t = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(t);
  }, []);
  const fmt = (tz: string) =>
    now.toLocaleTimeString("en-GB", { timeZone: tz, hour: "2-digit", minute: "2-digit", second: "2-digit" });
  return (
    <div className="hidden items-center rounded-full border border-slate-200 bg-white/60 px-1 py-1 font-mono text-[11px] tabular-nums text-slate-700 xl:flex" data-testid="live-clock">
      {[["IST", "Asia/Kolkata"], ["ET", "America/New_York"], ["UTC", "UTC"]].map(([label, tz], i) => (
        <span key={label} className={cn("flex items-center gap-1.5 px-2.5", i > 0 && "border-l border-slate-200")}>
          <span className="font-sans text-[10px] font-semibold tracking-wider text-slate-500">{label}</span>{fmt(tz)}
        </span>
      ))}
    </div>
  );
}

// Selected navigation item: a glass panel with an amber marker. The suffix keeps test ids unique in the mobile drawer.
function PrimaryNav({ suffix = "" }: { suffix?: string }) {
  return (
    <nav aria-label="Primary" className="flex-1 space-y-6 overflow-y-auto px-3 pb-2 pt-3">
      {NAV_GROUPS.map(group => (
        <div key={group.label}>
          <div className="mb-1.5 px-3 text-[10px] font-semibold uppercase tracking-[0.2em] text-slate-500">{group.label}</div>
          <div className="space-y-1">
            {group.items.map((n) => (
              <NavLink
                key={n.to}
                to={n.to}
                end={n.to === "/"}
                data-testid={n.testid + suffix}
                className={({ isActive }) =>
                  cn(
                    "group relative flex h-10 items-center gap-3 rounded-xl border border-transparent px-3 text-[13.5px] font-medium transition-all duration-200",
                    isActive ? "glass-panel text-navy-900" : "text-slate-600 hover:bg-amber-50/80 hover:text-navy-900",
                  )
                }
              >
                {({ isActive }) => (
                  <>
                    <span aria-hidden="true" className={cn(
                      "absolute left-0 top-1/2 h-5 w-[3px] -translate-y-1/2 rounded-full bg-amber-500 transition-all duration-300",
                      isActive ? "scale-y-100 opacity-100" : "scale-y-50 opacity-0 group-hover:scale-y-75 group-hover:opacity-70",
                    )} />
                    <n.icon className={cn("h-4 w-4 shrink-0 transition-colors", isActive ? "text-navy-700" : "text-slate-500 group-hover:text-amber-600")} />
                    <span className="truncate">{n.label}</span>
                  </>
                )}
              </NavLink>
            ))}
          </div>
        </div>
      ))}
    </nav>
  );
}

// Each website's output today and its publishing state, in the site's own colour.
function SitesPanel({ sites }: { sites: SiteStat[] }) {
  if (!sites.length) return null;
  return (
    <div className="rounded-xl border border-slate-200 bg-white/60 p-3" data-testid="sites-panel">
      <div className="mb-2.5 text-[10px] font-semibold uppercase tracking-[0.18em] text-slate-500">Today’s output</div>
      <div className="space-y-3">
        {sites.map(s => {
          const done = s.published_today + s.scheduled;
          const kn = s.key === "kannadiga";
          const [state, tone] = s.paused ? ["Paused", "border-amber-300/80 bg-amber-50 text-amber-900"]
            : s.auto_publish ? ["Auto", "border-emerald-200 bg-emerald-50 text-emerald-800"]
            : ["Manual", "border-slate-300 bg-white text-slate-600"];
          return (
            <div key={s.key}>
              <div className="mb-1.5 flex items-center justify-between gap-2 text-xs">
                <span className="flex min-w-0 items-center gap-1.5">
                  <span className={cn("h-2 w-2 shrink-0 rounded-full", kn ? "bg-violet-600" : "bg-cyan-600")} aria-hidden="true" />
                  <span className={cn("truncate font-medium text-slate-800", kn && "font-kannada leading-none")}>{s.name}</span>
                  <span className={cn("rounded-full border px-1.5 text-[9.5px] font-semibold uppercase leading-4 tracking-wide", tone)}
                    title={s.paused ? `${s.name} is paused` : s.auto_publish ? "Automatic publishing is on" : "Automatic publishing is off"}>{state}</span>
                </span>
                <span className="font-mono tabular-nums text-slate-700">{done}<span className="text-slate-400">/{s.daily_quota}</span></span>
              </div>
              <div className="h-1.5 overflow-hidden rounded-full bg-navy-900/[0.07]" role="progressbar"
                aria-valuemin={0} aria-valuemax={s.daily_quota} aria-valuenow={Math.min(done, s.daily_quota)}
                aria-label={`${s.name}: ${done} of ${s.daily_quota} posts published or scheduled today`}>
                <div className={cn("h-full rounded-full transition-[width] duration-700 ease-out", kn ? "bg-gradient-to-r from-violet-500 to-violet-700" : "bg-gradient-to-r from-cyan-500 to-cyan-700")}
                  style={{ width: `${Math.min(100, (done / Math.max(1, s.daily_quota)) * 100)}%` }} />
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function ModePanel({ system, setMode, suffix = "" }: { system?: SystemSettings; setMode: (mode: string) => void; suffix?: string }) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white/60 p-3">
      <div className="mb-2 text-[10px] font-semibold uppercase tracking-[0.18em] text-slate-500">Operating mode</div>
      <div className="grid grid-cols-3 gap-1 rounded-lg border border-slate-200 bg-slate-100 p-1" role="group" aria-label="Operating mode">
        {MODES.map((m) => (
          <button
            key={m.key}
            type="button"
            data-testid={`mode-${m.key}${suffix}`}
            aria-pressed={system?.mode === m.key}
            onClick={() => setMode(m.key)}
            title={m.key === "research_only" ? "Research and dossier preparation" : m.key === "review" ? "Generate drafts for human review" : "Automatic workflow mode; live WordPress writes remain subject to separate safety controls"}
            className={cn(
              "rounded-md px-1.5 py-1.5 text-[11.5px] font-medium transition-all duration-200",
              system?.mode === m.key
                ? "bg-gradient-to-b from-navy-700 to-navy-800 text-white shadow-[0_4px_12px_-4px_rgb(1_27_75/0.6),inset_0_1px_0_rgb(255_255_255/0.16)]"
                : "text-slate-600 hover:bg-amber-50 hover:text-navy-900",
            )}
          >
            {m.label}
          </button>
        ))}
      </div>
    </div>
  );
}

function AccountButton() {
  return (
    <button
      type="button"
      onClick={() => endSession("/")}
      className="group flex w-full items-center justify-between rounded-lg px-3 py-2 text-[13px] text-slate-600 transition-colors hover:bg-amber-50/80 hover:text-navy-900"
    >
      <span className="flex items-center gap-2.5">
        <span className="flex h-6 w-6 items-center justify-center rounded-full bg-gradient-to-b from-navy-600 to-navy-800 text-[10px] font-semibold text-white">A</span>
        Administrator
      </span>
      <span className="flex items-center gap-1.5 text-xs text-slate-500 group-hover:text-navy-800">Sign out <LogOut className="h-3.5 w-3.5" /></span>
    </button>
  );
}

// A slim amber line under the header while a saved action is in flight.
function MutationProgress() {
  const active = useIsMutating() > 0;
  return <div aria-hidden="true" className={cn("progress-indeterminate pointer-events-none absolute inset-x-0 -bottom-px transition-opacity duration-300", active ? "opacity-100" : "opacity-0")} />;
}

export default function Layout() {
  const { data: stats } = useStats();
  const updateSystem = useUpdateSystem();
  const loc = useLocation();
  const system = stats?.system;
  const current = NAV.find(n => (n.to === "/" ? loc.pathname === "/" : loc.pathname.startsWith(n.to)));
  const [menuOpen, setMenuOpen] = useState(false);
  useEffect(() => { setMenuOpen(false); }, [loc.pathname]);

  const setMode = (mode: string) =>
    updateSystem.mutate({ mode: mode as never }, { onSuccess: () => toast.success(`Operating mode → ${mode}`) });

  const togglePause = () =>
    updateSystem.mutate(
      { global_paused: !system?.global_paused },
      { onSuccess: () => toast(system?.global_paused ? "Activity resumed; existing publishing restrictions still apply" : "Activity paused globally") },
    );

  const killswitch = () =>
    updateSystem.mutate(
      { killswitch: !system?.killswitch },
      { onSuccess: () => toast(system?.killswitch ? "Stop released; existing publishing restrictions still apply" : "EMERGENCY STOP — all activity halted") },
    );

  // Publishing status, always in the header: the state first, then what it means for publishing.
  const status = system?.killswitch ? { label: "Stopped", short: "Stopped", detail: "All activity halted", tone: "border-rose-200 bg-rose-50 text-rose-800", dot: "bg-rose-600" }
    : system?.dry_run ? { label: "Local review", short: "Review", detail: "Publishing off", tone: "border-sky-200 bg-sky-50 text-sky-800", dot: "bg-sky-600" }
    : system?.global_paused ? { label: "Paused", short: "Paused", detail: "Publishing on hold", tone: "border-amber-300/80 bg-amber-50 text-amber-900", dot: "bg-amber-500" }
    : { label: "Service available", short: "Active",
        detail: !system ? "" : system.mode === "auto" ? (system.scheduler_enabled ? "Auto publishing" : "Auto · scheduler off") : system.mode === "review" ? "Review mode" : "Research mode",
        tone: "border-emerald-200 bg-emerald-50 text-emerald-800", dot: "bg-emerald-600 animate-soft-pulse" };

  return (
    <div className="min-h-screen text-foreground">
      <a href="#main" className="skip-link">Skip to content</a>
      <Toaster richColors position="bottom-right" />

      {/* Sidebar */}
      <aside className="sidebar-glass fixed inset-y-0 left-0 z-30 hidden w-64 flex-col border-r border-slate-200 lg:flex">
        <NavLink to="/" end aria-label="News Room Editorial Engine — Command Center" className="flex h-[76px] shrink-0 items-center px-5">
          <BrandLogo priority className="w-[204px]" />
        </NavLink>
        <PrimaryNav />
        <div className="space-y-3 p-3">
          <SitesPanel sites={stats?.sites ?? []} />
          <ModePanel system={system} setMode={setMode} />
          <AccountButton />
        </div>
      </aside>

      {/* Header */}
      <header className="glass fixed inset-x-0 top-0 z-40 flex h-16 items-center justify-between gap-2 border-b border-slate-200 px-3 sm:gap-3 sm:px-4 lg:left-64 lg:px-8">
        <div className="flex min-w-0 items-center gap-2 sm:gap-4">
          <Sheet open={menuOpen} onOpenChange={(open) => setMenuOpen(open)}>
            <SheetTrigger render={<Button variant="outline" size="icon" className="shrink-0 lg:hidden" aria-label="Open navigation" data-testid="mobile-nav-button" />}>
              <Menu className="h-4 w-4" />
            </SheetTrigger>
            <SheetContent side="left" className="sidebar-glass w-[19rem] max-w-[88vw] gap-0 p-0">
              <SheetHeader className="shrink-0 px-5 pb-1 pt-5">
                <SheetTitle className="sr-only">Navigation</SheetTitle>
                <SheetDescription className="sr-only">Sections of the News Room Editorial Engine, today’s output and the operating mode.</SheetDescription>
                <BrandLogo className="w-[196px]" />
              </SheetHeader>
              <PrimaryNav suffix="-mobile" />
              <div className="space-y-3 p-3">
                <SitesPanel sites={stats?.sites ?? []} />
                <ModePanel system={system} setMode={setMode} suffix="-mobile" />
                <AccountButton />
              </div>
            </SheetContent>
          </Sheet>
          <NavLink to="/" end aria-label="News Room Editorial Engine — Command Center" className="min-w-0 shrink lg:hidden">
            <BrandLogo priority className="w-[128px] sm:w-[156px]" />
          </NavLink>
          <nav aria-label="Breadcrumb" className="hidden min-w-0 items-center gap-2 text-sm lg:flex">
            <span className="text-slate-500">News Room</span>
            <span className="text-slate-400" aria-hidden="true">/</span>
            <span className="truncate font-semibold text-slate-900" aria-current="page">{current?.label ?? "Workspace"}</span>
          </nav>
          <span
            data-testid="system-status-bar"
            role="status"
            title={status.detail ? `${status.label} · ${status.detail}` : status.label}
            className={cn("inline-flex shrink-0 items-center gap-2 rounded-full border px-2 py-1 text-[11.5px] font-semibold tracking-wide sm:px-3", status.tone)}
          >
            <span className={cn("h-2 w-2 rounded-full", status.dot)} aria-hidden="true" />
            <span className="hidden sm:inline">{status.label}</span>
            <span className="sm:hidden" aria-hidden="true">{status.short}</span>
            <span className="sr-only sm:hidden">{status.label}</span>
            {status.detail && <span className="hidden font-medium opacity-80 md:inline">· {status.detail}</span>}
          </span>
        </div>
        <div className="flex shrink-0 items-center gap-1.5 sm:gap-2">
          <Clock />
          <Button
            data-testid="global-pause-button"
            variant="outline"
            size="sm"
            onClick={togglePause}
            aria-label={system?.global_paused ? "Resume activity" : "Pause activity"}
            className="gap-1.5"
          >
            {system?.global_paused ? <PlayCircle className="h-4 w-4" /> : <PauseCircle className="h-4 w-4" />}
            <span className="hidden sm:inline">{system?.global_paused ? "Resume" : "Pause"}</span>
          </Button>
          <Dialog>
            <DialogTrigger
              data-testid="emergency-stop-button"
              aria-label={system?.killswitch ? "Release emergency stop" : "Stop all activity"}
              className={cn(
                "inline-flex h-8 items-center gap-1.5 rounded-lg border px-2.5 text-[13px] font-medium transition-all duration-200 sm:px-3",
                system?.killswitch
                  ? "border-emerald-300 bg-emerald-50 text-emerald-800 hover:bg-emerald-100"
                  : "border-rose-200 bg-rose-50 text-rose-800 hover:border-rose-400 hover:bg-rose-100 hover:shadow-[0_0_20px_-6px_rgb(244_63_94/0.6)]",
              )}
            >
              <AlertOctagon className="h-4 w-4" />
              <span className="hidden sm:inline">{system?.killswitch ? "Release Stop" : "Stop All"}</span>
            </DialogTrigger>
            <DialogContent>
              <DialogHeader>
                <DialogTitle>{system?.killswitch ? "Release emergency stop?" : "Stop all activity?"}</DialogTitle>
                <DialogDescription>
                  {system?.killswitch
                    ? "This allows activity permitted by the current mode. Review-mode restrictions and individual site pauses still apply."
                    : "This blocks new discovery, AI and publishing work across both sites. Existing local data is retained."}
                </DialogDescription>
              </DialogHeader>
              <DialogFooter>
                <DialogClose render={<Button variant="outline" data-testid="killswitch-cancel">Cancel</Button>} />
                <DialogClose
                  render={
                    <Button
                      data-testid="killswitch-confirm"
                      variant={system?.killswitch ? "default" : "destructive"}
                      onClick={killswitch}
                    >
                      {system?.killswitch ? "Release" : "Confirm Emergency Stop"}
                    </Button>
                  }
                />
              </DialogFooter>
            </DialogContent>
          </Dialog>
        </div>
        <MutationProgress />
      </header>

      <main id="main" tabIndex={-1} className="px-4 pb-20 pt-24 outline-none sm:px-6 lg:pl-72 lg:pr-8" key={loc.pathname}>
        <div className="mx-auto max-w-[1600px] animate-in fade-in-0 slide-in-from-bottom-1 duration-300">
          {system?.dry_run && (
            <Notice tone="info" icon={<Info className="h-4 w-4" />}
              title={<>Local review <span className="font-normal opacity-75">· WordPress publishing and the automatic scheduler are disabled. Change the runtime configuration to enable live automation.</span></>} />
          )}
          {!system?.dry_run && system?.mode === "auto" && system?.scheduler_enabled && (
            <Notice tone="success" icon={<Activity className="h-4 w-4" />} title="Automatic service is active">
              Discovery, research, writing, images, scheduling, and publishing run on the configured timetable.
            </Notice>
          )}
          <AIAlerts />
          <SignOffAlerts />
          <Outlet />
        </div>
      </main>

      <div className="glass pointer-events-none fixed bottom-4 right-4 z-10 hidden items-center gap-1.5 rounded-full border border-slate-200 px-3 py-1 font-mono text-[10.5px] text-slate-600 shadow-[0_1px_2px_rgb(1_27_75/0.06)] lg:flex">
        <Activity className="h-3 w-3 text-amber-600" /> next run {stats?.next_run ? new Date(stats.next_run).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) : "—"}
      </div>
    </div>
  );
}
