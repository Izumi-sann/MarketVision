from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Iterable

DB_DIR = Path("data")
DB_FILE = DB_DIR / "marketvision.db"


def init_db(db_path: str | None = None) -> str:
    path = Path(db_path) if db_path else DB_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS posts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            account TEXT NOT NULL,
            shortcode TEXT,
            post_url TEXT,
            post_type TEXT,
            posted_at TEXT,
            likes INTEGER,
            comments INTEGER,
            views INTEGER,
            caption TEXT,
            snapshot_at TEXT NOT NULL
        )
        """
    )
    conn.commit()
    conn.close()
    return str(path)


def save_posts_snapshot(account: str, posts: Iterable[object], db_path: str | None = None) -> int:
    path = db_path or str(DB_FILE)
    snapshot_at = datetime.utcnow().isoformat()
    conn = sqlite3.connect(path)
    cur = conn.cursor()
    inserted = 0
    for p in posts:
        cur.execute(
            "INSERT INTO posts (account, shortcode, post_url, post_type, posted_at, likes, comments, views, caption, snapshot_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                getattr(p, "username", account),
                getattr(p, "shortcode", None),
                getattr(p, "post_url", None),
                getattr(p, "post_type", None),
                getattr(p, "posted_at", None).isoformat() if getattr(p, "posted_at", None) is not None else None,
                getattr(p, "likes", None),
                getattr(p, "comments", None),
                getattr(p, "views", None),
                getattr(p, "caption", None),
                snapshot_at,
            ),
        )
        inserted += 1
    conn.commit()
    conn.close()
    return inserted


def fetch_snapshots(account: str, db_path: str | None = None) -> list[dict]:
    path = db_path or str(DB_FILE)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT * FROM posts WHERE account = ? ORDER BY snapshot_at DESC, posted_at DESC", (account,))
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


def list_accounts(db_path: str | None = None) -> list[str]:
    path = db_path or str(DB_FILE)
    conn = sqlite3.connect(path)
    cur = conn.cursor()
    cur.execute("SELECT DISTINCT account FROM posts ORDER BY account")
    rows = [r[0] for r in cur.fetchall()]
    conn.close()
    return rows
