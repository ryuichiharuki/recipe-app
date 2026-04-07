"""
GET    /api/recipes/:id  — fetch one
PUT    /api/recipes/:id  — update
DELETE /api/recipes/:id  — delete
"""
import json
import re
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse
from _shared import ensure_table, get_conn, row_to_dict


def _get_id(path: str):
    m = re.search(r"/api/recipes/(\d+)", path)
    return int(m.group(1)) if m else None


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

    def _body(self):
        n = int(self.headers.get("Content-Length", 0))
        return json.loads(self.rfile.read(n)) if n else {}

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,PUT,DELETE,OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        ensure_table()
        id_ = _get_id(self.path)
        c = get_conn()
        try:
            cur = c.cursor()
            cur.execute("SELECT * FROM recipes WHERE id = %s", (id_,))
            row = cur.fetchone()
            self._json(row_to_dict(row) if row else {"error": "Not found"}, 200 if row else 404)
        except Exception as e:
            self._json({"error": str(e)}, 500)
        finally:
            c.close()

    def do_PUT(self):
        ensure_table()
        id_ = _get_id(self.path)
        b   = self._body()
        c   = get_conn()
        try:
            cur = c.cursor()
            cur.execute(
                "UPDATE recipes"
                " SET title=%s,description=%s,image=%s,ingredients=%s,instructions=%s,"
                "     category=%s,tags=%s,memo=%s,updated_at=CURRENT_TIMESTAMP"
                " WHERE id=%s RETURNING *",
                (b.get("title",""), b.get("description",""), b.get("image",""),
                 json.dumps(b.get("ingredients",[])), b.get("instructions",""),
                 b.get("category",""), json.dumps(b.get("tags",[])), b.get("memo",""),
                 id_)
            )
            c.commit()
            row = cur.fetchone()
            self._json(row_to_dict(row) if row else {"error": "Not found"}, 200 if row else 404)
        except Exception as e:
            self._json({"error": str(e)}, 500)
        finally:
            c.close()

    def do_DELETE(self):
        id_ = _get_id(self.path)
        c   = get_conn()
        try:
            c.cursor().execute("DELETE FROM recipes WHERE id = %s", (id_,))
            c.commit()
            self._json({"success": True})
        except Exception as e:
            self._json({"error": str(e)}, 500)
        finally:
            c.close()
