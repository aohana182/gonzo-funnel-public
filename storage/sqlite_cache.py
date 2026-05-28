import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class SqliteCache:
    def __init__(self, path: str = "./cache.sqlite"):
        self._path = path
        self._init_schema()

    @contextmanager
    def _conn(self):
        conn = sqlite3.connect(self._path, timeout=30)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _init_schema(self) -> None:
        # WAL must be set outside a transaction — executescript auto-commits, but the
        # PRAGMA itself must not be inside an implicit transaction on some SQLite builds.
        with sqlite3.connect(self._path, timeout=30) as wal_conn:
            wal_conn.execute("PRAGMA journal_mode=WAL")
        with self._conn() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS scorer_cache (
                    vc_name TEXT NOT NULL,
                    thesis_hash TEXT NOT NULL,
                    dossier_hash TEXT NOT NULL,
                    score_json TEXT NOT NULL,
                    cached_at TEXT NOT NULL,
                    PRIMARY KEY (vc_name, thesis_hash, dossier_hash)
                );
                CREATE TABLE IF NOT EXISTS vcs_seen (
                    name TEXT PRIMARY KEY,
                    url TEXT,
                    first_seen_at TEXT NOT NULL,
                    last_researched_at TEXT,
                    airtable_record_id TEXT
                );
                CREATE TABLE IF NOT EXISTS run_log (
                    run_id TEXT PRIMARY KEY,
                    started_at TEXT NOT NULL,
                    ended_at TEXT,
                    status TEXT,
                    total_cost_usd REAL,
                    total_tokens_in INTEGER,
                    total_tokens_out INTEGER,
                    vcs_scouted INTEGER,
                    vcs_researched INTEGER,
                    drafts_written INTEGER
                );
            """)

    # --- scorer_cache ---

    def get_cached_score(self, vc_name: str, thesis_hash: str, dossier_hash: str) -> str | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT score_json FROM scorer_cache WHERE vc_name=? AND thesis_hash=? AND dossier_hash=?",
                (vc_name, thesis_hash, dossier_hash),
            ).fetchone()
            return row["score_json"] if row else None

    def set_cached_score(self, vc_name: str, thesis_hash: str, dossier_hash: str, score_json: str) -> None:
        with self._conn() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO scorer_cache
                   (vc_name, thesis_hash, dossier_hash, score_json, cached_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (vc_name, thesis_hash, dossier_hash, score_json, _now()),
            )

    # --- vcs_seen ---

    def add_vc_seen(self, name: str, url: str | None = None) -> None:
        with self._conn() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO vcs_seen (name, url, first_seen_at) VALUES (?, ?, ?)",
                (name, url, _now()),
            )

    def get_vc_seen(self, name: str) -> dict | None:
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM vcs_seen WHERE name = ?", (name,)).fetchone()
            return dict(row) if row else None

    def get_all_seen_names(self) -> list[str]:
        with self._conn() as conn:
            rows = conn.execute("SELECT name FROM vcs_seen").fetchall()
            return [r["name"] for r in rows]

    def update_last_researched(self, name: str) -> None:
        with self._conn() as conn:
            conn.execute(
                "UPDATE vcs_seen SET last_researched_at = ? WHERE name = ?",
                (_now(), name),
            )

    def update_airtable_record_id(self, name: str, record_id: str) -> None:
        with self._conn() as conn:
            conn.execute(
                "UPDATE vcs_seen SET airtable_record_id = ? WHERE name = ?",
                (record_id, name),
            )

    def get_stale_vcs(self, ttl_days: int) -> list[dict]:
        cutoff = datetime.now(timezone.utc).isoformat()[:10]  # date part
        with self._conn() as conn:
            rows = conn.execute(
                """SELECT * FROM vcs_seen
                   WHERE last_researched_at IS NULL
                      OR date(last_researched_at) < date(?, ?)""",
                (cutoff, f"-{ttl_days} days"),
            ).fetchall()
            return [dict(r) for r in rows]

    # --- run_log ---

    def start_run(self, run_id: str) -> None:
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO run_log (run_id, started_at, status) VALUES (?, ?, 'running')",
                (run_id, _now()),
            )

    def end_run(
        self,
        run_id: str,
        status: str,
        total_cost_usd: float | None,
        total_tokens_in: int,
        total_tokens_out: int,
        vcs_scouted: int,
        vcs_researched: int,
        drafts_written: int,
    ) -> None:
        with self._conn() as conn:
            conn.execute(
                """UPDATE run_log SET
                    ended_at=?, status=?, total_cost_usd=?,
                    total_tokens_in=?, total_tokens_out=?,
                    vcs_scouted=?, vcs_researched=?, drafts_written=?
                   WHERE run_id=?""",
                (_now(), status, total_cost_usd, total_tokens_in, total_tokens_out,
                 vcs_scouted, vcs_researched, drafts_written, run_id),
            )

