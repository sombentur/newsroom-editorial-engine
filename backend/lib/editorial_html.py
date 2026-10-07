"""Allowlisted editorial markup for storage and preview."""
import bleach


def sanitize_html(value: str) -> str:
    return bleach.clean(value, tags={"p", "br", "h2", "h3", "h4", "ul", "ol", "li", "strong", "em", "blockquote", "a", "table", "thead", "tbody", "tr", "th", "td"},
                        attributes={"a": ["href", "title"]}, protocols={"http", "https"}, strip=True)
