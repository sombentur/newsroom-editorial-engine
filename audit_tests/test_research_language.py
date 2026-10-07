import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from lib.prompts import RESEARCH_LANGUAGE_RULES, RESEARCH_PROMPT


def render(lang):
    return RESEARCH_PROMPT.format(site_name="Site", topic="T", angle="", audience="", geography="",
                                  current_datetime_with_timezone="now",
                                  language="Kannada" if lang == "kn" else "English") + RESEARCH_LANGUAGE_RULES[lang]


def test_kannada_research_demands_a_kannada_report_from_kannada_and_english_sources():
    prompt = render("kn")
    assert "ENTIRE Deep Research report in Kannada" in prompt
    assert "BOTH Kannada and English" in prompt
    assert "not a research plan" in prompt
    # The Chrome extension only accepts a Kannada report when the prompt names Kannada.
    assert re.search(r"kannada|ಕನ್ನಡ", prompt, re.I)


def test_english_research_is_explicitly_english():
    prompt = render("en")
    assert "ENTIRE research report" in prompt and "in clear English" in prompt
