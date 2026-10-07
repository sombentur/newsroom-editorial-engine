import { Activity, CheckCircle2, Cpu, Download, Image as ImageIcon, Loader2, XCircle } from "lucide-react";
import { Card } from "@/components/ui/card";
import { useHealth, useSecrets } from "@/lib/hooks";
import { SectionLabel, SiteBadge, fmtTime } from "@/lib/ui";
import { cn } from "@/lib/utils";

function StatusPill({ ok, label }: { ok: boolean; label: string }) {
  return (
    <span className={cn("inline-flex shrink-0 items-center gap-1.5 whitespace-nowrap rounded-full border px-2.5 py-1 text-xs font-mono uppercase tracking-wider",
      ok ? "border-emerald-200 bg-emerald-50/60 text-emerald-700" : "border-slate-300 bg-slate-100/60 text-slate-600")}>
      {ok ? <CheckCircle2 className="h-3.5 w-3.5" /> : <XCircle className="h-3.5 w-3.5" />}{label.replace(/_/g, " ")}
    </span>
  );
}

function AiProviders() {
  const { data: sec } = useSecrets();
  return <Card className="border-slate-200 surface p-5">
    <SectionLabel>Direct AI provider configuration</SectionLabel>
    <p className="mt-3 text-sm text-slate-600">AI is optional for opening this app. Configure your own keys and model names locally in backend/.env when you are ready. Keys are never entered or stored in this browser.</p>
    <div className="mt-4 flex flex-wrap gap-3"><StatusPill ok={!!sec?.gemini_configured} label={sec?.gemini_configured ? "Gemini configured" : "Gemini not configured"} /><StatusPill ok={!!sec?.openai_configured} label={sec?.openai_configured ? "OpenAI configured" : "OpenAI not configured"} /><StatusPill ok={!!sec?.rankmath_configured} label={sec?.rankmath_configured ? "Rank Math configured" : "Rank Math not configured"} /></div>
    <p className="mt-3 text-xs text-slate-500">Configuration alone does not verify generation. Owner-enabled manual AI actions use API credits; scheduled execution and WordPress publishing stay locked.</p>
  </Card>;
}

export default function Health() {
  const { data, isLoading } = useHealth();

  if (isLoading || !data) return <div className="flex justify-center py-20"><Loader2 className="h-6 w-6 animate-spin text-slate-500" /></div>;

  return (
    <div className="space-y-5">
      <div>
        <SectionLabel>Integration Diagnostics</SectionLabel>
        <h1 className="page-title">Connection Health</h1>
        <p className="page-lede">Saved configuration and the latest verified connection state. No secrets are ever displayed here.</p>
      </div>

      <AiProviders />

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        <Card className="border-slate-200 surface p-5">
          <div className="mb-3 flex items-center gap-2"><Cpu className="h-4 w-4 text-indigo-600" /><SectionLabel>Gemini Research &amp; Writing</SectionLabel></div>
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="min-w-0">
              <div className="font-mono text-sm text-slate-800">research: {data.gemini.research_model}</div>
              <div className="font-mono text-sm text-slate-800">writing: {data.gemini.writing_model}</div>
              <div className="mt-1 text-xs text-slate-500">{data.gemini.mode}</div>
            </div>
            <StatusPill ok={data.gemini.status === "ready"} label={data.gemini.status} />
          </div>
        </Card>

        <Card className="border-slate-200 surface p-5">
          <div className="mb-3 flex items-center gap-2"><ImageIcon className="h-4 w-4 text-amber-600" /><SectionLabel>Featured Image Generation</SectionLabel></div>
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="min-w-0">
              <div className="font-mono text-sm text-slate-800">{data.image.model}</div>
              <div className="mt-1 text-xs text-slate-500">{data.image.mode}</div>
            </div>
            <StatusPill ok={data.image.status === "ready"} label={data.image.status} />
          </div>
        </Card>
      </div>

      <Card className="border-slate-200 surface p-5">
        <div className="mb-3 flex items-center gap-2"><Activity className="h-4 w-4 text-sky-600" /><SectionLabel>WordPress Endpoints</SectionLabel></div>
        <div className="space-y-3">
          {data.wordpress.map((w) => (
            <div key={w.key} className="flex items-center justify-between border-b border-slate-200 pb-3 last:border-0 last:pb-0">
              <div className="flex items-center gap-3">
                <SiteBadge siteKey={w.key} />
                <div>
                  <div className="font-heading text-sm font-medium text-slate-800">{w.name}</div>
                  <div className="font-mono text-xs text-slate-500">{w.domain} · {w.mode}</div>
                </div>
              </div>
              <StatusPill ok={w.connected} label={w.connected ? "connected" : "not connected"} />
            </div>
          ))}
        </div>
        <div className="mt-4 rounded border border-amber-100/50 bg-amber-50/30 p-3 text-xs text-amber-800/80">
          WordPress writes are disabled in local review. Saving credentials does not establish a connection or enable publishing. No simulated publication is created.
        </div>
      </Card>

      <Card className="border-slate-200 surface p-5">
        <SectionLabel>Companion SEO Plugin</SectionLabel>
        <p className="mt-2 max-w-2xl text-sm text-slate-600">
          SEO metadata support depends on each WordPress installation. Install this minimal, secure
          plugin (single file, capability-checked, fixed allow-list of SEO keys only) so the engine can persist and
          read back SEO fields. It never modifies WordPress core, themes, or other plugins.
        </p>
        <a
          href="/api/plugin/download"
          data-testid="plugin-download-link"
          className="mt-3 inline-flex items-center gap-2 rounded-md border border-sky-300 bg-sky-50/40 px-3 py-2 text-sm text-sky-800 transition-colors duration-150 hover:bg-sky-100/50"
        >
          <Download className="h-4 w-4" /> Download newsroom-seo-bridge.php
        </a>
        <ol className="mt-3 list-decimal space-y-1 pl-5 text-xs text-slate-500">
          <li>Upload the file to <span className="font-mono">wp-content/plugins/</span> and activate it in WP Admin → Plugins.</li>
          <li>Re-run the connection test in the Setup Wizard — <span className="font-mono">seo_field_support</span> should turn green.</li>
        </ol>
      </Card>
      <div className="text-right font-mono text-[11px] text-slate-400">last checked {fmtTime(data.checked_at)}</div>
    </div>
  );
}
