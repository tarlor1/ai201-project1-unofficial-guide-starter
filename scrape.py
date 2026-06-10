"""Stage 1 -- Document Ingestion.

Produces one cleaned JSON file per source in ./documents. Each file is a list of
"records", where a record is an atomic unit of opinion: a Reddit post, a Reddit
comment, a Reddit reply, or a block of review text from an HTML page.

Reddit no longer serves unauthenticated JSON, so the six r/SBU threads are read
from HTML pages saved by the user (logged-in browser, "Save page as"). Reddit's
"shreddit" web components expose author / depth / score / permalink as element
attributes and the body in a `div[slot="comment"]`, which is everything we need
to rebuild the comment/reply tree -- including each reply's parent, so context
survives into chunking and ChromaDB.

The remaining sites (RateMyProfessors, Coursicle, Niche) are JS-rendered and/or
bot-protected, so they are fetched through Playwright (headless Chromium) and
then stripped of boilerplate in clean.py.

Run:  python scrape.py
"""
import json
import re
import sys
from pathlib import Path

from bs4 import BeautifulSoup

import config
from clean import clean_text, html_to_text

# Windows consoles default to cp1252 and crash on emoji / curly quotes that show
# up in real reviews; force UTF-8 so progress output never dies mid-run.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

DOCS_DIR = Path(config.DOCS_PATH)

# Mirrors the Documents table in planning.md. `thread_id` ties a Reddit source
# to a saved HTML file; html sources are fetched live via Playwright.
SOURCES = [
    {"n": 1, "kind": "rmp", "name": "RateMyProfessors",
     "desc": "RateMyProfessors - Marco Martens",
     "url": "https://www.ratemyprofessors.com/professor/1125597"},
    {"n": 2, "kind": "rmp", "name": "RateMyProfessors",
     "desc": "RateMyProfessors - Erlend Graf",
     "url": "https://www.ratemyprofessors.com/professor/603668"},
    {"n": 3, "kind": "html", "name": "Coursicle",
     "desc": "Coursicle ISE 300",
     "url": "https://www.coursicle.com/stonybrook/courses/ISE/300/"},
    # Niche is behind a "Press & Hold to confirm you are a human" wall that
    # headless Chromium can't pass, so it's replaced with another r/SBU thread
    # (saved as HTML like the others).
    {"n": 4, "kind": "reddit", "name": "Reddit r/SBU", "thread_id": "1dmym7l",
     "desc": "Worst professors at SBU thread",
     "url": "https://www.reddit.com/r/SBU/comments/1dmym7l/worst_professors_at_sbu/"},
    {"n": 5, "kind": "reddit", "name": "Reddit r/SBU", "thread_id": "j0n2ff",
     "desc": "Best and worst professor thread",
     "url": "https://www.reddit.com/r/SBU/comments/j0n2ff/who_is_the_best_and_worst_professor_in_stony_brook/"},
    {"n": 6, "kind": "reddit", "name": "Reddit r/SBU", "thread_id": "dmqhc6",
     "desc": "Best / most interesting professor recommendations",
     "url": "https://www.reddit.com/r/SBU/comments/dmqhc6/who_is_the_bestmost_interesting_professor_youve/"},
    {"n": 7, "kind": "reddit", "name": "Reddit r/SBU", "thread_id": "i36oi3",
     "desc": "Professor & class recommendations thread",
     "url": "https://www.reddit.com/r/SBU/comments/i36oi3/you_recommend_sbus_best_professors_and_classes/"},
    {"n": 8, "kind": "reddit", "name": "Reddit r/SBU", "thread_id": "1c8ab9h",
     "desc": "Physics and math department best professors",
     "url": "https://www.reddit.com/r/SBU/comments/1c8ab9h/best_professors_in_physicsmath_departments_at_sbu/"},
    {"n": 9, "kind": "reddit", "name": "Reddit r/SBU", "thread_id": "16rueqm",
     "desc": "SBU professor quality discussion",
     "url": "https://www.reddit.com/r/SBU/comments/16rueqm/are_there_any_good_teachers_at_this_establishment/"},
    {"n": 10, "kind": "reddit", "name": "Reddit r/SBU", "thread_id": "1jz08ga",
     "desc": "Fall 25 professors opinions",
     "url": "https://www.reddit.com/r/SBU/comments/1jz08ga/fall_25_professors/"},
]

DELETED = {"[deleted]", "[removed]", "", None}
# How much of a parent comment to carry as context onto a reply.
PARENT_CONTEXT_CHARS = 240


# --------------------------------------------------------------------------- #
# Reddit -- parse saved shreddit HTML
# --------------------------------------------------------------------------- #
def _comment_body(comment, soup):
    """Body text of one shreddit-comment, excluding its nested replies.

    The body lives in `div#<thingid>-comment-rtjson-content`; looking it up by
    the comment's own thingid avoids accidentally grabbing a child reply's body.
    """
    thingid = comment.get("thingid", "")
    body_el = soup.find("div", id=f"{thingid}-comment-rtjson-content")
    if body_el is None:
        return ""
    return clean_text(body_el.get_text("\n"))


def parse_reddit_html(path):
    soup = BeautifulSoup(path.read_text(encoding="utf-8"), "lxml")
    post = soup.find("shreddit-post")
    title = clean_text(post.get("post-title", "")) if post else clean_text(path.stem)

    records = []

    # The submission itself.
    selftext = ""
    if post is not None:
        body_el = post.find(id=lambda x: x and x.endswith("-post-rtjson-content"))
        if body_el is not None:
            selftext = clean_text(body_el.get_text("\n"))
    post_text = f"{title}\n\n{selftext}".strip() if selftext else title
    records.append({
        "type": "post",
        "author": (post.get("author") if post else None) or "unknown",
        "score": int(post.get("score", 0)) if post and post.get("score") else 0,
        "depth": -1,
        "thread_title": title,
        "parent_author": "",
        "parent_text": "",
        "text": post_text,
    })

    # Every comment/reply. shreddit renders the whole tree, so find_all returns
    # them flat; each carries its own depth, and DOM nesting gives us the parent.
    for c in soup.find_all("shreddit-comment"):
        body = _comment_body(c, soup)
        if not body or body in DELETED:
            continue  # deleted/removed; its surviving children appear separately
        depth = int(c.get("depth", 0))
        parent = c.find_parent("shreddit-comment")
        parent_author, parent_text = "", ""
        if parent is not None:
            parent_author = parent.get("author") or "unknown"
            parent_text = _comment_body(parent, soup)[:PARENT_CONTEXT_CHARS]
        records.append({
            "type": "reply" if depth > 0 else "comment",
            "author": c.get("author") or "unknown",
            "score": int(c.get("score", 0)) if c.get("score") else 0,
            "depth": depth,
            "thread_title": title,
            "parent_author": parent_author,
            "parent_text": parent_text,
            "text": body,
        })
    return records


def find_reddit_html(thread_id):
    """Locate the saved HTML file for a thread by matching its permalink id."""
    for path in DOCS_DIR.glob("*.html"):
        head = path.read_text(encoding="utf-8")[:20000]
        if f"t3_{thread_id}" in head or f"/comments/{thread_id}/" in head:
            return path
    return None


def scrape_reddit(src):
    path = find_reddit_html(src["thread_id"])
    if path is None:
        print(f"    ! no saved HTML found for thread {src['thread_id']} "
              f"(save the page into {DOCS_DIR}/ as .html)")
        return []
    print(f"    reading saved page: {path.name}")
    return parse_reddit_html(path)


# --------------------------------------------------------------------------- #
# HTML sources -- render with Playwright (JS / bot-protected)
# --------------------------------------------------------------------------- #
def render_html(url, wait_selector=None, timeout_ms=45000):
    """Fetch a fully rendered page with headless Chromium.

    Uses domcontentloaded rather than networkidle: ad/analytics sockets on these
    sites keep the network "busy" forever, so networkidle never fires.
    """
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(
            user_agent=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/124.0 Safari/537.36"),
            locale="en-US",
        )
        page = ctx.new_page()
        page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
        if wait_selector:
            try:
                page.wait_for_selector(wait_selector, timeout=10000)
            except Exception:
                pass
        page.wait_for_timeout(4000)  # let client-side rendering settle
        # Scroll to trigger lazy-loaded reviews.
        try:
            page.mouse.wheel(0, 12000)
            page.wait_for_timeout(2000)
        except Exception:
            pass
        html = page.content()
        browser.close()
    return html


# --------------------------------------------------------------------------- #
# RateMyProfessors -- a single professor's page, all ratings loaded
# --------------------------------------------------------------------------- #
def _cls(pattern):
    return re.compile(pattern)


def render_rmp(url, max_clicks=100, timeout_ms=45000):
    """Load an RMP professor page and click "Load More Ratings" until it's gone,
    so every review is present in the returned HTML."""
    from playwright.sync_api import sync_playwright

    clicks = 0
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(
            user_agent=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/124.0 Safari/537.36"),
            locale="en-US",
        )
        page = ctx.new_page()
        page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
        page.wait_for_timeout(2500)

        # Dismiss the OneTrust cookie banner so it doesn't intercept clicks.
        for label in ("Reject All", "Allow All", "Accept All", "Close"):
            try:
                btn = page.query_selector(f"button:has-text('{label}')")
                if btn and btn.is_visible():
                    btn.click(timeout=3000)
                    page.wait_for_timeout(700)
                    break
            except Exception:
                pass

        while clicks < max_clicks:
            try:
                btn = page.query_selector("button:has-text('Load More Ratings')")
                if btn is None:
                    break
                btn.scroll_into_view_if_needed(timeout=3000)
                btn.click(timeout=4000)
                clicks += 1
                page.wait_for_timeout(1100)
            except Exception:
                break

        html = page.content()
        browser.close()
    print(f"    clicked 'Load More Ratings' {clicks}x")
    return html


def _card_of(comment_el):
    """Walk up from a comment to its enclosing rating <li> card."""
    node = comment_el
    for _ in range(10):
        if node.parent is None:
            break
        node = node.parent
        if node.name == "li":
            return node
    return comment_el.parent


def parse_rmp(html, src):
    soup = BeautifulSoup(html, "lxml")

    name_el = soup.find(class_=_cls("NameTitle__Name"))
    prof = clean_text(name_el.get_text(" ")) if name_el else src["desc"]
    dept_el = soup.find(class_=_cls("TeacherDepartment__StyledDepartmentLink"))
    dept = clean_text(dept_el.get_text(" ")) if dept_el else ""
    context = (f"{prof} ({dept}) on RateMyProfessors" if dept
               else f"{prof} on RateMyProfessors")

    records = []
    for cm in soup.find_all(class_=_cls("Comments__StyledComments")):
        comment = clean_text(cm.get_text(" "))
        if not comment:
            continue
        card = _card_of(cm)

        course_el = card.find(class_=_cls("RatingHeader__ClassInfoWrapper"))
        course = clean_text(course_el.get_text(" ")) if course_el else ""

        nums = [n.get_text(strip=True)
                for n in card.find_all(class_=_cls("CardNumRatingNumber"))]
        quality = nums[0] if nums else ""
        difficulty = nums[1] if len(nums) > 1 else ""

        grade = ""
        meta_el = card.find(class_=_cls("CourseMeta"))
        if meta_el:
            mg = re.search(r"Grade\s*:?\s*([A-FW][+-]?)\b",
                           meta_el.get_text(" ", strip=True))
            if mg:
                grade = mg.group(1)

        tags = [t.get_text(strip=True)
                for t in card.find_all(class_=_cls(r"Tag-bs9vf4"))]

        # Build a self-contained review: who/what course/ratings + the comment.
        head = f"Review of {prof}"
        if dept:
            head += f" ({dept})"
        if course:
            head += f", {course}"
        rating_bits = []
        if quality:
            rating_bits.append(f"Quality {quality}/5")
        if difficulty:
            rating_bits.append(f"Difficulty {difficulty}/5")
        if grade:
            rating_bits.append(f"Grade received: {grade}")
        text = head + ". "
        if rating_bits:
            text += ", ".join(rating_bits) + ". "
        text += comment
        if tags:
            text += " [Tags: " + ", ".join(tags) + "]"

        records.append({
            "type": "review",
            "author": "anonymous student",
            "score": 0,
            "depth": -1,
            "thread_title": context,
            "parent_author": "",
            "parent_text": "",
            "text": clean_text(text),
        })
    return records


def scrape_rmp(src):
    return parse_rmp(render_rmp(src["url"]), src)


def scrape_html(src):
    raw = render_html(src["url"])
    text, blocked = html_to_text(raw)
    if blocked:
        print(f"    ! page still looks bot-protected / thin "
              f"({len(text)} usable chars)")
    if not text:
        return []
    return [{
        "type": "review_page",
        "author": src["name"],
        "score": 0,
        "depth": -1,
        "thread_title": src["desc"],
        "parent_author": "",
        "parent_text": "",
        "text": text,
        "blocked": blocked,
    }]


def main():
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    summary = []
    for src in SOURCES:
        print(f"[{src['n']:>2}] {src['name']} -- {src['desc']}")
        try:
            handler = {"reddit": scrape_reddit, "rmp": scrape_rmp,
                       "html": scrape_html}[src["kind"]]
            records = handler(src)
        except Exception as exc:
            print(f"    ! FAILED: {type(exc).__name__}: {exc}")
            records = []

        for r in records:
            r["source"] = src["name"]
            r["source_desc"] = src["desc"]
            r["url"] = src["url"]
            r["source_n"] = src["n"]

        out_path = DOCS_DIR / f"{src['n']:02d}_{src['kind']}.json"
        out_path.write_text(json.dumps(records, ensure_ascii=False, indent=2),
                            encoding="utf-8")
        chars = sum(len(r["text"]) for r in records)
        print(f"    -> {len(records):>3} records, {chars:>6} chars  ({out_path.name})")
        summary.append((src["n"], src["desc"], len(records), chars))

    print("\nIngestion summary")
    print("-" * 64)
    for n, desc, recs, chars in summary:
        print(f"  {n:>2}. {recs:>4} records / {chars:>7} chars  {desc}")
    print(f"  total records: {sum(s[2] for s in summary)}")


if __name__ == "__main__":
    main()
