"""Live WordPress REST client (Application Password, Basic Auth over HTTPS).

Every method raises WPError on failure. Callers decide fallback. Secrets are never logged.
SEO meta is written through the optional companion plugin route (/wp-json/newsroom/v1/post-seo);
if the plugin is absent, SEO persistence is reported as unavailable rather than silently faked.
"""

import html
import logging
import re

import httpx
from lib.wp_credentials import CredentialError, decrypt_password, missing_credentials, normalize_base_url, is_connected

logger = logging.getLogger(__name__)

# SEO plugin meta keys (verified against playbook).
SEO_KEYS = {
    "yoast": {
        "title": "_yoast_wpseo_title", "desc": "_yoast_wpseo_metadesc", "focus": "_yoast_wpseo_focuskw",
        "canonical": "_yoast_wpseo_canonical", "og_title": "_yoast_wpseo_opengraph-title",
        "og_desc": "_yoast_wpseo_opengraph-description", "tw_title": "_yoast_wpseo_twitter-title",
        "tw_desc": "_yoast_wpseo_twitter-description",
    },
    "rankmath": {
        "title": "rank_math_title", "desc": "rank_math_description", "focus": "rank_math_focus_keyword",
        "canonical": "rank_math_canonical_url", "og_title": "rank_math_facebook_title",
        "og_desc": "rank_math_facebook_description", "tw_title": "rank_math_twitter_title",
        "tw_desc": "rank_math_twitter_description",
    },
}



_SAFE_TOKEN = re.compile(r"^[A-Za-z0-9_.\-]{1,60}$")


def wp_error_detail(response, endpoint: str) -> str:
    """WordPress's machine error code and rejected field names, plus our endpoint. Never its message or body."""
    where = f" (at {endpoint.split('?')[0][:60]})"
    try:
        body = response.json()
    except ValueError:
        return where
    if not isinstance(body, dict):
        return where
    code = str(body.get("code") or "")
    data = body.get("data") if isinstance(body.get("data"), dict) else {}
    params = data.get("params") if isinstance(data.get("params"), dict) else {}
    fields = [str(name) for name in params if _SAFE_TOKEN.match(str(name))][:6]
    parts = ([f"WordPress error {code}"] if _SAFE_TOKEN.match(code) else []) + ([f"fields: {', '.join(fields)}"] if fields else [])
    return (" " + "; ".join(parts) if parts else "") + where


class WPError(RuntimeError):
    def __init__(self, message: str, retryable: bool = False):
        super().__init__(message)
        self.retryable = retryable


def has_credentials(site: dict) -> bool:
    return not missing_credentials(site)


def safe_wp_error(exc: Exception) -> str:
    # Never reflect a remote body, URL, authorization header or arbitrary exception.
    if isinstance(exc, (WPError, CredentialError)):
        return str(exc)
    if isinstance(exc, httpx.TimeoutException):
        return "WordPress read-only request timed out."
    if isinstance(exc, httpx.RequestError):
        return "WordPress HTTPS connection failed (DNS, TLS or network failure)."
    return "WordPress returned an invalid or unexpected response."


class WordPressClient:
    def __init__(self, site: dict, *, read_only: bool = False):
        if not has_credentials(site):
            raise WPError("Missing saved WordPress connection settings.")
        base = normalize_base_url(site["wp_base_url"], site["domain"])
        self.site = site
        self.read_only = read_only
        self.base = base
        self.api = base + "/wp-json/wp/v2"
        self.seo_plugin = site.get("seo_plugin", "native")
        self._auth = (site["wp_username"], decrypt_password(site))

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            # Publishing can be slow while WordPress plugins react to a new post.
            auth=self._auth, timeout=httpx.Timeout(90, connect=10), verify=True,
            follow_redirects=False,
            headers={"Accept": "application/json", "User-Agent": "newsroom-engine/1.0"},
        )

    async def _call(self, method: str, url: str, **kw):
        method = method.upper()
        if self.read_only and method != "GET":
            raise WPError("Connection tests allow read-only GET requests only.")
        if not url.startswith(self.base + "/wp-json/"):
            raise WPError("WordPress request destination is not permitted.")
        if method != "GET":
            from lib.db import db
            from lib.safety import system_block_reason
            if reason := await system_block_reason():
                raise WPError(reason)
            current = await db.sites.find_one({"key": self.site["key"]}) or {}
            if not is_connected(current) or current.get("paused") or current.get("credential_revision") != self.site.get("credential_revision"):
                raise WPError("WordPress is NOT CONNECTED, paused, or credentials changed. Write blocked.")
        try:
            async with self._client() as c:
                r = await c.request(method, url, **kw)
        except httpx.RequestError as exc:
            raise WPError(safe_wp_error(exc), retryable=True) from None
        if not 200 <= r.status_code < 300:
            retryable = r.status_code in (429, 500, 502, 503, 504)
            reason = {401: "authentication rejected; check the saved username and Application Password or server Authorization-header forwarding",
                      403: "access forbidden; check account capabilities and WordPress security rules",
                      404: "REST endpoint not found; check the saved base URL and REST API configuration",
                      429: "WordPress rate limit reached"}.get(r.status_code, "request rejected")
            if 300 <= r.status_code < 400:
                reason = "redirect refused; save the final HTTPS base URL (including www if required)"
            raise WPError(f"WordPress HTTP {r.status_code}: {reason}.{wp_error_detail(r, url[len(self.base) + 8:])}",
                          retryable=retryable)
        try:
            return r.json() if r.content else None
        except ValueError:
            raise WPError("WordPress returned non-JSON content; REST access may be intercepted by a security page.") from None

    # ── capability probe ──
    async def verify(self) -> dict:
        checks: list[dict] = []
        authenticated = False
        try:
            me = await self._call("GET", f"{self.api}/users/me", params={"context": "edit"})
            if not isinstance(me, dict) or type(me.get("id")) is not int or me["id"] <= 0 or str(me.get("username", "")).casefold() != self.site["wp_username"].casefold():
                raise WPError("Authenticated WordPress identity did not match the saved username.")
            authenticated = True
            checks.append({"name": "authentication", "passed": True, "note": "Live GET users/me confirmed the saved account."})
            posts = await self._call("GET", f"{self.api}/posts", params={"per_page": 1, "context": "edit"})
            if not isinstance(posts, list):
                raise WPError("WordPress posts endpoint returned an unexpected response.")
            checks.append({"name": "read_only_access", "passed": True, "note": "Live authenticated GET only; no posts changed."})
        except Exception as exc:
            note = safe_wp_error(exc)
            checks.append({"name": "read_only_access" if authenticated else "authentication", "passed": False, "note": note})
            return {"passed": False, "authenticated": authenticated, "checks": checks, "simulated": False, "message": note}
        caps = me.get("capabilities") or {}
        for name, cap in (("post_creation", "edit_posts"), ("media_upload", "upload_files")):
            checks.append({"name": name, "passed": caps.get(cap) is True,
                           "note": "Declared capability only — no live write/upload test performed."})
        author = self.site.get("author", "")
        author_ok = author in (str(me["id"]), me.get("username"), me.get("slug"))
        checks.append({"name": "author_assignment", "passed": author_ok,
                       "note": "Configured author matches this account." if author_ok else "Author not verified; set the authenticated user's ID/login or verify a permitted author before writing."})
        try:
            categories = await self._call("GET", f"{self.api}/categories", params={"per_page": 1})
            checks.append({"name": "taxonomy_access", "passed": isinstance(categories, list), "note": "Read-only taxonomy access."})
        except Exception as exc:
            checks.append({"name": "taxonomy_access", "passed": False, "note": safe_wp_error(exc)})
        seo_ok = await self._seo_plugin_available()
        checks.append({"name": "seo_field_support", "passed": seo_ok,
                       "note": "companion plugin detected" if seo_ok else "install Newsroom SEO Bridge plugin"})

        return {"passed": True, "authenticated": True, "checks": checks, "simulated": False,
                "message": "Live authentication and read-only REST access passed. Write, upload and publication capabilities have NOT been live-tested."}

    async def _seo_plugin_available(self) -> bool:
        try:
            await self._call("GET", f"{self.base}/wp-json/newsroom/v1/ping")
            return True
        except Exception:
            return False

    # ── media ──
    async def upload_media(self, raw: bytes, filename: str, alt: str, caption: str, title: str,
                           content_type: str = "image/png") -> int:
        media = await self._call("POST", f"{self.api}/media", content=raw, headers={
                "Content-Type": content_type,
                "Content-Disposition": f'attachment; filename="{filename}"',
            })
        media_id = media["id"]
        await self._call("POST", f"{self.api}/media/{media_id}",
                         json={"alt_text": alt, "caption": caption, "title": title})
        return media_id

    async def find_media_by_slug(self, slug: str) -> dict | None:
        rows = await self._call("GET", f"{self.api}/media", params={"slug": slug, "context": "edit", "per_page": 1})
        return rows[0] if rows else None

    # ── taxonomy ──
    async def resolve_term(self, taxonomy: str, name: str, parent: int | None = None) -> int:
        """The term with this name, else a new one (a new category goes under `parent`). WordPress returns names
        HTML-escaped ("Work &amp; Labor"), so names are compared unescaped."""
        norm = lambda v: re.sub(r"\s+", " ", html.unescape(v).strip()).casefold()
        rows = await self._call("GET", f"{self.api}/{taxonomy}",
                                params={"search": name, "per_page": 100, "hide_empty": False})
        for x in rows or []:
            if norm(x["name"]) == norm(name):
                return x["id"]
        body = {"name": name, **({"parent": parent} if parent and taxonomy == "categories" else {})}
        created = await self._call("POST", f"{self.api}/{taxonomy}", json=body)
        return created["id"]

    async def set_primary_category(self, post_id: int, term_id: int) -> bool:
        """Rank Math's primary category (owner, 29 Sep 2026). False when Rank Math's REST route refuses or is absent."""
        try:
            await self._call("POST", f"{self.base}/wp-json/rankmath/v1/updateMeta",
                             json={"objectID": post_id, "objectType": "post", "meta": {"rank_math_primary_category": term_id}})
            return True
        except WPError:
            logger.info("Rank Math primary category unavailable; no remote response logged")
            return False

    async def find_by_slug(self, slug: str) -> dict | None:
        rows = await self._call("GET", f"{self.api}/posts", params={"slug": slug, "context": "edit", "status": "any"})
        return rows[0] if rows else None

    async def find_own_post(self, body: dict) -> dict | None:
        """The post an interrupted create made for this article: same slug, title, author and featured image."""
        try:
            rows = await self._call("GET", f"{self.api}/posts", params={"slug": body["slug"], "context": "edit", "status": "any"})
        except WPError:
            return None
        for post in rows or []:
            if (post.get("slug") == body["slug"] and (post.get("title") or {}).get("raw") == body.get("title")
                    and post.get("author") == body.get("author")
                    and (post.get("featured_media") or 0) == (body.get("featured_media") or 0)):
                return post
        return None

    # ── recent posts (Stage B dedupe) ──
    async def recent_posts(self, per_page: int = 50) -> list[dict]:
        rows = await self._call("GET", f"{self.api}/posts",
                                params={"per_page": per_page, "_fields": "id,title,slug,date,status"})
        return rows or []

    # ── create / update post ──
    async def save_post(self, body: dict, existing_id: int | None = None) -> dict:
        if existing_id:
            return await self._call("POST", f"{self.api}/posts/{existing_id}", json=body)
        old = await self.find_by_slug(body["slug"])
        if old:
            raise WPError("A WordPress post already uses this slug. Held to avoid modifying an unrelated existing post.")
        return await self._call("POST", f"{self.api}/posts", json=body)

    async def read_post(self, post_id: int) -> dict:
        return await self._call("GET", f"{self.api}/posts/{post_id}", params={"context": "edit"})

    # ── SEO meta via companion plugin ──
    async def write_seo(self, post_id: int, article: dict, canonical: str) -> bool:
        keys = SEO_KEYS.get(self.seo_plugin)
        if not keys:
            return False
        meta = {
            keys["title"]: article.get("seo_title", ""),
            keys["desc"]: article.get("meta_description", ""),
            keys["focus"]: article.get("focus_keyword", ""),
            keys["canonical"]: canonical,
            keys["og_title"]: article.get("og_title", ""),
            keys["og_desc"]: article.get("og_description", ""),
            keys["tw_title"]: article.get("og_title", ""),
            keys["tw_desc"]: article.get("og_description", ""),
        }
        try:
            await self._call("POST", f"{self.base}/wp-json/newsroom/v1/post-seo",
                             json={"post_id": post_id, "meta": meta})
            return True
        except Exception:
            logger.info("SEO meta write unavailable; no remote response logged")
            return False

    # ── public page verification ──
    async def verify_public(self, url: str) -> dict:
        try:
            async with httpx.AsyncClient(timeout=15, follow_redirects=True) as c:
                r = await c.get(url, headers={"User-Agent": "newsroom-verify/1.0"})
            html = r.text
            return {
                "status_code": r.status_code,
                "public_page_ok": r.status_code == 200,
                "canonical_ok": 'rel="canonical"' in html,
                "og_ok": 'property="og:' in html,
                "schema_ok": "application/ld+json" in html,
            }
        except Exception:
            return {"public_page_ok": False, "note": "Public page verification failed."}
