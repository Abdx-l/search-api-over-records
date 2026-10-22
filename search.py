"""FTS5-backed record search, keyset cursor, and relevance evaluation."""
import argparse
import base64
import json
import sqlite3
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit


SCHEMA = """
CREATE TABLE IF NOT EXISTS records(id TEXT PRIMARY KEY,name TEXT NOT NULL,body TEXT NOT NULL,state TEXT,role TEXT,org_type TEXT);
CREATE VIRTUAL TABLE IF NOT EXISTS record_fts USING fts5(id UNINDEXED,name,body);
"""


def connect(path):
    db = sqlite3.connect(path)
    db.row_factory = sqlite3.Row
    db.executescript(SCHEMA)
    return db


def load(db, records):
    with db:
        for item in records:
            values = tuple(item.get(key, "") for key in ("id", "name", "body", "state", "role", "org_type"))
            if not values[0] or not values[1]:
                raise ValueError("id and name required")
            db.execute("INSERT OR REPLACE INTO records VALUES(?,?,?,?,?,?)", values)
            db.execute("DELETE FROM record_fts WHERE id=?", (values[0],))
            db.execute("INSERT INTO record_fts(id,name,body) VALUES(?,?,?)", values[:3])


def encode_cursor(score, ident):
    return base64.urlsafe_b64encode(json.dumps([score, ident]).encode()).decode().rstrip("=")


def decode_cursor(token):
    try:
        score, ident = json.loads(base64.urlsafe_b64decode(token + "=" * (-len(token) % 4)))
        return float(score), str(ident)
    except Exception:
        raise ValueError("invalid cursor") from None


def search(db, query, filters=None, limit=10, cursor=None):
    if not query.strip() or not 1 <= limit <= 100:
        raise ValueError("query required and limit must be 1..100")
    filters = filters or {}
    where = ["record_fts MATCH ?"]
    args = [query]
    for field in ("state", "role", "org_type"):
        if filters.get(field):
            where.append(f"r.{field}=?")
            args.append(filters[field])
    # FTS5 bm25 yields lower numbers for stronger matches.
    sql = f"SELECT r.*,bm25(record_fts,0,6.0,1.0) AS score FROM record_fts JOIN records r ON r.id=record_fts.id WHERE {' AND '.join(where)} ORDER BY score ASC,r.id ASC"
    rows = [dict(row) for row in db.execute(sql, args)]
    if cursor:
        marker = decode_cursor(cursor)
        rows = [row for row in rows if (row["score"], row["id"]) > marker]
    page = rows[:limit]
    return {"results": page, "next_cursor": encode_cursor(page[-1]["score"], page[-1]["id"]) if len(rows) > limit else None}


def mrr(db, labels):
    scores = []
    for entry in labels:
        hits = search(db, entry["query"], limit=100)["results"]
        rank = next((i for i, row in enumerate(hits, 1) if row["id"] == entry["expected_id"]), None)
        scores.append(1 / rank if rank else 0)
    return sum(scores) / len(scores) if scores else 0


def serve(db_path, port):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if urlsplit(self.path).path != "/search":
                self.send_error(404)
                return
            params = {key: value[-1] for key, value in parse_qs(urlsplit(self.path).query).items()}
            try:
                with connect(db_path) as db:
                    payload = search(db, params.get("q", ""), params, int(params.get("limit", 10)), params.get("cursor"))
                status = 200
            except (ValueError, sqlite3.OperationalError) as exc:
                payload, status = {"error": str(exc)}, 400
            raw = json.dumps(payload).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("command", choices=["load", "serve", "evaluate"])
    p.add_argument("file", nargs="?")
    p.add_argument("--db", default="records.db")
    p.add_argument("--port", type=int, default=8080)
    a = p.parse_args()
    if a.command == "serve":
        serve(a.db, a.port)
    elif not a.file:
        p.error("load and evaluate need a JSON file")
    else:
        with connect(a.db) as db:
            data = json.loads(Path(a.file).read_text(encoding="utf-8"))
            if a.command == "load":
                load(db, data)
                print(f"Loaded {len(data)} records")
            else:
                print(json.dumps({"mean_reciprocal_rank": mrr(db, data)}))


if __name__ == "__main__":
    main()

