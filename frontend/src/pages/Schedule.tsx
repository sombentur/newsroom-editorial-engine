import { useState } from "react";
import { CalendarClock, Globe, Loader2, Send } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { apiPost } from "@/lib/api";
import { useArticles, useSites, useStats } from "@/lib/hooks";
import { useQueryClient } from "@tanstack/react-query";
import { EmptyState, fmtTime, SectionLabel, SiteBadge, StageBadge } from "@/lib/ui";
import type { Article } from "@/lib/types";
import { cn } from "@/lib/utils";

// Each site publishes in its own timezone: show that time beside the local one.
function siteTime(iso: string, timeZone: string): string {
  try { return new Date(iso).toLocaleTimeString(undefined, { timeZone, hour: "2-digit", minute: "2-digit" }); } catch { return ""; }
}

function Row({ a }: { a: Article }) {
  const qc = useQueryClient();
  const [when, setWhen] = useState("");
  const [busy, setBusy] = useState(false);
  const [publishing, setPublishing] = useState(false);
  const ready = !!a.article && !!a.image;
  const live = a.wp?.status === "publish";

  const publishNow = async () => {
    const site = a.site_key === "kannadiga" ? "the Kannada edition" : "the English edition";
    const waiting = a.stage === "scheduled" ? " It will not wait for its scheduled slot." : "";
    if (!window.confirm(`Publish “${a.article?.headline ?? a.topic_snapshot.topic}” on ${site} now?${waiting}`)) return;
    setPublishing(true);
    try {
      const result = await apiPost<Article>(`/articles/${a.id}/publish`, {});
      if (result.wp?.status === "publish" && result.stage === "verified") toast.success("Published — it is live now");
      else toast.info(result.held_reason ?? "Publishing held for review");
      qc.invalidateQueries({ queryKey: ["articles"] });
      qc.invalidateQueries({ queryKey: ["stats"] });
    } catch (e) { toast.error(e instanceof Error ? e.message : "Publish failed"); }
    finally { setPublishing(false); }
  };

  const schedule = async () => {
    if (!when) { toast.error("Pick a date & time"); return; }
    setBusy(true);
    try {
      const result = await apiPost<Article>(`/articles/${a.id}/schedule`, { scheduled_time: new Date(when).toISOString() });
      if (result.stage === "scheduled") toast.success("Scheduled");
      else toast.info(result.held_reason ?? "Scheduling held for review");
      qc.invalidateQueries({ queryKey: ["articles"] });
      qc.invalidateQueries({ queryKey: ["stats"] });
    } catch { toast.error("Schedule failed"); }
    finally { setBusy(false); }
  };

  return (
    <div className="flex flex-col gap-3 border-b border-slate-200 py-3 last:border-0 md:flex-row md:items-center md:justify-between">
      <div className="min-w-0 flex-1">
        <div className="mb-1 flex items-center gap-2">
          <SiteBadge siteKey={a.site_key} small />
          <StageBadge stage={a.stage} />
        </div>
        <div className={cn("truncate font-heading text-sm font-medium text-slate-800", a.site_key === "kannadiga" && "font-kannada")}>
          {a.article?.headline ?? a.topic_snapshot.topic}
        </div>
        {a.scheduled_time && <div className="font-mono text-[11px] text-sky-600">→ {fmtTime(a.scheduled_time)}{a.site_key === "human" && <span className="text-slate-500"> · {siteTime(a.scheduled_time, "America/New_York")} New York</span>}</div>}
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <Input
          type="datetime-local" value={when} onChange={(e) => setWhen(e.target.value)}
          data-testid={`schedule-input-${a.id}`} className="h-9 w-52 bg-slate-100 text-xs"
        />
        <Button size="sm" disabled={!ready || busy || publishing || live} onClick={schedule} data-testid={`schedule-set-${a.id}`} className="gap-1.5">
          {busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Send className="h-3.5 w-3.5" />} Schedule
        </Button>
        <Button size="sm" variant="outline" disabled={!ready || busy || publishing || live} onClick={publishNow} data-testid={`publish-now-${a.id}`} className="gap-1.5">
          {publishing ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Globe className="h-3.5 w-3.5" />} Publish now
        </Button>
      </div>
    </div>
  );
}

export default function Schedule() {
  const { data: articles, isLoading } = useArticles();
  const { data: sites } = useSites();
  const { data: stats } = useStats();

  const schedulable = (articles ?? []).filter((a) => ["image_ready", "article_validated", "wordpress_draft", "scheduled"].includes(a.stage));

  return (
    <div className="space-y-5">
      <div>
        <SectionLabel>Broadcast Schedule</SectionLabel>
        <h1 className="page-title">Publishing Timeline</h1>
        <p className="page-lede">Stagger the five daily slots per site — the engine never dumps a whole run at once.</p>
      </div>

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        {stats?.sites.map((s) => (
          <Card key={s.key} className="border-slate-200 surface p-4">
            <div className="mb-2 flex items-center gap-2"><SiteBadge siteKey={s.key} /><span className="font-mono text-xs text-slate-500">{s.timezone}</span></div>
            <div className="flex flex-wrap gap-1.5">
              {s.publish_times.map((t) => (
                <span key={t} className="inline-flex items-center gap-1 rounded border border-slate-300 bg-slate-100/60 px-2 py-1 font-mono text-xs text-slate-700">
                  <CalendarClock className="h-3 w-3 text-sky-600" /> {t}
                </span>
              ))}
            </div>
            <div className="mt-2 font-mono text-[11px] text-slate-500">
              {s.scheduled} scheduled · {s.remaining} slots remaining today
            </div>
          </Card>
        ))}
        {!sites && null}
      </div>

      <Card className="border-slate-200 surface p-4">
        <SectionLabel>Ready & scheduled articles</SectionLabel>
        <div className="mt-2">
          {isLoading ? (
            <div className="flex justify-center py-10"><Loader2 className="h-5 w-5 animate-spin text-slate-500" /></div>
          ) : schedulable.length === 0 ? (
            <EmptyState title="Nothing ready to schedule" hint="Generate an article and its featured image in the Editorial Workbench first." />
          ) : (
            schedulable.map((a) => <Row key={a.id} a={a} />)
          )}
        </div>
      </Card>
    </div>
  );
}
