"""
GET    /api/recipes        — list (filters: category, tag, search)
POST   /api/recipes        — create
GET    /api/recipes/:id    — fetch one
PUT    /api/recipes/:id    — update
DELETE /api/recipes/:id    — delete
"""
import json
import re
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from _shared import ensure_table, get_conn, row_to_dict


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

    def _id(self):
        qs = parse_qs(urlparse(self.path).query)
        ids = qs.get("id", [])
        return int(ids[0]) if ids else None

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,PUT,DELETE,OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        ensure_table()
        id_ = self._id()

        c = get_conn()
        try:
            cur = c.cursor()
            # Single recipe
            if id_:
                cur.execute("SELECT * FROM recipes WHERE id = %s", (id_,))
                row = cur.fetchone()
                return self._json(row_to_dict(row) if row else {"error": "Not found"}, 200 if row else 404)

            # List
            qs = parse_qs(urlparse(self.path).query)
            p  = lambda k: qs.get(k, [""])[0]
            sql, args = "SELECT * FROM recipes WHERE 1=1", []
            if p("category"):
                sql += " AND category = %s"; args.append(p("category"))
            if p("search"):
                q = f"%{p('search')}%"
                sql += " AND (title ILIKE %s OR description ILIKE %s OR memo ILIKE %s)"
                args.extend([q, q, q])
            sql += " ORDER BY created_at DESC"
            cur.execute(sql, args)
            rows = [row_to_dict(r) for r in cur.fetchall()]
            if p("tag"):
                rows = [r for r in rows if p("tag") in r["tags"]]
            self._json(rows)
        except Exception as e:
            self._json({"error": str(e)}, 500)
        finally:
            c.close()

    def do_POST(self):
        ensure_table()
        b = self._body()
        c = get_conn()
        try:
            cur = c.cursor()
            cur.execute(
                "INSERT INTO recipes (url,title,description,image,ingredients,instructions,category,tags,memo)"
                " VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *",
                (b.get("url",""), b.get("title",""), b.get("description",""), b.get("image",""),
                 json.dumps(b.get("ingredients",[])), b.get("instructions",""),
                 b.get("category",""), json.dumps(b.get("tags",[])), b.get("memo",""))
            )
            c.commit()
            self._json(row_to_dict(cur.fetchone()))
        except Exception as e:
            self._json({"error": str(e)}, 500)
        finally:
            c.close()

    def do_PUT(self):
        ensure_table()
        id_ = self._id()
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
        id_ = self._id()
        c   = get_conn()
        try:
            c.cursor().execute("DELETE FROM recipes WHERE id = %s", (id_,))
            c.commit()
            self._json({"success": True})
        except Exception as e:
            self._json({"error": str(e)}, 500)
        finally:
            c.close()
