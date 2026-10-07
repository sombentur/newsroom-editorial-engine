"""Owner request (28 Sep 2026): the final WordPress post reads well: no Gemini false start or empty tables, and the
body goes to WordPress as core blocks (styled tables with captions, a lead paragraph, tidy source links)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

# Live case (post #2811): Gemini restarted its report; the false start is repeated later, and the real headline sat in
# a table that holds nothing else.
FALSE_START = (
    "<h1>US Wage Inequality Research</h1><h2>The Anatomy of the Inequality Tax</h2>"
    "<p>The financial squeeze felt by the American middle class can be quantified with stark precision. Between 1979 "
    "and 2022, market income for the top one percent of households grew by an astonishing 277 percent. &nbsp; \n\n\n</p>"
    "<table><thead><tr><th>Income Group</th><th>Gap</th><th>Impact</th></tr></thead><tbody><tr><td>The $30,000 Paycheck "
    "Penalty: Inside the Roots of America’s Affordability Crisis</td><td></td><td></td></tr></tbody></table>"
    "<p>In late September 2026, the United States economy presents a jarring paradox to its citizens and policymakers "
    "alike. &nbsp; </p><h2>The Mathematics of the Inequality Tax</h2>"
    "<p>The financial squeeze felt by the American middle class can be quantified with stark precision using data from "
    "the Congressional Budget Office (CBO). Between 1979 and 2022, market income for the top one percent of households "
    "grew by an astonishing 277 percent.</p>"
    "<table><thead><tr><th>Income Group</th><th>Gap</th><th>Impact</th></tr></thead><tbody><tr><td>Middle Quintile</td>"
    "<td>-16.6%</td><td>-$19,320</td></tr></tbody></table><table><thead><tr><th>Empty</th></tr></thead></table>")


def test_gemini_false_start_and_empty_tables_are_removed():
    from lib.report_article import report_to_article
    article = report_to_article(FALSE_START)
    assert article["headline"] == "The $30,000 Paycheck Penalty: Inside the Roots of America’s Affordability Crisis"
    body = article["content_html"]
    assert body.startswith("<p>In late September 2026"), "the article starts where Gemini restarted it"
    assert "Anatomy" not in body and body.count("<table") == 1 and "Middle Quintile" in body
    assert "&nbsp;" not in body and "\xa0" not in body and " </p>" not in body


def test_an_opening_the_article_does_not_repeat_is_kept():
    from lib.report_article import report_to_article
    report = FALSE_START.replace("The Mathematics of the Inequality Tax</h2><p>The financial squeeze",
                                 "Wages</h2><p>Entirely different words here, about something else").replace(
        "Between 1979 and 2022, market income for the top one percent of households grew by an astonishing 277 "
        "percent.</p><table", "Nothing in this sentence matches the opening section of the report at all.</p><table")
    body = report_to_article(report)["content_html"]
    assert "The Anatomy of the Inequality Tax" in body and body.count("<table") == 1, "only the empty table goes"


SAMPLE = ("<p>Lead paragraph.</p><h2>Section</h2><h3>Detail</h3><p>Body &amp; more.</p>"
          "<table><thead><tr><th>Group</th><th>Gap</th></tr></thead><tbody><tr><td>Top 1%</td><td>+119.4%</td></tr>"
          "<tr><td>Middle</td><td>-16.6%</td></tr></tbody></table><p>Data source: CBO (2022).</p>"
          "<ul><li><p>One</p></li><li>Two</li></ul>"
          "<ol><li><p>https://www.epi.org/productivity-pay-gap/</p></li><li><p>https://www.epi.org/productivity-pay-gap/</p>"
          "</li><li><p>https://www.bls.gov/news.release/pdf/prod2.pdf</p></li></ol>")


def test_article_html_becomes_wordpress_blocks():
    from lib.wp_blocks import to_blocks
    out = to_blocks(SAMPLE, "en")
    assert out.startswith('<!-- wp:paragraph {"fontSize":"medium"} -->\n<p class="has-medium-font-size">Lead paragraph.</p>')
    assert '<!-- wp:heading -->\n<h2 class="wp-block-heading">Section</h2>' in out
    assert '<!-- wp:heading {"level":3} -->\n<h3 class="wp-block-heading">Detail</h3>' in out
    assert "<p>Body &amp; more.</p>" in out
    assert ('<!-- wp:table {"hasFixedLayout":false,"className":"is-style-stripes"} -->\n<figure class="wp-block-table '
            'is-style-stripes"><table><thead><tr><th>Group</th><th class="has-text-align-right" data-align="right">Gap</th>') in out
    assert '<td class="has-text-align-right" data-align="right">+119.4%</td>' in out, "figures are right-aligned"
    assert '<figcaption class="wp-element-caption">Data source: CBO (2022).</figcaption>' in out
    assert "<p>Data source" not in out, "the source line became the caption"
    assert "<li>One</li>" in out and "<li>Two</li>" in out
    assert out.count("epi.org — Productivity pay gap") == 1, "each source once, as a readable link"
    assert "<summary>Sources (2)</summary>" in out and 'href="https://www.bls.gov/news.release/pdf/prod2.pdf"' in out
    assert out.count("<!-- wp:") == out.count("<!-- /wp:"), "every block is closed"


def test_kannada_source_list_title():
    from lib.wp_blocks import to_blocks
    out = to_blocks("<p>ಕನ್ನಡ ಲೇಖನ.</p><p>ಮೂಲಗಳು</p><ol><li>https://www.prajavani.net/a</li></ol>", "kn")
    assert "<summary>ಮೂಲಗಳು (1)</summary>" in out and "<p>ಮೂಲಗಳು</p>" not in out
