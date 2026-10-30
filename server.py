#!/usr/bin/env python3
"""Lightweight local development server for Job-Boards web UI.

Directly queries job-boards.db (SQLite) and serves the frontend SPA.
Zero external dependencies (uses standard library http.server and sqlite3).
"""

from datetime import datetime
import json
import mimetypes
import os
from pathlib import Path
import sqlite3
import sys
from urllib.parse import parse_qs, urlparse
from http.server import HTTPServer, BaseHTTPRequestHandler

HERE = Path(__file__).parent.resolve()
FRONTEND_DIR = HERE / "frontend"
DB_PATH = HERE / "job-boards.db"


def get_db():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con


class JobBoardsHandler(BaseHTTPRequestHandler):
    def send_json(self, data, status=200):
        body = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        params = parse_qs(parsed.query)

        if path == "/api/stats":
            self.handle_stats()
        elif path == "/api/companies":
            self.handle_companies()
        elif path == "/api/jobs":
            self.handle_jobs(params)
        elif path == "/api/standard-jobs":
            self.handle_standard_jobs(params)
        elif path == "/api/standard-job":
            self.handle_standard_job(params)
        elif path == "/job-boards.standard.json":
            self.serve_file(HERE / "job-boards.standard.json", "application/json; charset=utf-8")
        else:
            self.serve_static(path)

    def serve_file(self, file_path, content_type="application/json"):
        if not file_path.exists():
            return self.send_error(404, "File not found")
        content = file_path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(content)

    def handle_standard_job(self, params):
        source_id = params.get("id", [""])[0].strip() or params.get("source_id", [""])[0].strip()
        source = params.get("source", ["ats"])[0].strip()
        if not source_id:
            return self.send_json({"error": "id parameter required"}, 400)

        con = get_db()
        try:
            row = con.execute(
                "SELECT data_json FROM jobs_standard WHERE (source = ? AND source_id = ?) OR source_id = ?",
                (source, source_id, source_id),
            ).fetchone()
            if not row:
                return self.send_json({"error": "Job not found in standard schema"}, 404)
            self.send_json(json.loads(row["data_json"]))
        finally:
            con.close()

    def handle_standard_jobs(self, params):
        query = params.get("q", [""])[0].strip()
        company = params.get("company", [""])[0].strip()
        ats = params.get("ats", [""])[0].strip()

        try:
            page = max(1, int(params.get("page", ["1"])[0]))
        except ValueError:
            page = 1

        try:
            limit = min(200, max(1, int(params.get("limit", ["24"])[0])))
        except ValueError:
            limit = 24

        conditions = []
        sql_params = []

        if query:
            conditions.append("(title LIKE ? OR organization LIKE ? OR description LIKE ?)")
            term = f"%{query}%"
            sql_params.extend([term, term, term])

        if company:
            conditions.append("company_slug = ?")
            sql_params.append(company.lower())

        if ats and ats != "all":
            selected_ats = [a.strip().lower() for a in ats.split(",") if a.strip()]
            if selected_ats:
                placeholders = ",".join("?" * len(selected_ats))
                conditions.append(f"og_source IN ({placeholders})")
                sql_params.extend(selected_ats)

        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""

        con = get_db()
        try:
            (total,) = con.execute(f"SELECT COUNT(*) FROM jobs_standard {where_clause}", sql_params).fetchone()
            offset = (page - 1) * limit
            rows = con.execute(
                f"SELECT data_json FROM jobs_standard {where_clause} ORDER BY date_posted DESC LIMIT ? OFFSET ?",
                sql_params + [limit, offset],
            ).fetchall()

            jobs = [json.loads(r["data_json"]) for r in rows]
            pages = (total + limit - 1) // limit if limit else 1

            self.send_json({
                "jobs": jobs,
                "total": total,
                "page": page,
                "pages": pages,
                "limit": limit,
            })
        finally:
            con.close()

    def handle_stats(self):
        if not DB_PATH.exists():
            return self.send_json({"error": "Database not found. Run job_boards.py or seed_db.py first."}, 404)

        con = get_db()
        try:
            (total_jobs,) = con.execute("SELECT COUNT(*) FROM jobs").fetchone()
            (total_companies,) = con.execute("SELECT COUNT(DISTINCT company) FROM jobs").fetchone()
            (remote_jobs,) = con.execute("SELECT COUNT(*) FROM jobs WHERE isRemote = 'True'").fetchone()

            ats_counts = {
                r["ats"]: r["count"]
                for r in con.execute("SELECT ats, COUNT(*) as count FROM jobs GROUP BY ats")
            }

            top_companies = [
                {"company": r["company"], "count": r["count"], "ats": r["ats"]}
                for r in con.execute(
                    "SELECT company, ats, COUNT(*) as count FROM jobs GROUP BY company ORDER BY count DESC LIMIT 8"
                )
            ]

            (latest_published,) = con.execute(
                "SELECT MAX(publishedAt) FROM jobs WHERE publishedAt != ''"
            ).fetchone()

            self.send_json({
                "total_jobs": total_jobs,
                "total_companies": total_companies,
                "remote_jobs": remote_jobs,
                "ats_counts": ats_counts,
                "top_companies": top_companies,
                "latest_published": latest_published or "",
                "db_size_bytes": DB_PATH.stat().st_size,
            })
        finally:
            con.close()

    def handle_companies(self):
        if not DB_PATH.exists():
            return self.send_json([])

        con = get_db()
        try:
            companies = [
                {"company": r["company"], "ats": r["ats"], "count": r["count"]}
                for r in con.execute(
                    "SELECT company, ats, COUNT(*) as count FROM jobs GROUP BY company ORDER BY company ASC"
                )
            ]
            self.send_json(companies)
        finally:
            con.close()

    def handle_jobs(self, params):
        if not DB_PATH.exists():
            return self.send_json({"jobs": [], "total": 0, "page": 1, "pages": 0})

        query = params.get("q", [""])[0].strip()
        company = params.get("company", [""])[0].strip()
        ats = params.get("ats", [""])[0].strip()
        remote = params.get("remote", [""])[0].strip()
        sort_by = params.get("sort", ["recent"])[0].strip()

        try:
            page = max(1, int(params.get("page", ["1"])[0]))
        except ValueError:
            page = 1

        try:
            limit = min(200, max(1, int(params.get("limit", ["24"])[0])))
        except ValueError:
            limit = 24

        conditions = []
        sql_params = []

        if query:
            conditions.append(
                "(title LIKE ? OR company LIKE ? OR department LIKE ? OR location LIKE ?)"
            )
            term = f"%{query}%"
            sql_params.extend([term, term, term, term])

        if company:
            conditions.append("company = ?")
            sql_params.append(company)

        if ats and ats != "all":
            selected_ats = [a.strip() for a in ats.split(",") if a.strip()]
            if selected_ats:
                placeholders = ",".join("?" * len(selected_ats))
                conditions.append(f"ats IN ({placeholders})")
                sql_params.extend(selected_ats)

        if remote == "true":
            conditions.append("isRemote = 'True'")
        elif remote == "false":
            conditions.append("isRemote = 'False'")

        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""

        order_clause = "ORDER BY "
        if sort_by == "recent":
            order_clause += "CASE WHEN publishedAt != '' THEN 0 ELSE 1 END, publishedAt DESC, id ASC"
        elif sort_by == "oldest":
            order_clause += "CASE WHEN publishedAt != '' THEN 0 ELSE 1 END, publishedAt ASC, id ASC"
        elif sort_by == "company":
            order_clause += "company ASC, title ASC"
        elif sort_by == "title":
            order_clause += "title ASC, company ASC"
        else:
            order_clause += "last_seen DESC"

        con = get_db()
        try:
            count_sql = f"SELECT COUNT(*) FROM jobs {where_clause}"
            (total,) = con.execute(count_sql, sql_params).fetchone()

            offset = (page - 1) * limit
            select_sql = f"""
                SELECT ats, id, company, title, department, team, employmentType,
                       location, isRemote, workplaceType, publishedAt, jobUrl, first_seen, last_seen
                FROM jobs
                {where_clause}
                {order_clause}
                LIMIT ? OFFSET ?
            """
            rows = con.execute(select_sql, sql_params + [limit, offset]).fetchall()
            jobs = [dict(r) for r in rows]

            pages = (total + limit - 1) // limit if limit else 1
            self.send_json({
                "jobs": jobs,
                "total": total,
                "page": page,
                "pages": pages,
                "limit": limit,
            })
        finally:
            con.close()

    def serve_static(self, path):
        if path == "/" or not path:
            path = "/index.html"

        safe_path = Path(path.lstrip("/")).as_posix()
        target = FRONTEND_DIR / safe_path

        # Protect against path traversal
        try:
            target = target.resolve()
            if not str(target).startswith(str(FRONTEND_DIR)):
                self.send_error(403, "Forbidden")
                return
        except Exception:
            self.send_error(404, "Not Found")
            return

        if not target.is_file():
            # SPA fallback to index.html for unknown frontend routes
            target = FRONTEND_DIR / "index.html"
            if not target.is_file():
                self.send_error(404, "Frontend file not found")
                return

        content_type, _ = mimetypes.guess_type(str(target))
        if not content_type:
            content_type = "application/octet-stream"

        try:
            with open(target, "rb") as f:
                content = f.read()

            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(content)))
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            self.wfile.write(content)
        except OSError:
            self.send_error(500, "Internal Server Error")

    def log_message(self, format, *args):
        # Concise logging
        sys.stderr.write(f"[{datetime.now().strftime('%H:%M:%S')}] {args[0]} - {args[1]}\n")


def run(port=8000):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except AttributeError:
        pass
    server = HTTPServer(("127.0.0.1", port), JobBoardsHandler)
    print("==========================================================")
    print(f">> Job-Boards Local UI running at: http://localhost:{port}")
    print(f">> Connected to SQLite database: {DB_PATH.name}")
    print("==========================================================")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down server.")
        server.server_close()


if __name__ == "__main__":
    port = 8000
    if len(sys.argv) > 1 and sys.argv[1].isdigit():
        port = int(sys.argv[1])
    run(port)
