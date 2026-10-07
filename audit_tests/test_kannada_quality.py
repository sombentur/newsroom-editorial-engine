"""Offline checks for source corroboration and readable Kannada."""
import sys
from pathlib import Path
import unittest
from unittest.mock import AsyncMock, patch
import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from lib import ai
from lib.kannada_audit import editorial_audit, language_checks
from lib.research_validation import reconcile_provider_citations, resolve_grounding_redirects, validate_research


class KannadaQualityTests(unittest.IsolatedAsyncioTestCase):
    def test_research_requires_two_sources_and_claim_mapping(self):
        dossier = {"sources": [{"url": "https://first.example/story"}],
                   "claim_evidence": [{"claim": "A", "source_url": "https://first.example/story", "verified": True}],
                   "publication_ready": True}
        self.assertIn("kannada_second_source", validate_research(dossier, "kn")["failed_reasons"])
        dossier["sources"].append({"url": "https://second.example/report"})
        self.assertTrue(validate_research(dossier, "kn")["passed"])
        dossier["claim_evidence"][0]["source_url"] = "https://unknown.example/story"
        self.assertIn("claim_urls_match_sources", validate_research(dossier, "kn")["failed_reasons"])

    def test_kannada_prose_must_be_readable_script(self):
        good = {"headline": "ಕರ್ನಾಟಕದ ಇಂದಿನ ಸುದ್ದಿ", "content_html": "<p>ಕರ್ನಾಟಕದಲ್ಲಿ ನಡೆದ ಘಟನೆಯ ಬಗ್ಗೆ ಪರಿಶೀಲನೆ ನಡೆಯುತ್ತಿದೆ.</p>"}
        self.assertTrue(all(passed for _, passed, _ in language_checks(good)))
        bad = {"headline": "Kannada news ಕ", "content_html": "<p>This is an English story with one ಕ character.</p>"}
        self.assertFalse(all(passed for _, passed, _ in language_checks(bad)))

    async def test_independent_editorial_audit_requires_all_three_verdicts(self):
        with patch("lib.kannada_audit.provider_json", new=AsyncMock(return_value=(
                {"language_ok": True, "readability_ok": False, "grounding_ok": True,
                 "issues": ["Literal translation in the headline"]}, "fixture-model"))):
            result = await editorial_audit({"headline": "ಶೀರ್ಷಿಕೆ"}, {"sources": []})
        self.assertFalse(result["passed"])
        self.assertIn("Literal translation", result["issues"][0])

    async def test_kannada_audit_cannot_pass_with_unresolved_issues(self):
        with patch("lib.kannada_audit.provider_json", new=AsyncMock(return_value=(
                {"language_ok": True, "readability_ok": True, "grounding_ok": True,
                 "issues": ["Replace an awkward translated phrase"]}, "fixture-model"))):
            result = await editorial_audit({"headline": "ಶೀರ್ಷಿಕೆ"}, {"sources": []})
        self.assertFalse(result["passed"])

    async def test_grounding_redirects_resolve_to_real_source_domains(self):
        first = "https://vertexaisearch.cloud.google.com/grounding-api-redirect/first"
        second = "https://vertexaisearch.cloud.google.com/grounding-api-redirect/second"
        dossier = {"sources": [{"url": first}, {"url": second}],
                   "claim_evidence": [{"source_url": first, "verified": True}], "publication_ready": True}
        destinations = {first: "https://first.example/story", second: "https://second.example/report"}
        real_client = httpx.AsyncClient

        def factory(**kwargs):
            return real_client(transport=httpx.MockTransport(lambda request: httpx.Response(
                302, headers={"location": destinations[str(request.url)]})), **kwargs)

        with patch("lib.research_validation.httpx.AsyncClient", side_effect=factory):
            await resolve_grounding_redirects(dossier)
        self.assertTrue(validate_research(dossier, "kn")["passed"])

    async def test_only_provider_backed_missing_claim_links_are_added(self):
        redirect = "https://vertexaisearch.cloud.google.com/grounding-api-redirect/second"
        dossier = {"sources": [{"url": "https://first.example/story"}],
                   "claim_evidence": [
                       {"claim": "Backed fact", "source_url": "https://second.example/report", "verified": True},
                       {"claim": "Unbacked fact", "source_url": "https://invented.example/story", "verified": True}],
                   "publication_ready": True}
        report = "Research\n\nPROVIDER CITATION LINKS — use only these exact URLs:\n- [cite: 2]: " + redirect
        real_client = httpx.AsyncClient

        def factory(**kwargs):
            return real_client(transport=httpx.MockTransport(lambda request: httpx.Response(
                302, headers={"location": "https://second.example/report"})), **kwargs)

        with patch("lib.research_validation.httpx.AsyncClient", side_effect=factory):
            await reconcile_provider_citations(dossier, report)
        urls = {source["url"] for source in dossier["sources"]}
        self.assertIn("https://second.example/report", urls)
        self.assertNotIn("https://invented.example/story", urls)
        self.assertIn("claim_urls_match_sources", validate_research(dossier, "kn")["failed_reasons"])
        dossier["claim_evidence"].pop()
        self.assertTrue(validate_research(dossier, "kn")["passed"])

    def test_missing_model_error_is_actionable_without_secret(self):
        exc = Exception("private-key-do-not-display")
        exc.code = "model_not_found"
        self.assertEqual(ai._classify(exc), "model_unavailable")
        self.assertIn("selected AI model", ai._safe(exc))
        self.assertNotIn("private-key", ai._safe(exc))


if __name__ == "__main__":
    unittest.main()
