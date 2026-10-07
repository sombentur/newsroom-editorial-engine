// Shared presentational bits and formatting helpers.
import type { ReactNode } from "react";
import { AlertTriangle, CalendarClock, CheckCircle2, XCircle } from "lucide-react";
import { cn } from "@/lib/utils";

export const STAGE_LABEL: Record<string, string> = {
  selected: "In Workbench",
  researching: "Started workflow · Researching",
  writing_article: "Writing Article",
  research_validated: "Research Validated",
  article_generated: "Article Generated",
  article_validated: "Article Validated",
  generating_image: "Image generation",
  image_ready: "Image attached",
  wordpress_draft: "WP Draft",
  scheduled: "Auto scheduled",
  published: "Published",
  verified: "Published & Verified",
  held_review: "Held for Review",
  rejected: "Rejected",
  failed: "Failed",
};

// Tone per stage: [chip classes, dot classes]. Publishing status must read at a glance and never by colour alone:
// in-progress work is the navy-blue info tint, scheduled is solid navy, published is green, held is amber, failed is
// rose; the end states also carry an icon. Violet and cyan are reserved for the two websites.
const INFO: [string, string] = ["border-sky-200 bg-sky-50 text-sky-800", "bg-sky-500"];
const STAGE_TONE: Record<string, [string, string]> = {
  held_review: ["border-amber-300/80 bg-amber-50 text-amber-900", "bg-amber-500"],
  rejected: ["border-slate-300 bg-slate-100/70 text-slate-600", "bg-slate-400"],
  failed: ["border-rose-200 bg-rose-50 text-rose-800", "bg-rose-600"],
  verified: ["border-emerald-200 bg-emerald-50 text-emerald-800", "bg-emerald-600"],
  published: ["border-emerald-200 bg-emerald-50 text-emerald-800", "bg-emerald-600"],
  scheduled: ["border-navy-200 bg-navy-100/80 text-navy-800", "bg-navy-600"],
  wordpress_draft: INFO,
  image_ready: INFO,
  article_validated: INFO,
  article_generated: INFO,
  research_validated: INFO,
  researching: ["border-sky-200 bg-white text-sky-800", "bg-navy-600"],
  writing_article: ["border-sky-200 bg-white text-sky-800", "bg-navy-600"],
  generating_image: ["border-sky-200 bg-white text-sky-800", "bg-navy-600"],
};
const STAGE_ICON: Record<string, typeof CheckCircle2> = {
  published: CheckCircle2, verified: CheckCircle2, scheduled: CalendarClock, held_review: AlertTriangle, failed: XCircle,
};
const ACTIVE_STAGES = new Set(["researching", "writing_article", "generating_image"]);

// A step that failed in the browser or at a provider: it needs a fix and Retry, not editorial approval ("Go ahead").
export const TECHNICAL_HOLD = /\bfailed \((?:browser|network|timeout|rate_limit|quota|auth|error|validation|safety)\)|work tab/i;

export function workflowStageLabel(stage: string, heldReason?: string | null): string {
  if (stage === "held_review") {
    if (heldReason && TECHNICAL_HOLD.test(heldReason)) return "Needs action";
    if (heldReason?.startsWith("High-risk subject requires human editorial sign-off")) return "Waiting for final human approval";
    if (heldReason?.toLowerCase().includes("research")) return "Research needs review";
    if (heldReason?.toLowerCase().includes("article")) return "Article needs review";
  }
  return STAGE_LABEL[stage] ?? stage;
}

const chip = "inline-flex max-w-full items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-left text-[11px] font-medium leading-4 tracking-wide";

export function StageBadge({ stage, heldReason }: { stage: string; heldReason?: string | null }) {
  const [tone, dot] = STAGE_TONE[stage] ?? ["border-slate-300 bg-white text-slate-700", "bg-slate-500"];
  const Icon = STAGE_ICON[stage];
  return (
    <span data-testid={`stage-badge-${stage}`} className={cn(chip, tone)}>
      {Icon
        ? <Icon className="h-3 w-3 shrink-0" aria-hidden="true" />
        : <span className={cn("h-1.5 w-1.5 shrink-0 rounded-full", dot, ACTIVE_STAGES.has(stage) && "animate-soft-pulse")} />}
      <span className="py-0.5">{workflowStageLabel(stage, heldReason)}</span>
    </span>
  );
}

// Site colours: the Kannada site violet, the English site cyan. Never red or amber: those mean danger / held.
export const SITE_META = {
  kannadiga: { name: "Kannada Edition", short: "Kannada", native: "ಕನ್ನಡ", language: "ಕನ್ನಡ · Kannada" },
  human: { name: "English Edition", short: "English", native: "English", language: "English" },
} as const;
export type SiteFilter = "all" | "kannadiga" | "human";

export function SiteBadge({ siteKey, small }: { siteKey: string; small?: boolean }) {
  const kn = siteKey === "kannadiga";
  return (
    <span
      className={cn(
        "inline-flex shrink-0 items-center gap-1.5 whitespace-nowrap rounded-full border font-medium",
        small ? "px-2 py-0 text-[10.5px] leading-5" : "px-2.5 py-0.5 text-[11px] leading-5",
        kn ? "border-violet-200 bg-violet-50 text-violet-900" : "border-cyan-200 bg-cyan-50 text-cyan-900",
      )}
    >
      <span className={cn("h-1.5 w-1.5 rounded-full", kn ? "bg-violet-600" : "bg-cyan-600")} />
      {kn ? <span className="font-kannada leading-none">ಕನ್ನಡ</span> : "English"}
    </span>
  );
}

// The website switch used on every screen that can be narrowed to one site. The chosen site fills with its own colour
// (violet / cyan; navy for all), so the selected website is unmistakable.
export function SiteSwitch({ value, onChange, testidPrefix, allLabel = "All sites", className }: {
  value: string; onChange: (key: SiteFilter) => void; testidPrefix?: string; allLabel?: string; className?: string;
}) {
  const options: { key: SiteFilter; label: string }[] = [
    { key: "all", label: allLabel }, { key: "kannadiga", label: "Kannada" }, { key: "human", label: "English" },
  ];
  return (
    <div role="group" aria-label="Website"
      className={cn("inline-flex max-w-full items-center gap-1 rounded-xl border border-slate-200 bg-white/75 p-1 shadow-[0_1px_2px_rgb(1_27_75/0.05)] backdrop-blur", className)}>
      {options.map((o) => {
        const selected = value === o.key;
        const kn = o.key === "kannadiga";
        return (
          <button
            key={o.key} type="button" aria-pressed={selected} onClick={() => onChange(o.key)}
            data-testid={testidPrefix ? `${testidPrefix}-${o.key}` : undefined}
            title={o.key === "all" ? "Both websites" : SITE_META[o.key].name}
            className={cn(
              "inline-flex h-8 min-w-0 items-center gap-2 rounded-lg px-3 text-[13px] font-medium transition-all duration-200",
              selected
                ? cn("text-white shadow-[0_6px_14px_-8px_rgb(1_27_75/0.6),inset_0_1px_0_rgb(255_255_255/0.18)]",
                    kn ? "bg-violet-600" : o.key === "human" ? "bg-cyan-700" : "bg-navy-800")
                : "text-slate-600 hover:bg-amber-50 hover:text-navy-900",
            )}
          >
            {o.key !== "all" && (
              <span className={cn("h-2 w-2 shrink-0 rounded-full", selected ? "bg-white" : kn ? "bg-violet-600" : "bg-cyan-600")} />
            )}
            <span className="truncate">{o.label}</span>
            {kn && <span className="hidden font-kannada text-[12px] leading-none opacity-80 sm:inline">ಕನ್ನಡ</span>}
          </button>
        );
      })}
    </div>
  );
}

export function RiskBadge({ flags }: { flags: string[] }) {
  if (!flags?.length) {
    return <span className={cn(chip, "shrink-0 whitespace-nowrap border-emerald-200/80 bg-emerald-50/60 text-emerald-800")}>Low risk</span>;
  }
  return (
    <span title={flags.join(", ")} className={cn(chip, "shrink-0 whitespace-nowrap border-rose-200 bg-rose-50 text-rose-800")}>
      High risk · {flags.length}
    </span>
  );
}

export function SectionLabel({ children }: { children: ReactNode }) {
  return (
    <div className="flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-600">
      <span className="h-0.5 w-4 shrink-0 rounded-full bg-gradient-to-r from-amber-500 to-amber-300/0" aria-hidden="true" />
      {children}
    </div>
  );
}

export function Metric({ label, value, accent }: { label: string; value: ReactNode; accent?: string }) {
  return (
    <div className="rounded-xl border border-slate-200 bg-gradient-to-b from-white to-slate-50/60 px-3.5 py-2.5 shadow-[0_1px_2px_rgb(1_27_75/0.04)]">
      <div className="truncate text-[10.5px] font-medium uppercase tracking-[0.12em] text-slate-500" title={label}>{label}</div>
      <div className={cn("mt-0.5 font-heading text-[26px] font-semibold tabular-nums leading-tight", accent ?? "text-slate-950")}>{value}</div>
    </div>
  );
}

export function EmptyState({ title, hint }: { title: string; hint?: string }) {
  return (
    <div className="flex flex-col items-center justify-center rounded-2xl border border-dashed border-slate-300 bg-white/40 px-6 py-16 text-center">
      <div className="mb-4 flex h-11 w-11 items-center justify-center rounded-full border border-amber-200 bg-amber-50 shadow-[0_0_0_6px_rgb(245_157_28/0.08)]" aria-hidden="true">
        <span className="h-2 w-2 rounded-full bg-amber-500" />
      </div>
      <div className="font-heading text-lg font-semibold text-slate-900">{title}</div>
      {hint && <div className="mt-1.5 max-w-md text-sm leading-relaxed text-slate-600">{hint}</div>}
    </div>
  );
}

export function fmtTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
  } catch {
    return iso;
  }
}
