// TS interfaces mirroring the backend Pydantic models — kept in sync by hand.

export interface SystemSettings {
  id: string;
  mode: "research_only" | "review" | "auto";
  global_paused: boolean;
  killswitch: boolean;
  scheduler_enabled: boolean;
  dry_run?: boolean;
  manual_ai_enabled?: boolean;
  repair_lock?: boolean;
  high_risk_review_required?: boolean;
  /** The next article's Deep Research may start while the current one is on its thumbnail (off by default). */
  research_ahead?: boolean;
  /** Off: the app starts no research itself; topics wait for their Manual Workbench report links. */
  auto_research?: boolean;
  updated_at: string;
}

export interface Site {
  key: "kannadiga" | "human";
  name: string;
  domain: string;
  language: "kn" | "en";
  audience: string;
  timezone: string;
  publish_times: string[];
  daily_quota: number;
  word_count_min: number;
  word_count_max: number;
  default_category: string;
  categories: string[];
  author: string;
  seo_plugin: string;
  brand_style: string;
  tone: string;
  alert_channel: string;
  auto_publish: boolean;
  paused: boolean;
  wp_base_url: string;
  wp_username: string;
  connected: boolean;
  connection_test: ConnectionTest | null;
  has_wp_password: boolean;
  connection_reason?: string;
}

export interface ConnectionCheck { name: string; passed: boolean; note?: string }
export interface ConnectionTest {
  passed: boolean;
  checks: ConnectionCheck[];
  simulated: boolean;
  message: string;
  tested_at: string;
}

export interface ScoreBreakdown {
  relevance?: number; impact?: number; trend?: number;
  freshness?: number; source?: number; seo?: number;
  /** Present when Gemini ranked the topic. */
  engagement?: number; ai_reason?: string;
}
export interface SourceRef {
  title: string; publisher?: string; author?: string; url: string; type?: string;
}
export interface Topic {
  id: string;
  site_key: string;
  topic: string;
  angle: string;
  why_trending: string;
  first_seen: string;
  last_seen: string;
  geography: string;
  category: string;
  reader_impact: string;
  sources: SourceRef[];
  source_confidence: string;
  focus_keyword: string;
  related_terms: string[];
  similarity: number;
  risk_flags: string[];
  score: number;
  score_breakdown: ScoreBreakdown;
  status: string;
  selection_reason: string;
  fingerprint: string;
  run_date: string;
}

export interface GateCheck { name: string; passed: boolean; note?: string }
export interface Validation { passed: boolean; checks: GateCheck[]; failed_reasons: string[] }

export interface Dossier {
  /** True when Deep Research wrote the article itself (report-as-article workflow). */
  report_mode?: boolean;
  executive_summary: string;
  verified_facts: string[];
  newest_development: string;
  timeline: { date: string; event: string }[];
  stakeholders: string[];
  human_impact: string;
  key_statistics: { metric: string; value: string; period?: string; source?: string }[];
  competing_claims: string[];
  unresolved_questions: string[];
  risk_review: { level: string; flags: string[]; explanation: string };
  recommended_angle: string;
  outline: string[];
  seo: { search_intent: string; focus_keyword: string; related_terms: string[] };
  claim_evidence: { claim: string; source_url: string; verified: boolean; note: string }[];
  sources: {
    title: string; publisher: string; author?: string; published?: string;
    url: string; type: string; reliability: string;
  }[];
  publication_ready: boolean;
  not_ready_reasons: string[];
}

export interface ArticleContent {
  headline: string;
  short_headline: string;
  thumbnail_headlines?: string[];
  dek: string;
  excerpt: string;
  content_html: string;
  key_takeaways: string[];
  focus_keyword: string;
  secondary_keywords: string[];
  seo_title: string;
  meta_description: string;
  slug: string;
  category: string;
  menu_categories?: { id: number; name: string }[];
  tags: string[];
  og_title: string;
  og_description: string;
  suggested_internal_links: string[];
  approved_external_sources: string[];
  featured_image_brief: string;
  featured_image_alt_text: string;
  featured_image_caption: string;
  schema_type: string;
  article_section: string;
  review_flags: string[];
}

export interface ImageData {
  data_uri?: string;
  has_image?: boolean;
  source: string;
  brief: string;
  filename: string;
  alt_text: string;
  caption: string;
  media_title: string;
  aspect_ratio: string;
  status: string;
}

export interface WpResult {
  simulated: boolean;
  post_id: number;
  status: string;
  edit_url: string;
  public_url: string;
  scheduled_time: string | null;
  author: string;
  category: string;
  tags: string[];
  featured_media_id: number;
  seo_persisted: boolean;
  seo_plugin: string;
  verification: Record<string, unknown>;
}

export interface HistoryEntry { stage: string; at: string; actor: string; note: string }

export interface Article {
  id: string;
  job_id: string;
  site_key: string;
  topic_id: string;
  topic_snapshot: Record<string, unknown> & { topic: string; category: string; risk_flags: string[] };
  stage: string;
  dossier: Dossier | null;
  dossier_meta: { model: string; prompt_version: number; provider?: string; status?: string; report?: string; formatting_model?: string; report_mode?: boolean } | null;
  validation: Validation | null;
  article: ArticleContent | null;
  article_meta: { model: string; prompt_version: number } | null;
  quality_gate: Validation | null;
  image: ImageData | null;
  approval?: { by: string; at: string } | null;
  wp: WpResult | null;
  review_flags: string[];
  held_reason: string | null;
  turn_wait?: { behind: string; since: string } | null;
  /** Its place in line: in production now, next (researching ahead), or waiting in the queue. */
  queue?: "current" | "next" | "queued" | null;
  /** 1 = the next article the app takes, 2 = the one after, ... */
  queue_position?: number | null;
  scheduled_time: string | null;
  history: HistoryEntry[];
  created_at: string;
  updated_at: string;
}

export interface SiteStat {
  key: string; name: string; domain: string; language: string; brand_style: string;
  daily_quota: number; published_today: number; scheduled: number; drafts: number;
  held_review: number; failed: number; in_progress: number; remaining: number;
  auto_publish: boolean; paused: boolean; connected: boolean;
  next_run: string | null; publish_times: string[]; timezone: string;
}
export interface Stats {
  system: SystemSettings;
  sites: SiteStat[];
  next_run: string | null;
  server_time: string;
  /** The single article currently in production (research -> SEO -> thumbnail -> WordPress). */
  producing?: { id: string; site_key: string; stage: string; held_reason?: string | null; since?: string; topic: string } | null;
  /** The next article: its research runs while the current one is on its thumbnail; it goes next. */
  next_article?: { id: string; site_key: string; stage: string; held_reason?: string | null; topic: string } | null;
  /** Site whose turn is next in the alternating sequence. */
  next_site?: "kannadiga" | "human";
}

export interface Prompt {
  id: string; key: string; name: string; template: string;
  version: number; versions: { version: number; template: string; at: string }[];
  updated_at: string;
}

export interface AuditEntry {
  id: string; at: string; actor: string; action: string;
  entity_type: string; entity_id: string | null; site_key: string | null;
  detail: unknown;
}

export interface PublishedPost {
  id: string; site_key: string; title: string; slug: string; date: string;
  wp_post_id: number | null; fingerprint: string; source: string; imported_at: string;
}
export interface ImportResult {
  count: number; simulated: boolean; lookback_days: number; posts: PublishedPost[];
}

export interface Health {
  wordpress: { key: string; name: string; domain: string; connected: boolean; last_test: boolean | null; mode: string }[];
  gemini: { configured: boolean; key_masked: string; research_model: string; writing_model: string; status: string; mode: string };
  image: { configured: boolean; key_masked: string; model: string; status: string; mode: string };
  emergent_used: boolean;
  checked_at: string;
}

export interface SecretsStatus {
  gemini_configured: boolean; gemini_key_masked: string;
  openai_configured: boolean; openai_key_masked: string;
  rankmath_configured: boolean; rankmath_key_masked: string;
  research_model: string; writing_model: string; image_model: string;
  research_provider: "gemini" | "openai"; writing_provider: "gemini" | "openai"; image_provider: "gemini" | "openai";
  research_key_configured: boolean; writing_key_configured: boolean; image_key_configured: boolean;
  provider: string; emergent_used: boolean;
}
export interface ProviderTest { ok: boolean; model: string; kind?: string; error?: string }
