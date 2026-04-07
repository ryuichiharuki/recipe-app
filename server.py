#!/usr/bin/env python3
"""
レシピアプリ サーバー — Python 標準ライブラリのみ使用（pip不要）
起動: python3 server.py
"""

import json
import mimetypes
import os
import re
import sqlite3
import threading
import urllib.request
import urllib.error
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse, parse_qs

BASE_DIR = Path(__file__).parent
DB_PATH  = BASE_DIR / 'db' / 'recipes.db'
PUBLIC   = BASE_DIR / 'public'
PORT     = int(os.environ.get('PORT', 3000))

# ===== DB =====
_local = threading.local()

def get_db():
    if not hasattr(_local, 'conn'):
        conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        _local.conn = conn
    return _local.conn

def init_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute('''
        CREATE TABLE IF NOT EXISTS recipes (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            url          TEXT    NOT NULL DEFAULT '',
            title        TEXT    NOT NULL,
            description  TEXT    DEFAULT '',
            image        TEXT    DEFAULT '',
            ingredients  TEXT    DEFAULT '[]',
            instructions TEXT    DEFAULT '',
            category     TEXT    DEFAULT '',
            tags         TEXT    DEFAULT '[]',
            memo         TEXT    DEFAULT '',
            created_at   DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at   DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()

def row_to_dict(row):
    d = dict(row)
    d['ingredients'] = json.loads(d.get('ingredients') or '[]')
    d['tags']        = json.loads(d.get('tags')        or '[]')
    return d


# ===== HTML Parser for recipe scraping =====
class RecipeParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self._ld_active  = False
        self._ld_buf     = []
        self._title_active = False
        self.ld_blocks   = []
        self.og           = {}
        self.page_title   = ''

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == 'script' and a.get('type') == 'application/ld+json':
            self._ld_active = True
            self._ld_buf = []
        if tag == 'title':
            self._title_active = True
        if tag == 'meta':
            prop    = a.get('property', '')
            name    = a.get('name', '')
            content = a.get('content', '')
            key = prop or name
            if key and content:
                self.og[key] = content

    def handle_endtag(self, tag):
        if tag == 'script' and self._ld_active:
            self._ld_active = False
            self.ld_blocks.append(''.join(self._ld_buf))
        if tag == 'title':
            self._title_active = False

    def handle_data(self, data):
        if self._ld_active:
            self._ld_buf.append(data)
        if self._title_active:
            self.page_title += data


def extract_recipe(url: str) -> dict:
    req = urllib.request.Request(url, headers={
        'User-Agent':      'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
        'Accept':          'text/html,application/xhtml+xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'ja,en;q=0.5',
    })
    with urllib.request.urlopen(req, timeout=15) as resp:
        raw = resp.read(5 * 1024 * 1024)  # 5 MB limit
        charset = resp.headers.get_content_charset('utf-8')
    html = raw.decode(charset, errors='replace')

    p = RecipeParser()
    p.feed(html)

    recipe = dict(url=url, title='', description='', image='', ingredients=[], instructions='')

    # --- JSON-LD (schema.org/Recipe) ---
    for block in p.ld_blocks:
        try:
            data = json.loads(block)
        except Exception:
            continue
        nodes = data if isinstance(data, list) else [data]
        # unwrap @graph
        flat = []
        for n in nodes:
            if isinstance(n, dict) and '@graph' in n:
                flat.extend(n['@graph'])
            else:
                flat.append(n)

        r = None
        for node in flat:
            if not isinstance(node, dict):
                continue
            t = node.get('@type', '')
            types = t if isinstance(t, list) else [t]
            if 'Recipe' in types:
                r = node
                break

        if not r:
            continue

        if r.get('name'):        recipe['title']       = r['name']
        if r.get('description'): recipe['description'] = r['description']

        img = r.get('image')
        if img:
            if isinstance(img, list): img = img[0]
            if isinstance(img, dict): img = img.get('url', '')
            recipe['image'] = str(img) if img else ''

        if r.get('recipeIngredient'):
            recipe['ingredients'] = [str(i) for i in r['recipeIngredient']]

        instr = r.get('recipeInstructions')
        if instr:
            if isinstance(instr, list):
                steps = []
                for i, s in enumerate(instr, 1):
                    text = s if isinstance(s, str) else (s.get('text', '') if isinstance(s, dict) else str(s))
                    steps.append(f'{i}. {text}')
                recipe['instructions'] = '\n'.join(steps)
            else:
                recipe['instructions'] = str(instr)

        if recipe['title']:
            break  # found a valid recipe block

    # --- OGP / meta fallback ---
    og = p.og
    if not recipe['title']:
        recipe['title'] = (og.get('og:title') or og.get('twitter:title') or
                           p.page_title.strip() or '無題のレシピ')
    if not recipe['description']:
        recipe['description'] = og.get('og:description') or og.get('description') or ''
    if not recipe['image']:
        recipe['image'] = og.get('og:image') or og.get('twitter:image') or ''

    recipe['title']       = re.sub(r'\s+', ' ', recipe['title']).strip()
    recipe['description'] = re.sub(r'\s+', ' ', recipe['description']).strip()
    return recipe


# ===== HTTP Handler =====
class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        print(f'  {self.address_string()} [{self.log_date_time_string()}] {fmt % args}')

    # --- helpers ---
    def send_json(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', len(body))
        self.end_headers()
        self.wfile.write(body)

    def err(self, status, msg):
        self.send_json({'error': msg}, status)

    def body(self):
        n = int(self.headers.get('Content-Length', 0))
        return json.loads(self.rfile.read(n)) if n else {}

    def qs(self, key=''):
        q = parse_qs(urlparse(self.path).query)
        return q.get(key, [''])[0] if key else q

    # --- GET ---
    def do_GET(self):
        path = urlparse(self.path).path

        # GET /api/recipes
        if path == '/api/recipes':
            db   = get_db()
            sql  = 'SELECT * FROM recipes WHERE 1=1'
            args = []
            cat  = self.qs('category')
            srch = self.qs('search')
            tag  = self.qs('tag')
            if cat:  sql += ' AND category = ?';                             args += [cat]
            if srch: sql += ' AND (title LIKE ? OR description LIKE ? OR memo LIKE ?)'; q=f'%{srch}%'; args += [q,q,q]
            sql += ' ORDER BY created_at DESC'
            rows = [row_to_dict(r) for r in db.execute(sql, args).fetchall()]
            if tag: rows = [r for r in rows if tag in r['tags']]
            return self.send_json(rows)

        # GET /api/recipes/:id
        m = re.fullmatch(r'/api/recipes/(\d+)', path)
        if m:
            row = get_db().execute('SELECT * FROM recipes WHERE id=?', (m.group(1),)).fetchone()
            return self.send_json(row_to_dict(row)) if row else self.err(404, 'Not found')

        # GET /api/meta
        if path == '/api/meta':
            rows = get_db().execute('SELECT category, tags FROM recipes').fetchall()
            cats = sorted({r['category'] for r in rows if r['category']})
            tags = sorted({t for r in rows for t in json.loads(r['tags'] or '[]')})
            return self.send_json({'categories': cats, 'tags': tags})

        # Static files
        if path == '/': path = '/index.html'
        fp = PUBLIC / path.lstrip('/')
        if fp.exists() and fp.is_file():
            data = fp.read_bytes()
            mime, _ = mimetypes.guess_type(str(fp))
            self.send_response(200)
            self.send_header('Content-Type', mime or 'application/octet-stream')
            self.send_header('Content-Length', len(data))
            self.end_headers()
            self.wfile.write(data)
        else:
            self.err(404, 'Not found')

    # --- POST ---
    def do_POST(self):
        path = urlparse(self.path).path
        b    = self.body()

        if path == '/api/fetch':
            url = b.get('url', '').strip()
            if not url: return self.err(400, 'URLが必要です')
            try:
                self.send_json(extract_recipe(url))
            except Exception as e:
                self.err(500, f'取得に失敗しました: {e}')
            return

        if path == '/api/recipes':
            db  = get_db()
            cur = db.execute('''
                INSERT INTO recipes (url,title,description,image,ingredients,instructions,category,tags,memo)
                VALUES (?,?,?,?,?,?,?,?,?)
            ''', (b.get('url',''), b.get('title',''), b.get('description',''), b.get('image',''),
                  json.dumps(b.get('ingredients',[])), b.get('instructions',''),
                  b.get('category',''), json.dumps(b.get('tags',[])), b.get('memo','')))
            db.commit()
            row = db.execute('SELECT * FROM recipes WHERE id=?', (cur.lastrowid,)).fetchone()
            return self.send_json(row_to_dict(row))

        self.err(404, 'Not found')

    # --- PUT ---
    def do_PUT(self):
        m = re.fullmatch(r'/api/recipes/(\d+)', urlparse(self.path).path)
        if not m: return self.err(404, 'Not found')
        b  = self.body()
        db = get_db()
        db.execute('''
            UPDATE recipes
            SET title=?,description=?,image=?,ingredients=?,instructions=?,
                category=?,tags=?,memo=?,updated_at=CURRENT_TIMESTAMP
            WHERE id=?
        ''', (b.get('title',''), b.get('description',''), b.get('image',''),
              json.dumps(b.get('ingredients',[])), b.get('instructions',''),
              b.get('category',''), json.dumps(b.get('tags',[])), b.get('memo',''),
              m.group(1)))
        db.commit()
        row = db.execute('SELECT * FROM recipes WHERE id=?', (m.group(1),)).fetchone()
        self.send_json(row_to_dict(row)) if row else self.err(404, 'Not found')

    # --- DELETE ---
    def do_DELETE(self):
        m = re.fullmatch(r'/api/recipes/(\d+)', urlparse(self.path).path)
        if not m: return self.err(404, 'Not found')
        db = get_db()
        db.execute('DELETE FROM recipes WHERE id=?', (m.group(1),))
        db.commit()
        self.send_json({'success': True})


if __name__ == '__main__':
    init_db()
    httpd = ThreadingHTTPServer(('', PORT), Handler)
    print(f'\n🍳 レシピアプリ起動中 → http://localhost:{PORT}\n')
    print('停止するには Ctrl+C を押してください\n')
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print('\n停止しました')
