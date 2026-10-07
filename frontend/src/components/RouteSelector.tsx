// Generation route: Chrome Bridge (owner's Gemini/ChatGPT subscriptions) or paid API keys.
import { useMutation, useQuery } from "@tanstack/react-query";
import { toast } from "sonner";
import { Chrome, KeyRound, Loader2 } from "lucide-react";
import { apiGet, apiPut } from "@/lib/api";
import { queryClient } from "@/lib/queryClient";
import { SectionLabel } from "@/lib/ui";
import { cn } from "@/lib/utils";

export type BridgeJob = { id: string; article_id: string; kind: string; status: string; message: string };
export type BridgeStatus = {
  research: boolean; image: boolean; paired: boolean; version?: string; latest_version?: string; last_seen: string | null;
  workspace?: Record<string, { attached: boolean; ready: boolean; message: string }>; workspace_seen?: string;
  jobs: BridgeJob[];
};

export const EXTENSION_VERSION = "0.4.26";

export function useBridgeStatus() {
  return useQuery({ queryKey: ["browser-status"], queryFn: () => apiGet<BridgeStatus>("/browser/status"), refetchInterval: 5000 });
}

const STEPS = [
  { key: "research" as const, title: "Deep Research article",
    chrome: { name: "Chrome Bridge", detail: "Gemini Pro · Deep Research in your signed-in tab", cost: "Included in your Gemini subscription" },
    api: { name: "API keys", detail: "Gemini Deep Research API", cost: "Billed to your Gemini API credits" } },
  { key: "image" as const, title: "SEO assets & thumbnail",
    chrome: { name: "Chrome Bridge", detail: "ChatGPT writes SEO + generates the thumbnail", cost: "Included in your ChatGPT subscription" },
    api: { name: "API keys", detail: "Gemini SEO + OpenAI Images", cost: "Billed to your API credits" } },
];

export default function RouteSelector({ compact }: { compact?: boolean }) {
  const { data } = useBridgeStatus();
  const save = useMutation({
    mutationFn: (body: { research: boolean; image: boolean }) => apiPut("/browser/settings", body),
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ["browser-status"] }); toast.success("Generation route saved"); },
    onError: (e: Error) => toast.error(e.message),
  });
  const connected = !!data?.last_seen && Date.now() - new Date(data.last_seen).getTime() < 90000;
  const lane = (kinds: string[]) => data?.jobs.find(j => kinds.includes(j.kind) && ["running", "attention"].includes(j.status));

  return (
    <div className="surface rounded-2xl border border-slate-200 p-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <SectionLabel>Generation route</SectionLabel>
        <span className={cn("inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-[11px] font-medium",
          connected ? "border-emerald-200 bg-emerald-50 text-emerald-700" : "border-amber-200 bg-amber-50 text-amber-700")}>
          <span className={cn("h-1.5 w-1.5 rounded-full", connected ? "bg-emerald-500 animate-soft-pulse" : "bg-amber-500")} />
          {connected ? `Chrome extension connected · v${data?.version ?? "?"}` : "Chrome extension offline"}
        </span>
      </div>
      {!compact && <p className="mt-2 text-sm text-slate-600">Choose how each step runs. Both routes follow the same workflow: Deep Research writes the article, then SEO assets and a thumbnail are prepared for WordPress.</p>}
      {connected && data?.version && data.version !== (data.latest_version ?? EXTENSION_VERSION) && (
        <p className="mt-3 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-800">
          Chrome is running an older extension (v{data?.version}). Restart the app with Start Local.cmd — it updates the extension, which reloads itself. If this notice stays, click reload once on Newsroom Browser Bridge in <strong>chrome://extensions</strong>.
        </p>
      )}
      <div className="mt-4 space-y-3">
        {STEPS.map(step => {
          const viaChrome = !!data?.[step.key];
          const active = lane(step.key === "research" ? ["research"] : ["image", "seo"]);
          return (
            <div key={step.key} className="rounded-xl border border-slate-200 bg-slate-50/70 p-3">
              <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
                <div className="text-[13px] font-medium text-slate-900">{step.title}</div>
                {active && viaChrome && (
                  <span className="max-w-[60%] truncate text-xs text-slate-500" title={active.message}>
                    {active.status === "attention" ? "Needs attention · " : "Working · "}{active.message}
                  </span>
                )}
              </div>
              <div className="grid gap-2 sm:grid-cols-2">
                {([["chrome", true], ["api", false]] as const).map(([route, chrome]) => {
                  const option = step[route];
                  const selected = viaChrome === chrome;
                  const disabled = save.isPending || (chrome && !data?.paired);
                  return (
                    <button
                      key={route}
                      type="button"
                      disabled={disabled || selected}
                      data-testid={`route-${step.key}-${route}`}
                      onClick={() => data && save.mutate({ research: data.research, image: data.image, [step.key]: chrome })}
                      className={cn(
                        "flex items-start gap-3 rounded-lg border px-3 py-2.5 text-left transition-all",
                        selected ? "border-navy-700 bg-white shadow-[0_0_0_3px_rgb(245_157_28/0.3)]" : "border-slate-200 bg-white/60 hover:border-amber-400 hover:bg-white",
                        disabled && !selected && "cursor-not-allowed opacity-50",
                      )}
                    >
                      <span className={cn("mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-md",
                        selected ? "bg-gradient-to-b from-navy-700 to-navy-800 text-white" : "bg-slate-100 text-slate-500")}>
                        {save.isPending && !selected ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : chrome ? <Chrome className="h-3.5 w-3.5" /> : <KeyRound className="h-3.5 w-3.5" />}
                      </span>
                      <span className="min-w-0">
                        <span className="block text-[13px] font-medium text-slate-900">{option.name}</span>
                        <span className="block text-xs text-slate-600">{option.detail}</span>
                        <span className={cn("mt-0.5 block text-[11px]", chrome ? "text-emerald-700" : "text-amber-700")}>{option.cost}</span>
                      </span>
                    </button>
                  );
                })}
              </div>
            </div>
          );
        })}
      </div>
      {!data?.paired && <p className="mt-3 text-xs text-slate-500">Chrome Bridge becomes available once the Newsroom Browser Bridge extension connects.</p>}
    </div>
  );
}
