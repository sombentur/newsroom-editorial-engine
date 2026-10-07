// TanStack Query hooks over the typed fetch layer.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiGet, apiPatch, apiPost, apiPut } from "@/lib/api";
import type {
  Article, AuditEntry, ConnectionTest, Health, ImportResult, Prompt, ProviderTest,
  PublishedPost, SecretsStatus, Site, Stats, SystemSettings, Topic,
} from "@/lib/types";

export function useStats() {
  return useQuery({ queryKey: ["stats"], queryFn: () => apiGet<Stats>("/stats"), refetchInterval: 15000 });
}
export function useSites() {
  return useQuery({ queryKey: ["sites"], queryFn: () => apiGet<Site[]>("/sites") });
}
export function useTopics(siteKey?: string) {
  return useQuery({
    queryKey: ["topics", siteKey ?? "all"],
    queryFn: () => apiGet<Topic[]>(`/topics${siteKey ? `?site_key=${siteKey}` : ""}`),
    refetchInterval: 10000,
  });
}
export function useArticles(siteKey?: string) {
  return useQuery({
    queryKey: ["articles", siteKey ?? "all"],
    queryFn: () => apiGet<Article[]>(`/articles${siteKey ? `?site_key=${siteKey}` : ""}`),
    refetchInterval: 10000,
  });
}
export function useArticle(id: string | null) {
  return useQuery({
    queryKey: ["article", id],
    queryFn: () => apiGet<Article>(`/articles/${id}`),
    enabled: !!id,
    refetchInterval: 5000,
  });
}
export function usePrompts() {
  return useQuery({ queryKey: ["prompts"], queryFn: () => apiGet<Prompt[]>("/prompts") });
}
export function useHealth() {
  return useQuery({ queryKey: ["health"], queryFn: () => apiGet<Health>("/health"), refetchInterval: 20000 });
}
export function useAudit(siteKey?: string) {
  return useQuery({
    queryKey: ["audit", siteKey ?? "all"],
    queryFn: () => apiGet<AuditEntry[]>(`/audit${siteKey ? `?site_key=${siteKey}` : ""}`),
    refetchInterval: 15000,
  });
}

export function useUpdateSystem() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: Partial<SystemSettings>) => apiPatch<SystemSettings>("/system", body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["stats"] });
      qc.invalidateQueries({ queryKey: ["system"] });
    },
  });
}

export function useUpdateSite() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ key, body }: { key: string; body: Record<string, unknown> }) =>
      apiPut<Site>(`/sites/${key}`, body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["sites"] });
      qc.invalidateQueries({ queryKey: ["stats"] });
    },
  });
}

export function useConnectionTest() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (key: string) => apiPost<ConnectionTest>(`/sites/${key}/connection-test`),
    onSettled: () => Promise.all(
      ["sites", "stats", "health", "audit"].map((key) => qc.invalidateQueries({ queryKey: [key] })),
    ),
  });
}

export function useDiscover() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (siteKey: string) => apiPost<{ count: number; rejected_duplicates: number; published_checked: number; queued?: number }>("/pipeline/discover", { site_key: siteKey }),
    onSuccess: () => Promise.all(["topics", "stats", "audit"].map((key) => qc.invalidateQueries({ queryKey: [key] }))),
  });
}

export function useImportPosts() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (siteKey: string) => apiPost<ImportResult>("/pipeline/import-posts", { site_key: siteKey }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["published"] });
      qc.invalidateQueries({ queryKey: ["audit"] });
    },
  });
}

export function usePublished(siteKey?: string) {
  return useQuery({
    queryKey: ["published", siteKey ?? "all"],
    queryFn: () => apiGet<PublishedPost[]>(`/published${siteKey ? `?site_key=${siteKey}` : ""}`),
  });
}

export function useSecrets() {
  return useQuery({ queryKey: ["secrets"], queryFn: () => apiGet<SecretsStatus>("/secrets") });
}
export function useUpdateSecrets() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: Record<string, string>) => apiPut<SecretsStatus>("/secrets", body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["secrets"] });
      qc.invalidateQueries({ queryKey: ["health"] });
    },
  });
}
export function useTestProvider() {
  return useMutation({
    mutationFn: (target: string) => apiPost<ProviderTest>(`/secrets/test/${target}`),
  });
}

// Generic article-action mutation; invalidates article, list, and stats.
export function useArticleAction() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ path, body }: { path: string; body?: unknown }) => apiPost<Article>(path, body),
    onSuccess: (art) => {
      qc.invalidateQueries({ queryKey: ["articles"] });
      qc.invalidateQueries({ queryKey: ["article", art?.id] });
      qc.invalidateQueries({ queryKey: ["stats"] });
      qc.invalidateQueries({ queryKey: ["topics"] });
      qc.invalidateQueries({ queryKey: ["audit"] });
    },
  });
}

export function useSelectTopic() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (topicId: string) => apiPost<Article>(`/topics/${topicId}/select`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["articles"] });
      qc.invalidateQueries({ queryKey: ["topics"] });
      qc.invalidateQueries({ queryKey: ["stats"] });
    },
  });
}

export function useUpdatePrompt() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ key, template }: { key: string; template: string }) =>
      apiPut<Prompt>(`/prompts/${key}`, { template }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["prompts"] }),
  });
}
