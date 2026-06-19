"""
Morning Email — daily digest of fund manager insights and market commentary.
Fetches sources defined in sources.yaml, summarises with Claude, sends via Gmail.
"""

import os
import smtplib
import yaml
import feedparser
import requests
import google.generativeai as genai
from bs4 import BeautifulSoup
from datetime import datetime, timedelta, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

# ── Config ────────────────────────────────────────────────────────────────────

GMAIL_USER = os.environ["GMAIL_USER"]          # jlai5212@gmail.com
GMAIL_APP_PW = os.environ["GMAIL_APP_PW"]      # 16-char app password
GEMINI_KEY = os.environ["GEMINI_API_KEY"]
RECIPIENT = os.environ.get("RECIPIENT_EMAIL", GMAIL_USER)

genai.configure(api_key=GEMINI_KEY)

NITTER_INSTANCES = [
    "https://nitter.privacydev.net",
    "https://nitter.poast.org",
    "https://nitter.net",
]

LOOKBACK_HOURS = 48   # include articles published within this window
MAX_ITEMS_PER_SOURCE = 3
MAX_CONTENT_CHARS = 3000  # chars of article body sent to Claude per item

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0 Safari/537.36"
    )
}

# ── Helpers ───────────────────────────────────────────────────────────────────

def load_sources(path="sources.yaml"):
    with open(path) as f:
        raw = yaml.safe_load(f)
    sources = []
    for category, items in raw.items():
        for item in items:
            item["category"] = category
            sources.append(item)
    return sources


def within_window(entry):
    """Return True if a feedparser entry was published within LOOKBACK_HOURS."""
    for attr in ("published_parsed", "updated_parsed"):
        t = getattr(entry, attr, None)
        if t:
            pub = datetime(*t[:6], tzinfo=timezone.utc)
            cutoff = datetime.now(timezone.utc) - timedelta(hours=LOOKBACK_HOURS)
            return pub >= cutoff
    return True  # if no date, include it


def fetch_rss(url):
    feed = feedparser.parse(url)
    items = []
    for entry in feed.entries:
        if not within_window(entry):
            continue
        body = ""
        if hasattr(entry, "summary"):
            body = BeautifulSoup(entry.summary, "html.parser").get_text(" ", strip=True)
        items.append({
            "title": getattr(entry, "title", "Untitled"),
            "url": getattr(entry, "link", url),
            "body": body[:MAX_CONTENT_CHARS],
        })
        if len(items) >= MAX_ITEMS_PER_SOURCE:
            break
    return items


def fetch_nitter(handle):
    for instance in NITTER_INSTANCES:
        try:
            rss_url = f"{instance}/{handle}/rss"
            feed = feedparser.parse(rss_url)
            if not feed.entries:
                continue
            items = []
            for entry in feed.entries[:MAX_ITEMS_PER_SOURCE]:
                body = BeautifulSoup(
                    getattr(entry, "summary", ""), "html.parser"
                ).get_text(" ", strip=True)
                items.append({
                    "title": f"@{handle}: {body[:120]}",
                    "url": getattr(entry, "link", ""),
                    "body": body[:MAX_CONTENT_CHARS],
                })
            return items
        except Exception:
            continue
    return []


def extract_links_from_page(url, filter_kw=None):
    """Scrape a listing page and return href+text pairs for recent articles."""
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        r.raise_for_status()
    except Exception:
        return []

    soup = BeautifulSoup(r.text, "html.parser")
    candidates = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        text = a.get_text(strip=True)
        if not text or len(text) < 10:
            continue
        if filter_kw and filter_kw.lower() not in href.lower() and filter_kw.lower() not in text.lower():
            continue
        # Resolve relative URLs
        if href.startswith("/"):
            from urllib.parse import urlparse
            parsed = urlparse(url)
            href = f"{parsed.scheme}://{parsed.netloc}{href}"
        if href.startswith("http"):
            candidates.append((text, href))

    # Deduplicate by href
    seen = set()
    unique = []
    for text, href in candidates:
        if href not in seen:
            seen.add(href)
            unique.append((text, href))
    return unique[:MAX_ITEMS_PER_SOURCE * 4]


def fetch_article_body(url):
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        # Remove nav/footer/script noise
        for tag in soup(["nav", "footer", "script", "style", "header", "aside"]):
            tag.decompose()
        text = soup.get_text(" ", strip=True)
        return text[:MAX_CONTENT_CHARS]
    except Exception:
        return ""


def fetch_scrape(url, filter_kw=None):
    links = extract_links_from_page(url, filter_kw)
    items = []
    for title, href in links[:MAX_ITEMS_PER_SOURCE]:
        body = fetch_article_body(href)
        if len(body) < 100:
            continue
        items.append({"title": title, "url": href, "body": body})
    return items


# ── Fetching ──────────────────────────────────────────────────────────────────

def fetch_all(sources):
    results = []
    for src in sources:
        print(f"  Fetching: {src['name']} ({src['type']})")
        try:
            if src["type"] == "rss":
                items = fetch_rss(src["url"])
            elif src["type"] == "nitter":
                items = fetch_nitter(src["handle"])
            elif src["type"] == "scrape":
                items = fetch_scrape(src["url"], src.get("filter"))
            else:
                items = []
        except Exception as e:
            print(f"    ERROR: {e}")
            items = []

        for item in items:
            item["source"] = src["name"]
            item["category"] = src["category"]
        results.extend(items)

    return results


# ── Summarisation ─────────────────────────────────────────────────────────────

def build_prompt(items):
    sections = []
    for item in items:
        sections.append(
            f"SOURCE: {item['source']}\n"
            f"TITLE: {item['title']}\n"
            f"URL: {item['url']}\n"
            f"CONTENT:\n{item['body']}\n"
        )
    content_block = "\n---\n".join(sections)

    return f"""You are preparing a daily morning briefing for a sophisticated investor.

Below are articles, fund manager insights, and social media posts collected in the last 48 hours.

Your job:
1. Group content by theme (e.g. Macro & Global Markets, Australian Equities, Mining & Commodities, AI & Technology, Notable Twitter/X Posts).
2. For each item worth highlighting, write 2-4 sentences: what was said, why it matters, and any key data points or stock names mentioned.
3. Skip anything low-quality, repetitive, or lacking substance.
4. End with a "Key Themes Today" section: 3-5 bullet points on the biggest ideas across all sources.
5. Keep the tone professional, direct, and concise — no filler phrases.

FORMAT: Plain HTML suitable for an email. Use <h2> for section headings, <h3> for individual items with a hyperlink to the source, <p> for the summary, <ul>/<li> for the key themes. No CSS, no inline styles.

CONTENT:
{content_block}
"""


def summarise(items):
    model = genai.GenerativeModel("gemini-1.5-flash")
    prompt = build_prompt(items)
    response = model.generate_content(prompt)
    return response.text


# ── Email ─────────────────────────────────────────────────────────────────────

def send_email(html_body):
    today = datetime.now().strftime("%A, %d %B %Y")
    subject = f"Morning Briefing — {today}"

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = GMAIL_USER
    msg["To"] = RECIPIENT

    plain = "Your morning briefing is ready. Open in an HTML-capable email client to read it."
    msg.attach(MIMEText(plain, "plain"))

    full_html = f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="font-family: Georgia, serif; max-width: 700px; margin: 40px auto; color: #111; line-height: 1.6;">
  <p style="color: #888; font-size: 13px;">{today}</p>
  <h1 style="border-bottom: 2px solid #111; padding-bottom: 8px;">Morning Briefing</h1>
  {html_body}
  <hr style="margin-top: 40px;">
  <p style="color: #aaa; font-size: 11px;">Generated automatically. Sources: fund manager insights, newsletters, and curated Twitter/X accounts.</p>
</body>
</html>"""

    msg.attach(MIMEText(full_html, "html"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(GMAIL_USER, GMAIL_APP_PW)
        server.sendmail(GMAIL_USER, RECIPIENT, msg.as_string())

    print(f"  Email sent to {RECIPIENT}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print("=== Morning Email ===")
    print(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M')}")

    print("\n[1/3] Fetching sources...")
    sources = load_sources()
    items = fetch_all(sources)
    print(f"  Total items fetched: {len(items)}")

    if not items:
        print("  No items found. Exiting.")
        return

    print("\n[2/3] Summarising with Claude...")
    html_body = summarise(items)

    print("\n[3/3] Sending email...")
    send_email(html_body)

    print("\nDone.")


if __name__ == "__main__":
    main()
