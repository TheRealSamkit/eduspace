"""
Tests for Phase 3: Server-enforced PDF & image preview, caching, and error handling.
"""

import io
import os
import tempfile
import pytest
from PIL import Image
from pypdf import PdfReader, PdfWriter

from app import create_app
from db import get_db


def _make_multipage_pdf(num_pages):
    writer = PdfWriter()
    for _ in range(num_pages):
        writer.add_blank_page(width=200, height=200)
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


def _make_png(width, height):
    img = Image.new('RGB', (width, height), color=(20, 90, 180))
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    return buf.getvalue()


@pytest.fixture
def app():
    """Create isolated test app with multi-page PDF, large PNG, corrupt PDF, and DOCX."""
    db_fd, db_path = tempfile.mkstemp(suffix='.db')
    upload_dir = tempfile.mkdtemp()
    test_app = create_app({
        'TESTING': True,
        'DATABASE': db_path,
        'UPLOAD_FOLDER': upload_dir,
        'SECRET_KEY': 'preview-test-secret',
        'ADMIN_EMAIL': 'admin@xyz.edu',
        'ALLOWED_DOMAINS': {'xyz.edu': 'XYZ University'},
    })
    with test_app.app_context():
        db = get_db()
        from werkzeug.security import generate_password_hash
        pwd = generate_password_hash('password123')
        xyz_id = db.execute("SELECT id FROM universities WHERE domain = 'xyz.edu'").fetchone()['id']
        db.execute(
            "INSERT INTO users (email, username, password_hash, university_id, credits, is_admin) VALUES (?, ?, ?, ?, 30, 0)",
            ('uploader@xyz.edu', 'uploader', pwd, xyz_id)
        )
        db.execute(
            "INSERT INTO users (email, username, password_hash, university_id, credits, is_admin) VALUES (?, ?, ?, ?, 30, 0)",
            ('viewer@xyz.edu', 'viewer', pwd, xyz_id)
        )
        db.execute("INSERT INTO consents (user_id) VALUES (1)")
        db.execute("INSERT INTO consents (user_id) VALUES (2)")

        pdf_bytes = _make_multipage_pdf(6)
        with open(os.path.join(upload_dir, 'six.pdf'), 'wb') as f:
            f.write(pdf_bytes)
        img_bytes = _make_png(1800, 1200)
        with open(os.path.join(upload_dir, 'big.png'), 'wb') as f:
            f.write(img_bytes)
        with open(os.path.join(upload_dir, 'corrupt.pdf'), 'wb') as f:
            f.write(b'%PDF-1.4\nnot-actually-valid-pdf')
        with open(os.path.join(upload_dir, 'slides.pptx'), 'wb') as f:
            f.write(b'PK\x03\x04dummy')

        db.execute(
            "INSERT INTO files (uploader_id, university_id, title, subject, semester, type, stored_name, original_name, size, status, visibility, content_hash) "
            "VALUES (1, ?, 'Six Page PDF', 'CS', 1, 'Lecture Notes', 'six.pdf', 'six.pdf', ?, 'active', 'university', 'hash_six')",
            (xyz_id, len(pdf_bytes))
        )
        db.execute(
            "INSERT INTO files (uploader_id, university_id, title, subject, semester, type, stored_name, original_name, size, status, visibility, content_hash) "
            "VALUES (1, ?, 'Big Diagram', 'CS', 1, 'Summaries', 'big.png', 'big.png', ?, 'active', 'university', 'hash_big')",
            (xyz_id, len(img_bytes))
        )
        db.execute(
            "INSERT INTO files (uploader_id, university_id, title, subject, semester, type, stored_name, original_name, size, status, visibility, content_hash) "
            "VALUES (1, ?, 'Corrupt PDF', 'CS', 1, 'Summaries', 'corrupt.pdf', 'corrupt.pdf', 30, 'active', 'university', 'hash_corrupt')",
            (xyz_id,)
        )
        db.execute(
            "INSERT INTO files (uploader_id, university_id, title, subject, semester, type, stored_name, original_name, size, status, visibility, content_hash) "
            "VALUES (1, ?, 'Slides PPTX', 'CS', 1, 'Lecture Notes', 'slides.pptx', 'slides.pptx', 10, 'active', 'university', 'hash_pptx')",
            (xyz_id,)
        )
        db.commit()
    yield test_app
    os.close(db_fd)
    if os.path.exists(db_path):
        os.unlink(db_path)


def test_locked_and_unlocked_pdf_and_image_preview(app):
    """Locked PDF has only 3 pages; unlocked/downloaded has 6; locked image is downscaled."""
    client = app.test_client()
    client.post('/login', data={'email': 'viewer@xyz.edu', 'password': 'password123'})

    # Locked PDF preview -> 3 pages, headers set, credits unchanged
    res_pdf = client.get('/preview/1')
    assert res_pdf.status_code == 200
    assert 'no-store' in res_pdf.headers.get('Cache-Control', '')
    assert res_pdf.headers.get('X-Content-Type-Options') == 'nosniff'
    reader = PdfReader(io.BytesIO(res_pdf.data))
    assert len(reader.pages) == 3

    # Locked image preview -> max 900px on longest side
    res_img = client.get('/preview/2')
    assert res_img.status_code == 200
    with Image.open(io.BytesIO(res_img.data)) as img:
        assert max(img.size) <= 900

    # Corrupt PDF -> 422, not 500
    res_corrupt = client.get('/preview/3')
    assert res_corrupt.status_code == 422

    # Unsupported PPTX -> 415
    res_pptx = client.get('/preview/4')
    assert res_pptx.status_code == 415

    # Download file 1 -> unlocks full 6 pages for preview
    dl_res = client.get('/download/1')
    assert dl_res.status_code == 200
    assert len(PdfReader(io.BytesIO(dl_res.data)).pages) == 6

    res_unlocked = client.get('/preview/1')
    assert res_unlocked.status_code == 200
    assert len(PdfReader(io.BytesIO(res_unlocked.data)).pages) == 6

    with app.app_context():
        db = get_db()
        evt = db.execute("SELECT * FROM events WHERE event_type = 'preview_open'").fetchone()
        assert evt is not None
