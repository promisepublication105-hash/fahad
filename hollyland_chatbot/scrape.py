"""Crawl the college website and build the chatbot's knowledge file.

Usage:
    python hollyland_chatbot/scrape.py                       # default site
    python hollyland_chatbot/scrape.py https://example.edu.bd --max-pages 60

It visits pages on the same host only, pulls out the readable text, splits it
into short passages and writes them to knowledge.js next to index.html. The
hand-written topic entries in topics.json are kept as they are; the bot
answers from the scraped passages first and only falls back to a topic's
demo answer when nothing was scraped.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from collections import deque
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urldefrag, urljoin, urlparse

import requests

HERE = Path(__file__).resolve().parent
DEFAULT_SITE = "https://www.hollylandcollege.com"
SKIP_TAGS = {"script", "style", "noscript", "svg", "head", "iframe", "form"}
BLOCK_TAGS = {"p", "div", "li", "br", "tr", "h1", "h2", "h3", "h4", "h5", "h6",
              "section", "article", "td", "th", "header", "footer", "table"}
SKIP_EXT = re.compile(r"\.(pdf|jpe?g|png|gif|webp|svg|zip|rar|docx?|xlsx?|pptx?|mp4|mp3)$", re.I)


class PageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.links: list[str] = []
        self.title = ""
        self._parts: list[str] = []
        self._skip = 0
        self._in_title = False

    def handle_starttag(self, tag, attrs):
        if tag in SKIP_TAGS:
            self._skip += 1
        if tag == "title":
            self._in_title = True
        if tag == "a":
            href = dict(attrs).get("href")
            if href:
                self.links.append(href)
        if tag in BLOCK_TAGS:
            self._parts.append("\n")

    def handle_endtag(self, tag):
        if tag in SKIP_TAGS and self._skip:
            self._skip -= 1
        if tag == "title":
            self._in_title = False
        if tag in BLOCK_TAGS:
            self._parts.append("\n")

    def handle_data(self, data):
        if self._in_title:
            self.title += data
        elif not self._skip:
            self._parts.append(data)

    @property
    def text(self) -> str:
        raw = "".join(self._parts)
        lines = [re.sub(r"\s+", " ", ln).strip() for ln in raw.splitlines()]
        return "\n".join(ln for ln in lines if ln)


def split_passages(text: str, size: int = 450) -> list[str]:
    """Group lines into passages of roughly `size` characters."""
    out, cur = [], ""
    for line in text.splitlines():
        if len(cur) + len(line) > size and cur:
            out.append(cur.strip())
            cur = ""
        cur += line + "\n"
    if cur.strip():
        out.append(cur.strip())
    return [p for p in out if len(p) > 25]


def crawl(start: str, max_pages: int, delay: float) -> list[dict]:
    host = urlparse(start).netloc.removeprefix("www.")
    queue, seen, pages = deque([start]), {start}, []
    session = requests.Session()
    session.headers["User-Agent"] = "college-demo-chatbot/1.0"

    while queue and len(pages) < max_pages:
        url = queue.popleft()
        try:
            resp = session.get(url, timeout=20)
        except requests.RequestException as exc:
            print(f"  ! {url}: {exc}", file=sys.stderr)
            continue
        if resp.status_code != 200 or "html" not in resp.headers.get("content-type", ""):
            continue
        resp.encoding = resp.apparent_encoding or resp.encoding
        parser = PageParser()
        parser.feed(resp.text)
        pages.append({"url": url, "title": parser.title.strip(), "text": parser.text})
        print(f"  ✓ {url}  ({len(parser.text)} chars)")

        for href in parser.links:
            link = urldefrag(urljoin(url, href))[0]
            p = urlparse(link)
            if p.scheme in ("http", "https") and p.netloc.removeprefix("www.") == host \
                    and not SKIP_EXT.search(p.path) and link not in seen:
                seen.add(link)
                queue.append(link)
        time.sleep(delay)
    return pages


def find_contacts(text: str) -> dict:
    phones = re.findall(r"(?:\+?88)?0?1[3-9]\d{2}[-\s]?\d{6}|\b0\d{1,3}[-\s]?\d{6,8}\b", text)
    emails = re.findall(r"[\w.+-]+@[\w-]+\.[\w.]+", text)
    return {"phones": sorted(set(phones))[:5], "emails": sorted(set(emails))[:5]}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("site", nargs="?", default=DEFAULT_SITE)
    ap.add_argument("--max-pages", type=int, default=40)
    ap.add_argument("--delay", type=float, default=0.5, help="seconds between requests")
    args = ap.parse_args()

    print(f"Crawling {args.site} …")
    pages = crawl(args.site, args.max_pages, args.delay)
    if not pages:
        sys.exit("No pages could be read; knowledge.js was left unchanged.")

    chunks = [{"url": pg["url"], "title": pg["title"], "text": passage}
              for pg in pages for passage in split_passages(pg["text"])]
    all_text = "\n".join(pg["text"] for pg in pages)
    home_title = pages[0]["title"] or urlparse(args.site).netloc

    kb = {
        "meta": {
            "name": home_title,
            "source": args.site,
            "scraped_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "pages": len(pages),
            "demo": False,
            **find_contacts(all_text),
        },
        "topics": json.loads((HERE / "topics.json").read_text(encoding="utf-8")),
        "chunks": chunks,
    }
    out = HERE / "knowledge.js"
    out.write_text("window.COLLEGE_KB = " + json.dumps(kb, ensure_ascii=False, indent=1) + ";\n",
                   encoding="utf-8")
    print(f"Wrote {len(chunks)} passages from {len(pages)} pages to {out}")


if __name__ == "__main__":
    main()
