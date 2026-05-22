import os
import sqlite3
import time

from flask import Flask, jsonify, render_template, request

app = Flask(__name__)
DATABASE_URL = os.environ.get("DATABASE_URL")
DB_PATH = os.environ.get("DB_PATH", "/data/tasks.db")
USE_POSTGRES = bool(DATABASE_URL)


def get_db_sqlite():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def get_db_postgres():
    import psycopg2
    from psycopg2.extras import RealDictCursor

    return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)


def init_db():
    if USE_POSTGRES:
        for attempt in range(30):
            try:
                conn = get_db_postgres()
                with conn:
                    with conn.cursor() as cur:
                        cur.execute(
                            """
                            CREATE TABLE IF NOT EXISTS tasks (
                                id SERIAL PRIMARY KEY,
                                title TEXT NOT NULL
                            )
                            """
                        )
                conn.close()
                return
            except Exception:
                time.sleep(1)
        print("Nu se poate conecta la PostgreSQL", flush=True)
        return
    os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)
    with get_db_sqlite() as conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS tasks (id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL)"
        )
        conn.commit()


def fetch_tasks():
    if USE_POSTGRES:
        conn = get_db_postgres()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT id, title FROM tasks ORDER BY id")
                return cur.fetchall()
        finally:
            conn.close()
    with get_db_sqlite() as conn:
        return conn.execute("SELECT id, title FROM tasks ORDER BY id").fetchall()


def insert_task(title):
    if USE_POSTGRES:
        conn = get_db_postgres()
        try:
            with conn:
                with conn.cursor() as cur:
                    cur.execute("INSERT INTO tasks (title) VALUES (%s) RETURNING id", (title,))
                    row = cur.fetchone()
                    return row["id"], title
        finally:
            conn.close()
    with get_db_sqlite() as conn:
        cur = conn.execute("INSERT INTO tasks (title) VALUES (?)", (title,))
        conn.commit()
        return cur.lastrowid, title


def remove_task(task_id):
    if USE_POSTGRES:
        conn = get_db_postgres()
        try:
            with conn:
                with conn.cursor() as cur:
                    cur.execute("DELETE FROM tasks WHERE id = %s", (task_id,))
                    return cur.rowcount
        finally:
            conn.close()
    with get_db_sqlite() as conn:
        cur = conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
        conn.commit()
        return cur.rowcount


@app.get("/")
def home():
    return render_template("index.html")


@app.get("/health")
def health():
    return jsonify({"status": "ok", "database": "postgresql" if USE_POSTGRES else "sqlite"})


@app.get("/tasks")
def list_tasks():
    rows = fetch_tasks()
    return jsonify([{"id": r["id"], "title": r["title"]} for r in rows])


@app.post("/tasks")
def create_task():
    data = request.get_json(silent=True) or {}
    title = (data.get("title") or request.form.get("title") or "").strip()
    if not title:
        return jsonify({"error": "title is required"}), 400
    task_id, title = insert_task(title)
    return jsonify({"id": task_id, "title": title}), 201


@app.delete("/tasks/<int:task_id>")
def delete_task(task_id):
    if remove_task(task_id) == 0:
        return jsonify({"error": "not found"}), 404
    return jsonify({"deleted": task_id})


try:
    init_db()
except Exception as exc:
    print(f"init_db: {exc}", flush=True)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
