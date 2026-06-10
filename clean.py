"""Text cleaning helpers shared by scrape.py and chunk.py.

Goal: strip everything that is NOT review/opinion content -- HTML tags,
HTML entities (&amp;, &nbsp;), navigation, cookie banners, ads, footers,
"Read more" links, share buttons, markdown noise -- while keeping the
actual review text, ratings, and the context needed to understand it.
"""
import html
import re

from bs4 import BeautifulSoup

# Structural tags that never contain review content.
_DROP_TAGS = [
    "script", "style", "noscript", "template", "svg", "iframe",
    "nav", "header", "footer", "aside", "form", "button", "menu",
]

# Elements whose class/id marks them as boilerplate (chrome that repeats on
# every page): nav menus, cookie/consent banners, ads, share/social buttons,
# footers, breadcrumbs, newsletter signups, comment counters, etc.
_DROP_ATTR = re.compile(
    r"(nav|menu|breadcrumb|cookie|consent|gdpr|banner|advert|ad-|-ad\b|ads\b"
    r"|sponsor|promo|footer|header|masthead|share|social|subscribe|newsletter"
    r"|sidebar|modal|popup|overlay|related|recommend|comment-count|read-more"
    r"|skip-link|pagination|toolbar)",
    re.I,
)

# Phrases that signal an anti-bot / JS-required interstitial rather than content.
_BLOCK_MARKERS = (
    "enable javascript", "just a moment", "checking your browser",
    "verify you are human", "captcha", "access denied",
    "request unsuccessful", "are you a robot",
)


def unescape_entities(text: str) -> str:
    """Decode HTML entities (&amp; -> &, &nbsp; -> space) until stable."""
    prev = None
    while prev != text:
        prev = text
        text = html.unescape(text)
    # Normalize unicode whitespace that survives unescaping.
    return text.replace(" ", " ").replace("​", "").replace("﻿", "")


def normalize_whitespace(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t\f\v]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def strip_markdown(text: str) -> str:
    """Reddit bodies are markdown -- flatten links/formatting to plain prose."""
    # [label](url) -> label ; bare images ![alt](url) -> alt
    text = re.sub(r"!?\[([^\]]*)\]\([^)]*\)", r"\1", text)
    # Bare URLs add no semantic value to a review.
    text = re.sub(r"https?://\S+", "", text)
    # Leading markdown markers per line: headings, quotes, list bullets.
    text = re.sub(r"(?m)^\s{0,3}(#{1,6}|>|[-*+]|\d+\.)\s+", "", text)
    # Inline emphasis / code markers.
    text = re.sub(r"[*_`~]{1,3}", "", text)
    return text


def clean_text(text: str) -> str:
    """Full cleaning pass for already-plain (non-HTML) text such as Reddit bodies."""
    if not text:
        return ""
    text = unescape_entities(text)
    text = strip_markdown(text)
    return normalize_whitespace(text)


def html_to_text(raw_html: str) -> tuple[str, bool]:
    """Convert an HTML page to clean review text.

    Returns (text, looks_blocked). looks_blocked is True when the page appears
    to be an anti-bot interstitial instead of real content.
    """
    soup = BeautifulSoup(raw_html, "lxml")

    for tag in soup(_DROP_TAGS):
        tag.decompose()
    for el in soup.find_all(attrs={"class": _DROP_ATTR}):
        el.decompose()
    for el in soup.find_all(attrs={"id": _DROP_ATTR}):
        el.decompose()

    # "Read more" / "Share" anchors that slipped past class-based removal.
    for a in soup.find_all("a"):
        label = a.get_text(" ", strip=True).lower()
        if label in ("read more", "share", "report", "reply", "...more", "see more"):
            a.decompose()

    text = unescape_entities(soup.get_text("\n"))
    text = normalize_whitespace(text)

    blocked = len(text) < 200 or any(m in text.lower() for m in _BLOCK_MARKERS)
    return text, blocked
