import BrowserBridge from "./BrowserBridge";
import { useEffect, useState } from "react";
import { BrainCircuit, CheckCircle2, Image, KeyRound, Loader2, Lock, PlugZap, Save, XCircle } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useConnectionTest, useSecrets, useSites, useUpdateSecrets, useUpdateSite } from "@/lib/hooks";
import { SectionLabel, SiteBadge } from "@/lib/ui";
import type { Site } from "@/lib/types";

const SEO_PLUGINS: Record<string, string> = { yoast: "Yoast SEO", rankmath: "Rank Math", aioseo: "All in One SEO", native: "Native metadata" };
const RESEARCH_MODELS: Record<string, { name: string; provider: "gemini" | "openai" }> = {
  "deep-research-preview-04-2026": { name: "Google Gemini Deep Research", provider: "gemini" },
  "deep-research-max-preview-04-2026": { name: "Google Gemini Deep Research Max", provider: "gemini" },
  "o4-mini-deep-research": { name: "OpenAI o4-mini Deep Research", provider: "openai" },
  "o3-deep-research": { name: "OpenAI o3 Deep Research", provider: "openai" },
};
const WRITING_MODELS: Record<string, { name: string; provider: "gemini" | "openai" }> = {
  "gemini-3.8-flash": { name: "Google Gemini 3.8 Flash", provider: "gemini" },
  "gemini-3.7-flash": { name: "Google Gemini 3.7 Flash", provider: "gemini" },
  "gemini-3.6-flash": { name: "Google Gemini 3.6 Flash", provider: "gemini" },
  "gemini-3.5-flash": { name: "Google Gemini 3.5 Flash", provider: "gemini" },
  "gpt-5.1": { name: "OpenAI GPT-5.1", provider: "openai" },
  "gpt-4.1": { name: "OpenAI GPT-4.1", provider: "openai" },
};
const IMAGE_MODELS: Record<string, { name: string; provider: "gemini" | "openai" }> = {
  "gpt-image-2.5-sunburst": { name: "OpenAI GPT Image 2.5 Sunburst — Best quality", provider: "openai" },
  "gpt-image-2.5-flare": { name: "OpenAI GPT Image 2.5 Flare — Fast", provider: "openai" },
  "gpt-image-2": { name: "OpenAI GPT Image 2 — Standard", provider: "openai" },
  "imagen-4.0-generate-001": { name: "Google Imagen 4", provider: "gemini" },
  "imagen-4.0-ultra-generate-001": { name: "Google Imagen 4 Ultra", provider: "gemini" },
};

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return <div className="space-y-1.5"><Label className="text-xs text-slate-600">{label}</Label>{children}</div>;
}

function SiteForm({ site }: { site: Site }) {
  const update = useUpdateSite();
  const test = useConnectionTest();
  const [f, setF] = useState({
    name: site.name, domain: site.domain,
    wp_base_url: site.wp_base_url, wp_username: site.wp_username, wp_app_password: "",
    author: site.author, timezone: site.timezone, seo_plugin: site.seo_plugin,
    word_count_min: site.word_count_min, word_count_max: site.word_count_max,
    publish_times: site.publish_times.join(", "), categories: site.categories.join(", "),
    alert_channel: site.alert_channel,
  });
  useEffect(() => {
    setF((p) => ({ ...p, name: site.name, domain: site.domain, wp_base_url: site.wp_base_url, wp_username: site.wp_username, author: site.author,
      timezone: site.timezone, seo_plugin: site.seo_plugin, word_count_min: site.word_count_min,
      word_count_max: site.word_count_max, publish_times: site.publish_times.join(", "),
      categories: site.categories.join(", "), alert_channel: site.alert_channel }));
  }, [site]);

  const set = (k: string, v: unknown) => setF((p) => ({ ...p, [k]: v }));

  const save = () => {
    const body: Record<string, unknown> = {
      name: f.name, domain: f.domain,
      wp_base_url: f.wp_base_url, wp_username: f.wp_username, author: f.author, timezone: f.timezone,
      seo_plugin: f.seo_plugin, word_count_min: Number(f.word_count_min), word_count_max: Number(f.word_count_max),
      publish_times: f.publish_times.split(",").map((s) => s.trim()).filter(Boolean),
      categories: f.categories.split(",").map((s) => s.trim()).filter(Boolean),
      alert_channel: f.alert_channel,
    };
    if (f.wp_app_password) body.wp_app_password = f.wp_app_password;
    update.mutate({ key: site.key, body }, {
      onSuccess: () => { toast.success(`${site.name} settings saved`); set("wp_app_password", ""); },
      onError: (error) => toast.error(error.message),
    });
  };

  const runTest = () => {
    if (f.wp_base_url !== site.wp_base_url || f.wp_username !== site.wp_username ||
        f.author !== site.author || f.wp_app_password.trim()) {
      toast.error("Save your WordPress settings before testing the connection.");
      return;
    }
    if (!site.wp_base_url || !site.wp_username || !site.has_wp_password) {
      toast.error("Save a WordPress base URL, username and Application Password first.");
      return;
    }
    if (!window.confirm(`Test the saved connection to ${site.wp_base_url}? This sends authenticated read-only requests. Publishing and uploads remain disabled.`)) return;
    test.mutate(site.key, {
      onSuccess: (r) => r.passed ? toast.success("Authenticated read-only connection passed") : toast.error(r.message),
      onError: (error) => toast.error(error.message),
    });
  };

  const ct = site.connection_test;

  return (
    <div className="grid grid-cols-1 gap-6 lg:grid-cols-12">
      <div className="space-y-4 lg:col-span-7">
        <Card className="border-slate-200 bg-slate-100/40 p-4">
          <div className="mb-3 flex items-center gap-2"><Lock className="h-4 w-4 text-amber-600" /><SectionLabel>WordPress (Application Password)</SectionLabel></div>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <Field label="Website name"><Input value={f.name} onChange={(e) => set("name", e.target.value)} placeholder="My News Site" data-testid={`site-name-${site.key}`} className="bg-slate-50/60" /></Field>
            <Field label="Domain"><Input value={f.domain} onChange={(e) => set("domain", e.target.value)} placeholder="news.example.com" data-testid={`site-domain-${site.key}`} className="bg-slate-50/60" /></Field>
            <Field label="WordPress Base URL"><Input value={f.wp_base_url} onChange={(e) => set("wp_base_url", e.target.value)} placeholder={`https://${site.domain}`} data-testid={`wp-url-${site.key}`} className="bg-slate-50/60" /></Field>
            <Field label="WP Username"><Input value={f.wp_username} onChange={(e) => set("wp_username", e.target.value)} placeholder="editorial-bot" data-testid={`wp-user-${site.key}`} className="bg-slate-50/60" /></Field>
            <Field label={`Application Password ${site.has_wp_password ? "(saved — leave blank to keep)" : ""}`}>
              <Input type="password" value={f.wp_app_password} onChange={(e) => set("wp_app_password", e.target.value)} placeholder="xxxx xxxx xxxx xxxx" data-testid={`wp-pass-${site.key}`} className="bg-slate-50/60" />
            </Field>
            <Field label="Author"><Input value={f.author} onChange={(e) => set("author", e.target.value)} data-testid={`wp-author-${site.key}`} className="bg-slate-50/60" /></Field>
          </div>
          <p className="mt-2 text-[11px] text-slate-500">Use a dedicated least-privilege user + Application Password. Your main WordPress login password is never requested or stored.</p>
        </Card>

        <Card className="border-slate-200 bg-slate-100/40 p-4">
          <div className="mb-3 flex items-center gap-2"><SectionLabel>Editorial & Publishing</SectionLabel></div>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <Field label="SEO Plugin">
              <Select value={f.seo_plugin} onValueChange={(v) => set("seo_plugin", v)}>
                <SelectTrigger data-testid={`seo-plugin-${site.key}`} className="bg-slate-50/60"><SelectValue>{(v) => SEO_PLUGINS[v as string] ?? "Select"}</SelectValue></SelectTrigger>
                <SelectContent>{Object.entries(SEO_PLUGINS).map(([k, v]) => <SelectItem key={k} value={k}>{v}</SelectItem>)}</SelectContent>
              </Select>
            </Field>
            <Field label="Time Zone"><Input value={f.timezone} onChange={(e) => set("timezone", e.target.value)} data-testid={`tz-${site.key}`} className="bg-slate-50/60" /></Field>
            <Field label="Word Count Min"><Input type="number" value={f.word_count_min} onChange={(e) => set("word_count_min", e.target.value)} className="bg-slate-50/60" /></Field>
            <Field label="Word Count Max"><Input type="number" value={f.word_count_max} onChange={(e) => set("word_count_max", e.target.value)} className="bg-slate-50/60" /></Field>
            <div className="sm:col-span-2"><Field label="5 Publishing Times (comma-separated, 24h)"><Input value={f.publish_times} onChange={(e) => set("publish_times", e.target.value)} data-testid={`times-${site.key}`} className="bg-slate-50/60 font-mono" /></Field></div>
            <div className="sm:col-span-2"><Field label="Permitted Categories (comma-separated)"><Input value={f.categories} onChange={(e) => set("categories", e.target.value)} className="bg-slate-50/60" /></Field></div>
            <div className="sm:col-span-2"><Field label="Failure / Review Alert Channel (email or Slack webhook)"><Input value={f.alert_channel} onChange={(e) => set("alert_channel", e.target.value)} placeholder="optional" className="bg-slate-50/60" /></Field></div>
          </div>
        </Card>

        <div className="flex gap-2">
          <Button onClick={save} disabled={update.isPending || test.isPending} data-testid={`save-settings-button-${site.key}`} className="gap-1.5">
            {update.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />} Save Settings
          </Button>
          <Button variant="outline" onClick={runTest} disabled={test.isPending || update.isPending} data-testid={`wp-connection-test-button-${site.key}`} className="gap-1.5">
            {test.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <PlugZap className="h-4 w-4" />} Test Connection
          </Button>
        </div>
      </div>

      <div className="lg:col-span-5">
        <Card className="border-slate-200 bg-slate-100/40 p-4">
          <SectionLabel>Read-only Connection Test</SectionLabel>
          <p className="mt-2 text-xs text-slate-500">Checks the saved account and REST access. Write and upload permissions are reported by WordPress; no content is created.</p>
          <div className="mt-3 space-y-2">
            {!ct && <p className="text-xs text-slate-600">No connection test yet. Save your settings, then select Test Connection.</p>}
            {ct?.checks.map((c) => (
              <div key={c.name} className="flex items-center justify-between rounded border border-slate-200 bg-slate-50/40 px-3 py-1.5">
                <div className="pr-2"><span className="font-mono text-xs text-slate-600">{c.name}</span>
                  {c.note && <p className="mt-1 text-[11px] text-slate-500">{c.note}</p>}
                </div>
                {c.passed ? <CheckCircle2 className="h-4 w-4 shrink-0 text-emerald-600" /> : <XCircle className="h-4 w-4 shrink-0 text-slate-400" />}
              </div>
            ))}
          </div>
          {ct && <div className="mt-3 rounded border border-slate-200 bg-slate-50/40 p-2 text-[11px] text-slate-600">{ct.message}</div>}
        </Card>
      </div>
    </div>
  );
}

function AIProvidersForm() {
  const { data, isLoading } = useSecrets();
  const update = useUpdateSecrets();
  const [researchModel, setResearchModel] = useState("deep-research-preview-04-2026");
  const [writingModel, setWritingModel] = useState("gemini-3.8-flash");
  const [imageModel, setImageModel] = useState("gpt-image-2.5-sunburst");
  const [geminiKey, setGeminiKey] = useState("");
  const [writingKey, setWritingKey] = useState("");
  const [openaiKey, setOpenaiKey] = useState("");
  const [rankMathKey, setRankMathKey] = useState("");

  useEffect(() => {
    if (data?.research_model && RESEARCH_MODELS[data.research_model]) setResearchModel(data.research_model);
    if (data?.writing_model && WRITING_MODELS[data.writing_model]) setWritingModel(data.writing_model);
    if (data?.image_model && IMAGE_MODELS[data.image_model]) setImageModel(data.image_model);
  }, [data]);

  const saveResearch = () => {
    const option = RESEARCH_MODELS[researchModel];
    const body: Record<string, string> = { research_provider: option.provider, model_research: researchModel };
    if (geminiKey.trim()) body[`${option.provider}_api_key`] = geminiKey.trim();
    update.mutate(body, {
      onSuccess: () => { setGeminiKey(""); toast.success("Research AI settings saved"); },
      onError: (error) => toast.error(error.message),
    });
  };
  const saveWriting = () => {
    const option = WRITING_MODELS[writingModel];
    const body: Record<string, string> = { writing_provider: option.provider, model_writing: writingModel };
    if (writingKey.trim()) body[`${option.provider}_api_key`] = writingKey.trim();
    update.mutate(body, {
      onSuccess: () => { setWritingKey(""); toast.success("Writing AI settings saved"); },
      onError: (error) => toast.error(error.message),
    });
  };
  const saveImage = () => {
    const option = IMAGE_MODELS[imageModel];
    const body: Record<string, string> = { image_provider: option.provider, model_image: imageModel };
    if (openaiKey.trim()) body[`${option.provider}_api_key`] = openaiKey.trim();
    update.mutate(body, {
      onSuccess: () => { setOpenaiKey(""); toast.success("Image generation settings saved"); },
      onError: (error) => toast.error(error.message),
    });
  };
  const saveRankMath = () => {
    if (!rankMathKey.trim()) {
      toast.error("Paste the Rank Math API key before saving.");
      return;
    }
    update.mutate({ rankmath_api_key: rankMathKey.trim() }, {
      onSuccess: () => { setRankMathKey(""); toast.success("Rank Math SEO key saved"); },
      onError: (error) => toast.error(error.message),
    });
  };

  if (isLoading || !data) return <div className="flex justify-center py-16"><Loader2 className="h-6 w-6 animate-spin text-slate-500" /></div>;
  return (
    <div className="grid grid-cols-1 gap-5 lg:grid-cols-2" data-testid="ai-providers-settings">
      <Card className="border-slate-200 bg-slate-100/40 p-5">
        <div className="mb-4 flex items-start justify-between gap-3">
          <div><div className="flex items-center gap-2"><BrainCircuit className="h-4 w-4 text-cyan-600" /><SectionLabel>Research</SectionLabel></div><p className="mt-2 text-xs text-slate-500">Choose a Google or OpenAI research agent.</p></div>
          <span className={`rounded border px-2 py-1 text-[10px] font-semibold uppercase ${data.research_key_configured ? "border-emerald-200 bg-emerald-50 text-emerald-800" : "border-amber-300/80 bg-amber-50 text-amber-900"}`}>{data.research_key_configured ? "Configured" : "Not configured"}</span>
        </div>
        <div className="space-y-4">
          <Field label="AI Module"><Select value={researchModel} onValueChange={setResearchModel}><SelectTrigger data-testid="research-ai-module" className="bg-slate-50/60"><SelectValue>{(value) => RESEARCH_MODELS[value as string]?.name ?? "Select"}</SelectValue></SelectTrigger><SelectContent>{Object.entries(RESEARCH_MODELS).map(([id, option]) => <SelectItem key={id} value={id}>{option.name}</SelectItem>)}</SelectContent></Select></Field>
          <Field label={`API Key ${data.research_key_configured ? "(saved — leave blank to keep)" : ""}`}><Input type="password" autoComplete="new-password" value={geminiKey} onChange={(e) => setGeminiKey(e.target.value)} placeholder={`Paste ${RESEARCH_MODELS[researchModel].provider === "gemini" ? "Google Gemini" : "OpenAI"} API key`} data-testid="research-api-key" className="bg-slate-50/60" /></Field>
          <Button onClick={saveResearch} disabled={update.isPending} data-testid="save-research-ai" className="gap-1.5">{update.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />} Save Research AI</Button>
        </div>
      </Card>
      <Card className="border-slate-200 bg-slate-100/40 p-5">
        <div className="mb-4 flex items-start justify-between gap-3">
          <div><div className="flex items-center gap-2"><BrainCircuit className="h-4 w-4 text-emerald-600" /><SectionLabel>Writing & Kannada Audit</SectionLabel></div><p className="mt-2 text-xs text-slate-500">Formats saved research, writes articles, and reviews Kannada language and source consistency.</p></div>
          <span className={`rounded border px-2 py-1 text-[10px] font-semibold uppercase ${data.writing_key_configured ? "border-emerald-200 bg-emerald-50 text-emerald-800" : "border-amber-300/80 bg-amber-50 text-amber-900"}`}>{data.writing_key_configured ? "Configured" : "Not configured"}</span>
        </div>
        <div className="space-y-4">
          <Field label="AI Module"><Select value={writingModel} onValueChange={setWritingModel}><SelectTrigger data-testid="writing-ai-module" className="bg-slate-50/60"><SelectValue>{(value) => WRITING_MODELS[value as string]?.name ?? "Select"}</SelectValue></SelectTrigger><SelectContent>{Object.entries(WRITING_MODELS).map(([id, option]) => <SelectItem key={id} value={id}>{option.name}</SelectItem>)}</SelectContent></Select></Field>
          <Field label={`API Key ${data.writing_key_configured ? "(saved — leave blank to keep)" : ""}`}><Input type="password" autoComplete="new-password" value={writingKey} onChange={(e) => setWritingKey(e.target.value)} placeholder={`Paste ${WRITING_MODELS[writingModel].provider === "gemini" ? "Google Gemini" : "OpenAI"} API key`} data-testid="writing-api-key" className="bg-slate-50/60" /></Field>
          <Button onClick={saveWriting} disabled={update.isPending} data-testid="save-writing-ai" className="gap-1.5">{update.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />} Save Writing AI</Button>
        </div>
      </Card>
      <Card className="border-slate-200 bg-slate-100/40 p-5">
        <div className="mb-4 flex items-start justify-between gap-3">
          <div><div className="flex items-center gap-2"><Image className="h-4 w-4 text-violet-600" /><SectionLabel>Image Generation</SectionLabel></div><p className="mt-2 text-xs text-slate-500">Choose an OpenAI or Google image model.</p></div>
          <span className={`rounded border px-2 py-1 text-[10px] font-semibold uppercase ${data.image_key_configured ? "border-emerald-200 bg-emerald-50 text-emerald-800" : "border-amber-300/80 bg-amber-50 text-amber-900"}`}>{data.image_key_configured ? "Configured" : "Not configured"}</span>
        </div>
        <div className="space-y-4">
          <Field label="AI Module"><Select value={imageModel} onValueChange={setImageModel}><SelectTrigger data-testid="image-ai-module" className="bg-slate-50/60"><SelectValue>{(value) => IMAGE_MODELS[value as string]?.name ?? "Select"}</SelectValue></SelectTrigger><SelectContent>{Object.entries(IMAGE_MODELS).map(([id, option]) => <SelectItem key={id} value={id}>{option.name}</SelectItem>)}</SelectContent></Select></Field>
          <Field label={`API Key ${data.image_key_configured ? "(saved — leave blank to keep)" : ""}`}><Input type="password" autoComplete="new-password" value={openaiKey} onChange={(e) => setOpenaiKey(e.target.value)} placeholder={`Paste ${IMAGE_MODELS[imageModel].provider === "gemini" ? "Google Gemini" : "OpenAI"} API key`} data-testid="image-api-key" className="bg-slate-50/60" /></Field>
          <Button onClick={saveImage} disabled={update.isPending} data-testid="save-image-ai" className="gap-1.5">{update.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />} Save Image AI</Button>
        </div>
      </Card>
      <Card className="border-slate-200 bg-slate-100/40 p-5 lg:col-span-2">
        <div className="mb-4 flex items-start justify-between gap-3">
          <div><div className="flex items-center gap-2"><KeyRound className="h-4 w-4 text-emerald-600" /><SectionLabel>Rank Math SEO</SectionLabel></div><p className="mt-2 text-xs text-slate-500">Account API access for Rank Math SEO and Content AI features.</p></div>
          <span className={`rounded border px-2 py-1 text-[10px] font-semibold uppercase ${data.rankmath_configured ? "border-emerald-200 bg-emerald-50 text-emerald-800" : "border-amber-300/80 bg-amber-50 text-amber-900"}`}>{data.rankmath_key_masked}</span>
        </div>
        <div className="grid grid-cols-1 items-end gap-4 md:grid-cols-[1fr_auto]">
          <Field label={`Rank Math API Key ${data.rankmath_configured ? "(saved — leave unchanged to keep)" : ""}`}><Input type="password" autoComplete="new-password" value={rankMathKey} onChange={(e) => setRankMathKey(e.target.value)} placeholder="Paste Rank Math API key" data-testid="rankmath-api-key" className="bg-slate-50/60" /></Field>
          <Button onClick={saveRankMath} disabled={update.isPending} data-testid="save-rankmath-key" className="gap-1.5">{update.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />} Save Rank Math Key</Button>
        </div>
      </Card>
      <div className="flex items-start gap-2 rounded border border-slate-200 bg-slate-50/40 p-3 text-xs text-slate-600 lg:col-span-2"><KeyRound className="mt-0.5 h-4 w-4 shrink-0 text-slate-500" /><span>API keys stay in the local server configuration. The app only shows whether each key is configured and never sends a saved key back to the browser.</span></div>
    </div>
  );
}

export default function Wizard() {
  const { data: sites, isLoading } = useSites();
  if (isLoading || !sites) return <div className="flex justify-center py-20"><Loader2 className="h-6 w-6 animate-spin text-slate-500" /></div>;

  return (
    <div className="space-y-5">
      <div>
        <SectionLabel>Deployment Setup Wizard</SectionLabel>
        <h1 className="page-title">Configure Sites & Integrations</h1>
        <p className="page-lede">Manage WordPress connections and the AI providers used for research, writing and thumbnails.</p>
      </div>
      <Card className="border-slate-200 surface p-5" data-testid="setup-wizard-flow">
        <Tabs defaultValue={new URLSearchParams(window.location.search).get("tab") === "ai" ? "ai" : sites[0]?.key}>
          <TabsList>
            {sites.map((s) => <TabsTrigger key={s.key} value={s.key} data-testid={`wizard-tab-${s.key}`}><span className="flex items-center gap-2"><SiteBadge siteKey={s.key} small /> {s.name}</span></TabsTrigger>)}
            <TabsTrigger value="browser">Browser Extension</TabsTrigger>
            <TabsTrigger value="ai" data-testid="wizard-tab-ai"><span className="flex items-center gap-2"><BrainCircuit className="h-4 w-4" /> AI Providers</span></TabsTrigger>
          </TabsList>
          {sites.map((s) => <TabsContent key={s.key} value={s.key} className="mt-4"><SiteForm site={s} /></TabsContent>)}
          <TabsContent value="browser" className="mt-4"><BrowserBridge /></TabsContent>
          <TabsContent value="ai" className="mt-4"><AIProvidersForm /></TabsContent>
        </Tabs>
      </Card>
    </div>
  );
}
