"""
Database connection management, schema initialization, and safe migrations for EduSpace.
"""

import hashlib
import logging
import os
import sqlite3
from flask import g, current_app
from config import Config

logger = logging.getLogger(__name__)


def get_db():
    """Get a database connection from Flask application context."""
    if 'db' not in g:
        db_path = current_app.config.get('DATABASE', Config.DATABASE)
        db_dir = os.path.dirname(os.path.abspath(db_path))
        if db_dir and not os.path.exists(db_dir):
            os.makedirs(db_dir, exist_ok=True)

        g.db = sqlite3.connect(db_path)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON;")
    return g.db


def close_db(e=None):
    """Close the database connection if open."""
    db = g.pop('db', None)
    if db is not None:
        db.close()


def _get_table_columns(conn, table_name):
    """Return set of column names for an existing table, or empty set if missing."""
    rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    return {row['name'] for row in rows}


def _get_table_sql(conn, table_name):
    """Return CREATE TABLE SQL from sqlite_master or None."""
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name=?",
        (table_name,)
    ).fetchone()
    return row['sql'] if row else None


def _rebuild_files_table(conn):
    """Rebuild files table to support 'hidden' status, visibility, content_hash, and license."""
    existing_cols = _get_table_columns(conn, 'files')
    before_count = conn.execute("SELECT COUNT(*) FROM files").fetchone()[0]

    vis_expr = "visibility" if "visibility" in existing_cols else "'university'"
    hash_expr = "content_hash" if "content_hash" in existing_cols else "NULL"
    lic_expr = "license" if "license" in existing_cols else "NULL"

    conn.execute("PRAGMA foreign_keys = OFF;")
    try:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute("""
            CREATE TABLE files_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                uploader_id INTEGER NOT NULL REFERENCES users(id),
                university_id INTEGER NOT NULL REFERENCES universities(id),
                title TEXT NOT NULL,
                subject TEXT NOT NULL,
                semester INTEGER NOT NULL,
                type TEXT NOT NULL,
                description TEXT,
                stored_name TEXT NOT NULL,
                original_name TEXT NOT NULL,
                size INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active', 'hidden', 'removed')),
                visibility TEXT NOT NULL DEFAULT 'university' CHECK(visibility IN ('university', 'public')),
                content_hash TEXT,
                license TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute(f"""
            INSERT INTO files_new (
                id, uploader_id, university_id, title, subject, semester, type,
                description, stored_name, original_name, size, status,
                visibility, content_hash, license, created_at
            )
            SELECT
                id, uploader_id, university_id, title, subject, semester, type,
                description, stored_name, original_name, size, status,
                {vis_expr}, {hash_expr}, {lic_expr}, created_at
            FROM files
        """)
        after_count = conn.execute("SELECT COUNT(*) FROM files_new").fetchone()[0]
        if before_count != after_count:
            raise RuntimeError(f"files migration row count mismatch: {before_count} != {after_count}")
        conn.execute("DROP TABLE files")
        conn.execute("ALTER TABLE files_new RENAME TO files")
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.execute("PRAGMA foreign_keys = ON;")


def _rebuild_ledger_table(conn):
    """Rebuild ledger table to allow 'request_reward' in reason CHECK constraint."""
    before_count = conn.execute("SELECT COUNT(*) FROM ledger").fetchone()[0]
    conn.execute("PRAGMA foreign_keys = OFF;")
    try:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute("""
            CREATE TABLE ledger_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL REFERENCES users(id),
                amount INTEGER NOT NULL,
                reason TEXT NOT NULL CHECK(reason IN ('signup', 'upload', 'download', 'reversal', 'request_reward')),
                file_id INTEGER REFERENCES files(id),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("""
            INSERT INTO ledger_new (id, user_id, amount, reason, file_id, created_at)
            SELECT id, user_id, amount, reason, file_id, created_at FROM ledger
        """)
        after_count = conn.execute("SELECT COUNT(*) FROM ledger_new").fetchone()[0]
        if before_count != after_count:
            raise RuntimeError(f"ledger migration row count mismatch: {before_count} != {after_count}")
        conn.execute("DROP TABLE ledger")
        conn.execute("ALTER TABLE ledger_new RENAME TO ledger")
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.execute("PRAGMA foreign_keys = ON;")


def _migrate_existing_tables(conn):
    """Upgrade an existing pre-v2 database schema safely without data loss."""
    uni_cols = _get_table_columns(conn, 'universities')
    if uni_cols and 'kind' not in uni_cols:
        conn.execute("ALTER TABLE universities ADD COLUMN kind TEXT NOT NULL DEFAULT 'partner'")
        conn.commit()

    user_cols = _get_table_columns(conn, 'users')
    if user_cols and 'theme' not in user_cols:
        conn.execute("ALTER TABLE users ADD COLUMN theme TEXT NOT NULL DEFAULT 'light'")
        conn.commit()

    files_sql = _get_table_sql(conn, 'files')
    if files_sql and ("'hidden'" not in files_sql or 'visibility' not in _get_table_columns(conn, 'files')):
        _rebuild_files_table(conn)

    ledger_sql = _get_table_sql(conn, 'ledger')
    if ledger_sql and "'request_reward'" not in ledger_sql:
        _rebuild_ledger_table(conn)


def _backfill_content_hashes(conn, upload_folder):
    """Compute SHA-256 content_hash for existing files that lack one."""
    rows = conn.execute("SELECT id, stored_name FROM files WHERE content_hash IS NULL").fetchall()
    if not rows:
        return
    for row in rows:
        path = os.path.join(upload_folder, row['stored_name'])
        if not os.path.isfile(path):
            logger.warning("Missing file on disk during hash backfill: id=%s path=%s", row['id'], path)
            continue
        h = hashlib.sha256()
        with open(path, 'rb') as f:
            for chunk in iter(lambda: f.read(65536), b''):
                h.update(chunk)
        conn.execute("UPDATE files SET content_hash = ? WHERE id = ?", (h.hexdigest(), row['id']))
    conn.commit()


def _seed_universities(conn, allowed_domains, public_domain, public_name):
    """Ensure partner universities and the single public university exist."""
    for domain, name in allowed_domains.items():
        conn.execute(
            "INSERT OR IGNORE INTO universities (name, domain, kind) VALUES (?, ?, 'partner')",
            (name, domain)
        )
        conn.execute(
            "UPDATE universities SET name = ?, kind = 'partner' WHERE domain = ?",
            (name, domain)
        )

    existing_public = conn.execute("SELECT id FROM universities WHERE kind = 'public'").fetchone()
    if existing_public:
        conn.execute(
            "UPDATE universities SET name = ?, domain = ? WHERE id = ?",
            (public_name, public_domain, existing_public['id'])
        )
    else:
        conn.execute(
            "INSERT OR IGNORE INTO universities (name, domain, kind) VALUES (?, ?, 'public')",
            (public_name, public_domain)
        )
        conn.execute(
            "UPDATE universities SET name = ?, kind = 'public' WHERE domain = ?",
            (public_name, public_domain)
        )
    conn.commit()


def init_db(app=None):
    """Initialize the database with schema, safe migrations, and default university records."""
    cfg = app.config if app else {}
    db_path = cfg.get('DATABASE', Config.DATABASE)
    allowed_domains = cfg.get('ALLOWED_DOMAINS', Config.ALLOWED_DOMAINS)
    upload_folder = cfg.get('UPLOAD_FOLDER', Config.UPLOAD_FOLDER)
    public_domain = cfg.get('PUBLIC_EMAIL_DOMAIN', Config.PUBLIC_EMAIL_DOMAIN)
    public_name = cfg.get('PUBLIC_UNI_NAME', Config.PUBLIC_UNI_NAME)

    os.makedirs(upload_folder, exist_ok=True)
    db_dir = os.path.dirname(os.path.abspath(db_path))
    if db_dir and not os.path.exists(db_dir):
        os.makedirs(db_dir, exist_ok=True)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")

    _migrate_existing_tables(conn)

    schema_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'schema.sql')
    with open(schema_file, 'r', encoding='utf-8') as f:
        conn.executescript(f.read())

    _seed_universities(conn, allowed_domains, public_domain, public_name)
    _backfill_content_hashes(conn, upload_folder)
    conn.close()


def init_app(app):
    """Register database teardown with Flask app and ensure database exists."""
    app.teardown_appcontext(close_db)
    init_db(app)
