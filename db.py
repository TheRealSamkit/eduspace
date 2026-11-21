import os
import sqlite3
from flask import g, current_app
from config import Config

def get_db():
    """Get a database connection from Flask application context."""
    if 'db' not in g:
        db_path = current_app.config.get('DATABASE', Config.DATABASE)
        # Ensure parent directory exists
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

def init_db(app=None):
    """Initialize the database with schema and default university records."""
    if app:
        db_path = app.config.get('DATABASE', Config.DATABASE)
        allowed_domains = app.config.get('ALLOWED_DOMAINS', Config.ALLOWED_DOMAINS)
        upload_folder = app.config.get('UPLOAD_FOLDER', Config.UPLOAD_FOLDER)
    else:
        db_path = Config.DATABASE
        allowed_domains = Config.ALLOWED_DOMAINS
        upload_folder = Config.UPLOAD_FOLDER

    # Ensure upload folder exists
    os.makedirs(upload_folder, exist_ok=True)

    db_dir = os.path.dirname(os.path.abspath(db_path))
    if db_dir and not os.path.exists(db_dir):
        os.makedirs(db_dir, exist_ok=True)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")

    schema_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'schema.sql')
    with open(schema_file, 'r', encoding='utf-8') as f:
        conn.executescript(f.read())

    # Populate allowed universities
    cursor = conn.cursor()

    # Safe migration: ensure theme column exists in users table
    try:
        cursor.execute("ALTER TABLE users ADD COLUMN theme TEXT NOT NULL DEFAULT 'light'")
        conn.commit()
    except Exception:
        pass

    for domain, name in allowed_domains.items():
        cursor.execute(
            "INSERT OR IGNORE INTO universities (name, domain) VALUES (?, ?)",
            (name, domain)
        )
        # Also ensure name matches if domain existed
        cursor.execute(
            "UPDATE universities SET name = ? WHERE domain = ?",
            (name, domain)
        )
    conn.commit()
    conn.close()

def init_app(app):
    """Register database teardown with Flask app and ensure database exists."""
    app.teardown_appcontext(close_db)
    # Automatically initialize DB schema on start
    init_db(app)
