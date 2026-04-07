"""
GET /api/meta  — all categories and tags (for filter UI)
"""
import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from http.server import BaseHTTPRequestHandler
from _shared import ensure_table, get_conn


class handler(BaseHTTPRequestHandler):
    def log_message(self, *a): pass

    def _json(self, data, code=200):
        b = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", len(b))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        ensure_table()
        c = get_conn()
        try:
            cur = c.cursor()
            cur.execute("SELECT category, tags FROM recipes")
            rows = cur.fetchall()
            cats = sorted({r["category"] for r in rows if r["category"]})
            tags = sorted({t for r in rows for t in json.loads(r["tags"] or "[]")})
            self._json({"categories": cats, "tags": tags})
        except Exception as e:
            self._json({"error": str(e)}, 500)
        finally:
            c.close()
