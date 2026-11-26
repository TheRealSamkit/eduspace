"""
Tests for Phase 4: Unlock-gated /view/<id> endpoint and removal of limited preview config.
"""

import os
import tempfile
import pytest

from app import create_app
from config import Config
from db import get_db


@pytest.fixture
def app():
    """Create isolated test app with multiple universities, users, and files."""
    db_fd, db_path = tempfile.mkstemp(suffix='.db')
    upload_dir = tempfile.mkdtemp()
    test_app = create_app({
        'TESTING': True,
        'DATABASE': db_path,
        'UPLOAD_FOLDER': upload_dir,
        'SECRET_KEY': 'view-test-secret',
        'ADMIN_EMAIL': 'admin@xyz.edu',
        'ALLOWED_DOMAINS': {
            'xyz.edu': 'XYZ University',
            'abc.edu': 'ABC College',
        },
    })
    with test_app.app_context():
        db = get_db()
        from werkzeug.security import generate_password_hash
        pwd = generate_password_hash('password123')
        xyz_id = db.execute("SELECT id FROM universities WHERE domain = 'xyz.edu'").fetchone()['id']
        abc_id = db.execute("SELECT id FROM universities WHERE domain = 'abc.edu'").fetchone()['id']

        # 1: uploader@xyz.edu, 2: viewer@xyz.edu, 3: admin@xyz.edu, 4: outsider@abc.edu
        db.execute(
            "INSERT INTO users (email, username, password_hash, university_id, credits, is_admin) VALUES (?, ?, ?, ?, 30, 0)",
            ('uploader@xyz.edu', 'uploader', pwd, xyz_id)
        )
        db.execute(
            "INSERT INTO users (email, username, password_hash, university_id, credits, is_admin) VALUES (?, ?, ?, ?, 30, 0)",
            ('viewer@xyz.edu', 'viewer', pwd, xyz_id)
        )
        db.execute(
            "INSERT INTO users (email, username, password_hash, university_id, credits, is_admin) VALUES (?, ?, ?, ?, 30, 1)",
            ('admin@xyz.edu', 'admin', pwd, xyz_id)
        )
        db.execute(
            "INSERT INTO users (email, username, password_hash, university_id, credits, is_admin) VALUES (?, ?, ?, ?, 30, 0)",
            ('outsider@abc.edu', 'outsider', pwd, abc_id)
        )
        for uid in (1, 2, 3, 4):
            db.execute("INSERT INTO consents (user_id) VALUES (?)", (uid,))

        pdf_bytes = b'%PDF-1.4\nFULL_PDF_CONTENT_BYTES\n%%EOF'
        with open(os.path.join(upload_dir, 'notes.pdf'), 'wb') as f:
            f.write(pdf_bytes)
        with open(os.path.join(upload_dir, 'slides.pptx'), 'wb') as f:
            f.write(b'PK\x03\x04dummy_pptx')

        db.execute(
            "INSERT INTO files (uploader_id, university_id, title, subject, semester, type, stored_name, original_name, size, status, visibility, content_hash) "
            "VALUES (1, ?, 'Full PDF Notes', 'CS', 1, 'Lecture Notes', 'notes.pdf', 'notes.pdf', ?, 'active', 'university', 'hash_pdf')",
            (xyz_id, len(pdf_bytes))
        )
        db.execute(
            "INSERT INTO files (uploader_id, university_id, title, subject, semester, type, stored_name, original_name, size, status, visibility, content_hash) "
            "VALUES (1, ?, 'Slides PPTX', 'CS', 1, 'Lecture Notes', 'slides.pptx', 'slides.pptx', 14, 'active', 'university', 'hash_pptx')",
            (xyz_id,)
        )
        db.commit()
    yield test_app
    os.close(db_fd)
    if os.path.exists(db_path):
        os.unlink(db_path)


def test_config_has_no_preview_constants():
    """PREVIEW_LOCKED_PAGES and PREVIEW_IMAGE_MAX_PX are removed from Config."""
    assert not hasattr(Config, 'PREVIEW_LOCKED_PAGES')
    assert not hasattr(Config, 'PREVIEW_IMAGE_MAX_PX')


def test_view_file_access_matrix(app):
    """Verify /view/<id> across guest, other-uni, locked, uploader, downloader, and admin."""
    # 1. Guest -> login redirect
    guest_client = app.test_client()
    res_guest = guest_client.get('/view/1')
    assert res_guest.status_code == 302
    assert '/login' in res_guest.headers.get('Location', '')

    # 2. Other university -> 404
    abc_client = app.test_client()
    abc_client.post('/login', data={'email': 'outsider@abc.edu', 'password': 'password123'})
    assert abc_client.get('/view/1').status_code == 404

    # 3. Same-scope locked -> redirect to detail with warning toast and NO file bytes
    viewer_client = app.test_client()
    viewer_client.post('/login', data={'email': 'viewer@xyz.edu', 'password': 'password123'})
    res_locked = viewer_client.get('/view/1', follow_redirects=False)
    assert res_locked.status_code == 302
    assert '/file/1' in res_locked.headers.get('Location', '')
    assert b'FULL_PDF_CONTENT_BYTES' not in res_locked.data
    res_detail = viewer_client.get('/file/1')
    assert b'Unlock this file to view it' in res_detail.data

    # 4. Uploader -> 200 with full file and security headers
    uploader_client = app.test_client()
    uploader_client.post('/login', data={'email': 'uploader@xyz.edu', 'password': 'password123'})
    res_up = uploader_client.get('/view/1')
    assert res_up.status_code == 200
    assert b'FULL_PDF_CONTENT_BYTES' in res_up.data
    assert 'no-store' in res_up.headers.get('Cache-Control', '')
    assert res_up.headers.get('X-Content-Type-Options') == 'nosniff'

    # 5. Admin -> 200 with full file
    admin_client = app.test_client()
    admin_client.post('/login', data={'email': 'admin@xyz.edu', 'password': 'password123'})
    res_admin = admin_client.get('/view/1')
    assert res_admin.status_code == 200
    assert b'FULL_PDF_CONTENT_BYTES' in res_admin.data

    # 6. Unsupported type (for unlocked uploader) -> 415
    assert uploader_client.get('/view/2').status_code == 415

    # 7. Downloader -> downloads then views full file; 'file_view' event logged
    dl_res = viewer_client.get('/download/1')
    assert dl_res.status_code == 200
    assert b'FULL_PDF_CONTENT_BYTES' in dl_res.data
    res_unlocked = viewer_client.get('/view/1')
    assert res_unlocked.status_code == 200
    assert b'FULL_PDF_CONTENT_BYTES' in res_unlocked.data

    with app.app_context():
        db = get_db()
        evt = db.execute("SELECT * FROM events WHERE event_type = 'file_view'").fetchone()
        assert evt is not None
