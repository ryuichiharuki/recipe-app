"""
Shared helpers for all Vercel API handlers.
"""
import datetime
import json
import os
import re
import urllib.request
from html.parser import HTMLParser

import psycopg2
from psycopg2.extras import RealDictCursor

_DDL = """
CREATE TABLE IF NOT EXISTS recipes (
    id           BIGSERIAL PRIMARY KEY,
    url          TEXT      NOT NULL DEFAULT '',
    title        TEXT      NOT NULL,
    description  TEXT      DEFAULT '',
    image        TEXT      DEFAULT '',
    ingredients  TEXT      DEFAULT '[]',
    instructions TEXT      DEFAULT '',
    category     TEXT      DEFAULT '',
    tags         TEXT      DEFAULT '[]',
    memo         TEXT      DEFAULT '',
    created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
"""

_table_ready = False


def get_conn():
    return psycopg2.connect(os.environ["DATABASE_URL"], cursor_factory=RealDictCursor)


def ensure_table():
    global _table_ready
    if _table_ready:
        return
    c = get_conn()
    try:
        c.cursor().execute(_DDL)
        c.commit()
        _table_ready = True
    finally:
        c.close()


def row_to_dict(row):
    d = dict(row)
    d["ingredients"] = json.loads(d.get("ingredients") or "[]")
    d["tags"] = json.loads(d.get("tags") or "[]")
    # datetime → ISO string for JSON serialization
    for k, v in list(d.items()):
        if isinstance(v, (datetime.datetime, datetime.date)):
            d[k] = v.isoformat(sep=" ", timespec="seconds")
    return d


# ─── Recipe HTML Scraper ──────────────────────────────────────────────────────

class _RecipeParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self._ld = False
        self._ld_buf = []
        self._title = False
        self.ld_blocks = []
        self.og = {}
        self.page_title = ""

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "script" and a.get("type") == "application/ld+json":
            self._ld = True; self._ld_buf = []
        if tag == "title":
            self._title = True
        if tag == "meta":
            key = a.get("property") or a.get("name", "")
            val = a.get("content", "")
            if key and val:
                self.og[key] = val

    def handle_endtag(self, tag):
        if tag == "script" and self._ld:
            self._ld = False
            self.ld_blocks.append("".join(self._ld_buf))
        if tag == "title":
            self._title = False

    def handle_data(self, data):
        if self._ld:    self._ld_buf.append(data)
        if self._title: self.page_title += data


def extract_recipe(url: str) -> dict:
    req = urllib.request.Request(url, headers={
        "User-Agent":      "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        "Accept":          "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "ja,en;q=0.5",
    })
    with urllib.request.urlopen(req, timeout=15) as resp:
        raw     = resp.read(5 * 1024 * 1024)
        charset = resp.headers.get_content_charset("utf-8")
    html = raw.decode(charset, errors="replace")

    p = _RecipeParser()
    p.feed(html)

    recipe = dict(url=url, title="", description="", image="", ingredients=[], instructions="")

    for block in p.ld_blocks:
        try:
            data = json.loads(block)
        except Exception:
            continue
        nodes = data if isinstance(data, list) else [data]
        flat  = []
        for n in nodes:
            flat.extend(n["@graph"]) if isinstance(n, dict) and "@graph" in n else flat.append(n)

        r = None
        for node in flat:
            if not isinstance(node, dict): continue
            t = node.get("@type", "")
            if "Recipe" in (t if isinstance(t, list) else [t]):
                r = node; break
        if not r:
            continue

        if r.get("name"):        recipe["title"]       = r["name"]
        if r.get("description"): recipe["description"] = r["description"]

        img = r.get("image")
        if img:
            if isinstance(img, list): img = img[0]
            if isinstance(img, dict): img = img.get("url", "")
            recipe["image"] = str(img) if img else ""

        if r.get("recipeIngredient"):
            recipe["ingredients"] = [str(i) for i in r["recipeIngredient"]]

        instr = r.get("recipeInstructions")
        if instr:
            if isinstance(instr, list):
                steps = []
                for i, s in enumerate(instr, 1):
                    text = s if isinstance(s, str) else (s.get("text", "") if isinstance(s, dict) else str(s))
                    steps.append(f"{i}. {text}")
                recipe["instructions"] = "\n".join(steps)
            elif isinstance(instr, str):
                recipe["instructions"] = instr

        if recipe["title"]:
            break

    og = p.og
    if not recipe["title"]:
        recipe["title"] = og.get("og:title") or og.get("twitter:title") or p.page_title.strip() or "無題のレシピ"
    if not recipe["description"]:
        recipe["description"] = og.get("og:description") or og.get("description") or ""
    if not recipe["image"]:
        recipe["image"] = og.get("og:image") or og.get("twitter:image") or ""

    recipe["title"]       = re.sub(r"\s+", " ", recipe["title"]).strip()
    recipe["description"] = re.sub(r"\s+", " ", recipe["description"]).strip()
    return recipe
