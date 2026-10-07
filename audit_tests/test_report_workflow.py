"""Report-as-article workflow: Gemini report -> article, ChatGPT SEO, Gemini topic ranking."""
import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from lib.report_article import (LANGUAGE_RULES, parse_seo, report_to_article, report_validation,
                                research_prompt, seo_prompt, DEEP_RESEARCH_ARTICLE_PROMPT)

KN_PARAGRAPH = ("ರಾಯಚೂರಿನ ದೇವದುರ್ಗ ತಾಲೂಕಿನಲ್ಲಿ ಫೇಕ್ ಸೀಡ್ಸ್ ದಂಧೆ ಬಯಲಾಗಿದೆ ಮತ್ತು ರೈತರು ಸಾಲದ ಸುಳಿಗೆ ಸಿಲುಕಿದ್ದಾರೆ. " * 6).strip()
REPORT = (
    "# ಫೇಕ್ ಸೀಡ್ಸ್ ಮತ್ತು ಬ್ಲ್ಯಾಕ್ ಮಾರ್ಕೆಟ್ ದಂಧೆ: ಉತ್ತರ ಕರ್ನಾಟಕದ ರೈತರು\n\n"
    + "\n\n".join(f"## ವಿಭಾಗ {i}\n\n{KN_PARAGRAPH}" for i in range(1, 6))
    + "\n\n## ಮೂಲಗಳು\n1. Prajavani, https://www.prajavani.net/a\n2. The Hindu, https://www.thehindu.com/b\n"
)


def test_copied_report_becomes_article_html_without_h1():
    article = report_to_article(REPORT)
    assert article["headline"].startswith("ಫೇಕ್ ಸೀಡ್ಸ್")
    assert "<h1" not in article["content_html"] and article["content_html"].count("<h2>") == 6
    assert '<a href="https://www.thehindu.com/b">' in article["content_html"]
    assert article["sources"] == ["https://www.prajavani.net/a", "https://www.thehindu.com/b"]


def test_report_validation_passes_complete_kannada_article_and_rejects_plans():
    article = report_to_article(REPORT)
    assert report_validation(REPORT, article, "kn")["passed"]
    plan = "I've put together a research plan\n" + REPORT
    assert "not_a_plan" in report_validation(plan, report_to_article(plan), "kn")["failed_reasons"]
    english = report_to_article(REPORT.replace(KN_PARAGRAPH, "English words only here. " * 30))
    assert "kannada_script" in report_validation(REPORT, english, "kn")["failed_reasons"]


def test_kannada_prompts_require_english_terms_in_kannada_script():
    site = {"name": "Kannada Edition", "language": "kn", "audience": "Karnataka"}
    prompt = research_prompt(DEEP_RESEARCH_ARTICLE_PROMPT, site, {"topic": "Fake seeds"}, "now")
    assert "ಫೇಕ್ ಸೀಡ್ಸ್" in prompt and "Kannada AND English sources" in prompt
    assert "not a research plan" in prompt and prompt.endswith(LANGUAGE_RULES["kn"])
    seo = seo_prompt(report_to_article(REPORT), site)
    assert "exactly 3 lines of Kannada-script text" in seo and "phonetically in Kannada script" in seo
    assert '"thumbnail_design"' in seo and "MERIT & SACRIFICE" in seo, "the owner's example shows the format"


DESIGN_JSON = ('{"story_type":"investigative farm-input scam","emotion":"farmer distress and alleged fraud",'
               '"left":{"title":"Farmer\'s loss","shows":["a","b","c","d"],"colors":["warm dusk"]},'
               '"right":{"title":"The racket","shows":["e","f","g","h"],"colors":["deep red"]},'
               '"center":["x","y","z"]}')


def test_parse_seo_takes_answer_json_and_normalises_slug():
    answer = ('Here you go:\n{"seo_title":"ಫೇಕ್ ಸೀಡ್ಸ್ ದಂಧೆ","meta_description":"ವಿವರ","focus_keyword":"ಫೇಕ್ ಸೀಡ್ಸ್",'
              '"slug":"Fake Seeds Scam North Karnataka!","tags":["a","b"],'
              '"thumbnail_headlines":["ಒಂದು","ಎರಡು","ಮೂರು"],"thumbnail_design":' + DESIGN_JSON + '}\n\n'
              "PROVIDER CITATION LINKS — ignore:\n")
    seo = parse_seo(answer, "kn")
    assert seo["slug"] == "fake-seeds-scam-north-karnataka" and len(seo["thumbnail_headlines"]) == 3
    with pytest.raises(ValueError):
        parse_seo('{"seo_title": "x"}', "kn")
    with pytest.raises(ValueError):
        parse_seo("Sorry, I can't help.", "kn")


def test_controller_allows_collecting_chatgpt_answer_for_seo_jobs():
    from lib.browser_controller import Decision, Observation, validate_decision
    obs = Observation(snapshot="s", url="https://chatgpt.com/c/1", text="", submitted=True,
                      elements=[{"id": 1, "role": "report", "name": "answer"}])
    decision = Decision(action="collect_report", target=1, reason="done")
    assert validate_decision({"kind": "seo"}, obs, decision).action == "collect_report"
    with pytest.raises(ValueError):
        validate_decision({"kind": "image"}, obs, decision)


class DiscoveryRankingTests(IsolatedAsyncioTestCase):
    def candidates(self, n):
        return [{"topic": f"Topic {i}", "status": "candidate", "score": 50, "similarity": 0.0, "risk_flags": [],
                 "category": "News", "score_breakdown": {}} for i in range(n)]

    async def test_gemini_scores_categories_and_caution(self):
        from lib import discovery
        cands = self.candidates(2)
        ranking = {"rankings": [{"index": 0, "engagement": 91, "category": "Agriculture", "reason": "Farmers hit", "safe": True},
                                {"index": 1, "engagement": 80, "category": "Crime", "reason": "Rumour", "safe": False}]}
        with patch.object(discovery, "_gemini_rank_call", return_value=ranking), \
                patch("lib.runtime.RuntimeSafety.from_env", return_value=SimpleNamespace(dry_run=False)):
            self.assertTrue(await discovery._rank_with_gemini({"name": "x"}, cands))
        self.assertEqual((cands[0]["score"], cands[0]["category"]), (91, "Agriculture"))
        self.assertEqual(cands[1]["score"], 50)
        self.assertIn("ai_editorial_caution", cands[1]["risk_flags"])

    async def test_ranking_failure_keeps_heuristic_scores(self):
        from lib import discovery
        cands = self.candidates(1)
        with patch.object(discovery, "_gemini_rank_call", side_effect=RuntimeError("quota")), \
                patch("lib.runtime.RuntimeSafety.from_env", return_value=SimpleNamespace(dry_run=False)):
            self.assertFalse(await discovery._rank_with_gemini({"name": "x"}, cands))
        self.assertEqual(cands[0]["score"], 50)


def test_gemini_html_copy_becomes_structured_article():
    """Gemini's HTML clipboard copy keeps structure that its plain-text copy loses."""
    paragraph = "ರಾಯಚೂರಿನ ದೇವದುರ್ಗ ತಾಲೂಕಿನಲ್ಲಿ ಫೇಕ್ ಸೀಡ್ಸ್ ದಂಧೆ ಬಯಲಾಗಿದೆ ಮತ್ತು ರೈತರು ಸಾಲದ ಸುಳಿಗೆ ಸಿಲುಕಿದ್ದಾರೆ. " * 8
    sections = "".join(f"<h2><span>ವಿಭಾಗ {i}</span></h2><p>{paragraph}</p>" for i in range(5))
    copied = ('<meta charset="utf-8"><div class="markdown"><h1>ಫೇಕ್ ಸೀಡ್ಸ್ ದಂಧೆ: ರೈತರ ಸಂಕಷ್ಟ</h1>'
              '<button>Learn More</button><script>alert(1)</script>' + sections +
              '<h2>ಮೂಲಗಳು</h2><ol><li><a href="https://www.prajavani.net/a" onclick="x()">Prajavani</a></li>'
              '<li><a href="https://www.thehindu.com/b">The Hindu</a></li></ol></div>')
    article = report_to_article(copied)
    assert article["headline"] == "ಫೇಕ್ ಸೀಡ್ಸ್ ದಂಧೆ: ರೈತರ ಸಂಕಷ್ಟ"
    body = article["content_html"]
    assert "<h1" not in body and body.count("<h2>") == 6 and "<script" not in body and "onclick" not in body
    assert '<a href="https://www.thehindu.com/b">' in body
    assert article["sources"] == ["https://www.prajavani.net/a", "https://www.thehindu.com/b"]
    assert report_validation(copied, article, "kn")["passed"]


def test_flattened_plain_text_copy_is_rejected_not_published():
    flat = "ರಾಜಕೀಯ ಬಿಕ್ಕಟ್ಟು " * 300 + "https://a.example/x" + "https://b.example/y"
    assert not report_validation(flat, report_to_article(flat), "kn")["passed"]


def test_recopy_fetches_the_reports_own_conversation_at_once():
    """Owner report (29 Sep 2026): a copy queued behind other articles threw away a report already imported."""
    from lib import browser_bridge as b
    art = {"id": "A", "stage": "held_review", "wp": None,
           "dossier_meta": {"report_mode": True, "prompt": "Use Deep Research ...", "report": "flat text"}}
    database = SimpleNamespace(
        articles=SimpleNamespace(find_one=AsyncMock(return_value=art)),
        browser_jobs=SimpleNamespace(find_one=AsyncMock(return_value={"conversation_url": "https://gemini.google.com/app/abc123"})))
    fetch = AsyncMock(return_value={"status": "ready_to_import"})
    with patch.object(b, "db", database), patch("lib.manual_research.import_again", fetch):
        result = asyncio.run(b.recopy_report("A"))
    assert fetch.await_args.args == ("A", "https://gemini.google.com/app/abc123"), "the report's own conversation"
    assert result["manual_research"]["status"] == "ready_to_import"



def test_recopy_without_recorded_conversation_asks_for_research_again():
    import pytest
    from fastapi import HTTPException
    from lib import browser_bridge as b
    art = {"id": "A", "stage": "held_review", "wp": None, "dossier_meta": {"report_mode": True, "prompt": "p"}}
    database = SimpleNamespace(
        articles=SimpleNamespace(find_one=AsyncMock(return_value=art)),
        browser_config=SimpleNamespace(find_one=AsyncMock(return_value={"workspace": {"research": {"tab_id": 42}}})),
        browser_jobs=SimpleNamespace(find_one=AsyncMock(return_value=None)))
    with patch.object(b, "db", database), pytest.raises(HTTPException, match="Research again"):
        asyncio.run(b.recopy_report("A"))



def test_recurring_columns_are_not_news_topics():
    from lib.discovery import RECURRING_COLUMN
    assert RECURRING_COLUMN.search("ದಿನ ಭವಿಷ್ಯ: ಇಂದು ಈ ರಾಶಿಯವರು ಆರ್ಥಿಕತೆಯನ್ನು ಗಟ್ಟಿಗೊಳಿಸಿ")
    assert RECURRING_COLUMN.search("Daily Horoscope for September 27")
    assert not RECURRING_COLUMN.search("ತೀವ್ರ ಸ್ವರೂಪ ಪಡೆದ ಬಿಡದಿ ರೈತರ ಹೋರಾಟ")



def test_english_source_list_does_not_fail_a_kannada_article():
    from lib.kannada_audit import language_checks
    paragraph = "ರಾಯಚೂರಿನ ದೇವದುರ್ಗ ತಾಲೂಕಿನಲ್ಲಿ ಫೇಕ್ ಸೀಡ್ಸ್ ದಂಧೆ ಬಯಲಾಗಿದೆ ಮತ್ತು ರೈತರು ಸಾಲದ ಸುಳಿಗೆ ಸಿಲುಕಿದ್ದಾರೆ. " * 8
    sources = "".join(f'<li><a href="https://example{i}.com/a">Karnataka farmers protest coverage report number {i} English title</a></li>'
                      for i in range(120))
    copied = ("<h1>ಫೇಕ್ ಸೀಡ್ಸ್ ದಂಧೆ: ರೈತರ ಸಂಕಷ್ಟ</h1>" + "".join(f"<h2>ವಿಭಾಗ {i}</h2><p>{paragraph}</p>" for i in range(5))
              + "<h2>ಉಲ್ಲೇಖಿತ ಕೃತಿಗಳು</h2><ol>" + sources + "</ol>")
    article = report_to_article(copied)
    assert report_validation(copied, article, "kn")["passed"]
    checks = {name: ok for name, ok, _ in language_checks(article)}
    assert checks["kannada_body_script"], "the English bibliography is not counted as prose"


def test_gemini_page_headings_are_not_the_headline():
    from lib.report_article import report_to_article
    body = "<p>" + "ಬಿಡದಿ ಯೋಜನೆಯ ವಿವರಗಳು ಇಲ್ಲಿವೆ. " * 40 + "</p>"
    article = report_to_article("<h1>Conversation with Gemini</h1><h2>Gemini said</h2><h1>ಬಿಡದಿ ಯೋಜನೆ</h1>" + body)
    assert article["headline"] == "ಬಿಡದಿ ಯೋಜನೆ"
    assert "Gemini said" not in article["content_html"] and "Conversation with Gemini" not in article["content_html"]


def test_gemini_cite_labels_are_removed():
    from lib.report_article import report_to_article
    body = "<p>" + "ಬಿಡದಿ ಯೋಜನೆಯ ವಿವರಗಳು ಇಲ್ಲಿವೆ. " * 40 + " [cite: 1, 2]</p>"
    sources = "<h2>ಮೂಲಗಳು</h2><ol><li>[cite: 10] https://publictv.in/a</li><li>[cite: 2] https://vijayavani.net/b</li></ol>"
    article = report_to_article("<h1>ಬಿಡದಿ ಯೋಜನೆ</h1>" + body + sources)
    assert "[cite" not in article["content_html"]
    assert {"https://publictv.in/a", "https://vijayavani.net/b"} <= set(article["sources"])


def test_source_urls_are_not_unsafe_html():
    from lib.workflow import UNSAFE_HTML
    sources = ("<li><p>https://nsp.nanet.go.kr/plan/detail.do?nationalPlanControlNo=PLAN1&amp;newReportChk=list</p></li>"
               '<li><a href="https://research.upjohn.org/cgi/viewcontent.cgi?article=1099&amp;context=up">Upjohn</a></li>')
    assert not UNSAFE_HTML.search(sources), "URL parameters are text, not event handlers"
    for unsafe in ('<p onclick="x()">a</p>', "<img src=x onerror=alert(1)>", "<script>alert(1)</script>",
                   '<iframe src="https://x"></iframe>', "<form action=x>"):
        assert UNSAFE_HTML.search(unsafe), unsafe


def test_rejected_article_is_not_overwritten_by_ai_hold():
    import asyncio
    from unittest.mock import AsyncMock, patch as mock_patch
    from lib import workflow
    rejected = {"id": "a1", "site_key": "kannadiga", "stage": "rejected", "held_reason": "Rejected by owner"}
    from types import SimpleNamespace
    fake_db = SimpleNamespace(articles=SimpleNamespace(find_one=AsyncMock(return_value=dict(rejected))))
    with mock_patch.object(workflow, "db", fake_db), \
         mock_patch.object(workflow, "_update", AsyncMock()) as update, mock_patch.object(workflow, "audit", AsyncMock()):
        result = asyncio.run(workflow._ai_hold(dict(rejected), "Deep Research", workflow.AIError("cancelled", kind="browser")))
    assert result["stage"] == "rejected" and not update.called


def test_wordpress_error_keeps_wordpress_explanation():
    import httpx
    from lib.wordpress import wp_error_detail
    rejected = httpx.Response(400, json={"code": "rest_invalid_param", "message": "Invalid parameter(s): date",
                                         "data": {"status": 400, "params": {"date": "Invalid date."}}})
    detail = wp_error_detail(rejected, "/wp/v2/posts?context=edit")
    assert "WordPress error rest_invalid_param" in detail and "fields: date" in detail
    assert "Invalid parameter" not in detail, "never WordPress's free-text message"
    assert detail.endswith("(at /wp/v2/posts)")
    odd = httpx.Response(400, json={"code": "<script>x</script>", "message": "secret", "data": {"params": {"a b": 1}}})
    assert wp_error_detail(odd, "/wp/v2/posts") == " (at /wp/v2/posts)"
    assert wp_error_detail(httpx.Response(400, text="<html>blocked</html>"), "/wp/v2/media") == " (at /wp/v2/media)"


def test_seo_is_never_requested_without_the_article():
    import asyncio
    from types import SimpleNamespace
    from unittest.mock import AsyncMock, patch as mock_patch
    from lib import workflow
    art = {"id": "a1", "site_key": "human", "stage": "research_validated", "dossier_meta": {"report_mode": True, "report": ""}}
    fake_db = SimpleNamespace(articles=SimpleNamespace(update_one=AsyncMock()))
    with mock_patch.object(workflow, "db", fake_db), \
         mock_patch.object(workflow, "_update", AsyncMock(return_value=dict(art))), \
         mock_patch.object(workflow, "_ai_hold", AsyncMock(return_value={"stage": "held_review"})) as hold, \
         mock_patch("lib.browser_bridge.run_job", AsyncMock()) as run_job:
        asyncio.run(workflow._run_report_article(dict(art), {"language": "en", "name": "English Edition"}))
    assert not run_job.called, "no SEO prompt without the article"
    assert "report is missing" in str(hold.call_args.args[2])
    assert fake_db.articles.update_one.call_args.args[1] == {"$set": {"dossier": None, "validation": None}}


def test_recopy_takes_the_gemini_link_the_owner_pasted():
    """Owner request (28 Sep 2026): a box for the Gemini link of a finished report; also when it was never recorded."""
    import pytest
    from fastapi import HTTPException
    from lib import browser_bridge as b
    art = {"id": "A", "stage": "held_review", "wp": None, "dossier_meta": {"report_mode": True, "prompt": "p"}}
    database = SimpleNamespace(articles=SimpleNamespace(find_one=AsyncMock(return_value=art)),
                               browser_jobs=SimpleNamespace(find_one=AsyncMock(return_value=None)))
    fetch = AsyncMock(return_value={"status": "ready_to_import"})
    with patch.object(b, "db", database), patch("lib.manual_research.import_again", fetch):
        asyncio.run(b.recopy_report("A", b.RecopyBody(url="https://gemini.google.com/u/2/app/026b0fa4de34145d?hl=en")))
        assert fetch.await_args.args == ("A", "https://gemini.google.com/u/2/app/026b0fa4de34145d")
        for bad in ("https://chatgpt.com/c/123456", "https://evil.example/app/026b0fa4de34145d", "gemini.google.com/app/x"):
            with pytest.raises(HTTPException, match="Gemini conversation"):
                asyncio.run(b.recopy_report("A", b.RecopyBody(url=bad)))
