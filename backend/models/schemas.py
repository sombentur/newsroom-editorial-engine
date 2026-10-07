"""Pydantic v2 request/response models. Mirror these in frontend/src/lib/types.ts."""

from typing import Any, Literal
from datetime import datetime

from pydantic import BaseModel, Field, SecretStr


class SystemUpdate(BaseModel):
    mode: Literal["research_only", "review", "auto"] | None = None
    global_paused: bool | None = None
    killswitch: bool | None = None
    scheduler_enabled: bool | None = None
    auto_research: bool | None = None  # off: topics wait for manual research links (owner request, 28 Sep 2026)


class SiteUpdate(BaseModel):
    name: str | None = None
    domain: str | None = None
    audience: str | None = None
    timezone: str | None = None
    publish_times: list[str] | None = None
    daily_quota: int | None = None
    word_count_min: int | None = None
    word_count_max: int | None = None
    default_category: str | None = None
    categories: list[str] | None = None
    author: str | None = None
    seo_plugin: str | None = None
    brand_style: str | None = None
    tone: str | None = None
    alert_channel: str | None = None
    auto_publish: bool | None = None
    paused: bool | None = None
    dedupe_lookback_days: int | None = None
    dedupe_similarity: float | None = None
    wp_base_url: str | None = None
    wp_username: str | None = None
    wp_app_password: SecretStr | None = None
    revoke_wp_password: bool = False


class ConnectionCheck(BaseModel):
    name: str
    passed: bool
    note: str = ""


class ConnectionTest(BaseModel):
    passed: bool
    authenticated: bool = False
    checks: list[ConnectionCheck]
    simulated: bool = False
    read_only: bool = True
    message: str
    tested_at: datetime | None = None


class SitePublic(BaseModel):
    key: Literal["human", "kannadiga"]
    name: str
    domain: str
    language: Literal["kn", "en"]
    audience: str
    timezone: str
    publish_times: list[str]
    daily_quota: int
    word_count_min: int
    word_count_max: int
    default_category: str
    categories: list[str]
    author: str
    seo_plugin: str
    brand_style: str
    tone: str
    alert_channel: str
    auto_publish: bool
    paused: bool
    wp_base_url: str = ""
    wp_username: str = ""
    connected: bool = False
    connection_test: ConnectionTest | None = None
    connection_reason: str
    has_wp_password: bool = False


class PromptUpdate(BaseModel):
    template: str
    name: str | None = None


class ArticleEdit(BaseModel):
    headline: str | None = None
    dek: str | None = None
    excerpt: str | None = None
    content_html: str | None = None
    seo_title: str | None = None
    meta_description: str | None = None
    slug: str | None = None
    category: str | None = None
    tags: list[str] | None = None


class ScheduleBody(BaseModel):
    scheduled_time: str  # ISO datetime


class DiscoverBody(BaseModel):
    site_key: str


class RejectBody(BaseModel):
    reason: str = "Rejected by editor"


class ManualImageBody(BaseModel):
    url: str | None = None
    data_uri: str | None = None
    source: str = "manual"


class ImageRegenBody(BaseModel):
    brief: str | None = None


class GenericOk(BaseModel):
    ok: bool = True
    detail: Any = None


class SecretsUpdate(BaseModel):
    gemini_api_key: str | None = None
    openai_api_key: str | None = None
    rankmath_api_key: str | None = None
    research_provider: str | None = None
    writing_provider: str | None = None
    image_provider: str | None = None
    model_research: str | None = None
    model_writing: str | None = None
    model_image: str | None = None
