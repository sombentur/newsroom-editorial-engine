import { useEffect, useState } from "react";
import { History, Loader2, RotateCcw, Save } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Textarea } from "@/components/ui/textarea";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { apiPost } from "@/lib/api";
import { useQueryClient } from "@tanstack/react-query";
import { usePrompts, useUpdatePrompt } from "@/lib/hooks";
import { SectionLabel, fmtTime } from "@/lib/ui";
import type { Prompt } from "@/lib/types";

function Editor({ prompt }: { prompt: Prompt }) {
  const [text, setText] = useState(prompt.template);
  const update = useUpdatePrompt();
  const qc = useQueryClient();
  useEffect(() => setText(prompt.template), [prompt.template]);

  const save = () =>
    update.mutate({ key: prompt.key, template: text }, { onSuccess: () => toast.success(`${prompt.name} saved · v${prompt.version + 1}`) });

  const restore = (v: number) =>
    apiPost(`/prompts/${prompt.key}/restore/${v}`).then(() => { qc.invalidateQueries({ queryKey: ["prompts"] }); toast(`Restored v${v}`); });

  return (
    <div className="grid grid-cols-1 gap-4 lg:grid-cols-12">
      <div className="lg:col-span-8">
        <div className="mb-2 flex items-center justify-between">
          <div className="font-mono text-xs text-slate-500">version {prompt.version} · updated {fmtTime(prompt.updated_at)}</div>
          <Button size="sm" onClick={save} disabled={update.isPending || text === prompt.template} data-testid={`prompt-save-${prompt.key}`} className="gap-1.5">
            {update.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Save className="h-3.5 w-3.5" />} Save Version
          </Button>
        </div>
        <Textarea
          value={text} onChange={(e) => setText(e.target.value)} data-testid={`prompt-editor-${prompt.key}`}
          className="writing-area min-h-[460px] font-mono text-[13px] text-slate-800"
        />
      </div>
      <div className="lg:col-span-4">
        <div className="mb-2 flex items-center gap-2"><History className="h-4 w-4 text-slate-600" /><SectionLabel>Version History</SectionLabel></div>
        <div className="space-y-2">
          {prompt.versions.length === 0 && <div className="text-xs text-slate-500">No previous versions yet.</div>}
          {[...prompt.versions].reverse().map((v) => (
            <div key={v.version} className="flex items-center justify-between rounded border border-slate-200 bg-slate-100/40 px-3 py-2">
              <div className="font-mono text-xs text-slate-600">v{v.version} · {fmtTime(v.at)}</div>
              <Button size="xs" variant="ghost" onClick={() => restore(v.version)} data-testid={`prompt-restore-${prompt.key}-${v.version}`} className="gap-1">
                <RotateCcw className="h-3 w-3" /> Restore
              </Button>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

export default function Prompts() {
  const { data: prompts, isLoading } = usePrompts();
  if (isLoading || !prompts) return <div className="flex justify-center py-20"><Loader2 className="h-6 w-6 animate-spin text-slate-500" /></div>;

  return (
    <div className="space-y-5">
      <div>
        <SectionLabel>Prompt Engineering Studio</SectionLabel>
        <h1 className="page-title">Editable Templates</h1>
        <p className="page-lede">Every research run records the model and prompt version used. Restore any prior version instantly.</p>
      </div>
      <Card className="border-slate-200 surface p-5">
        <Tabs defaultValue={prompts[0]?.key}>
          <TabsList className="h-auto flex-wrap">
            {prompts.filter((p) => p.key !== "image").map((p) => <TabsTrigger key={p.key} value={p.key} data-testid={`prompt-tab-${p.key}`}>{p.name}</TabsTrigger>)}
          </TabsList>
          {prompts.map((p) => (
            <TabsContent key={p.key} value={p.key} className="mt-4"><Editor prompt={p} /></TabsContent>
          ))}
        </Tabs>
      </Card>
    </div>
  );
}
