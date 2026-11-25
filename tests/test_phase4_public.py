"""
Tests for Phase 4: Public library, guest access, public member sign-up,
rate limit, honeypot, isolation, and auto-hide moderation.
"""

import io
import os
import tempfile
import pytest

from app import create_app
from db import get_db


@pytest.fixture
def app():
    """Create isolated test app for public library and public member tests."""
    db_fd, db_path = tempfile.mkstemp(suffix='.db')
    upload_dir = tempfile.mkdtemp()
    test_app = create_app({
        'TESTING': True,
        'DATABASE': db_path,
        'UPLOAD_FOLDER': upload_dir,
        'SECRET_KEY': 'public-test-secret',
        'ADMIN_EMAIL': 'admin@xyz.edu',
        'ALLOWED_DOMAINS': {
            'xyz.edu': 'XYZ University',
            'abc.edu': 'ABC College',
        },
        'PUBLIC_SIGNUPS_PER_HOUR_PER_IP': 3,
        'REPORTS_TO_AUTOHIDE': 3,
    })
    with test_app.app_context():
        db = get_db()
        from werkzeug.security import generate_password_hash
        pwd = generate_password_hash('password123')
        xyz_id = db.execute("SELECT id FROM universities WHERE domain = 'xyz.edu'").fetchone()['id']
        db.execute(
            "INSERT INTO users (email, username, password_hash, university_id, credits, is_admin) VALUES (?, ?, ?, ?, 20, 0)",
            ('alice@xyz.edu', 'alice', pwd, xyz_id)
        )
        db.execute(
            "INSERT INTO users (email, username, password_hash, university_id, credits, is_admin) VALUES (?, ?, ?, ?, 20, 0)",
            ('bob@xyz.edu', 'bob', pwd, xyz_id)
        )
        db.execute(
            "INSERT INTO users (email, username, password_hash, university_id, credits, is_admin) VALUES (?, ?, ?, ?, 20, 0)",
            ('carol@xyz.edu', 'carol', pwd, xyz_id)
        )
        db.execute(
            "INSERT INTO users (email, username, password_hash, university_id, credits, is_admin) VALUES (?, ?, ?, ?, 20, 1)",
            ('admin@xyz.edu', 'admin_xyz', pwd, xyz_id)
        )
        for uid in (1, 2, 3, 4):
            db.execute("INSERT INTO consents (user_id) VALUES (?)", (uid,))
        with open(os.path.join(upload_dir, 'priv.pdf'), 'wb') as f:
            f.write(b'%PDF-1.4\nprivate')
        with open(os.path.join(upload_dir, 'pub.pdf'), 'wb') as f:
            f.write(b'%PDF-1.4\npublic')
        db.execute(
            "INSERT INTO files (uploader_id, university_id, title, subject, semester, type, stored_name, original_name, size, status, visibility, content_hash) "
            "VALUES (1, ?, 'Private XYZ Doc', 'CS', 1, 'Summaries', 'priv.pdf', 'priv.pdf', 15, 'active', 'university', 'h_priv')",
            (xyz_id,)
        )
        db.execute(
            "INSERT INTO files (uploader_id, university_id, title, subject, semester, type, stored_name, original_name, size, status, visibility, license, content_hash) "
            "VALUES (1, ?, 'Public Open Guide', 'Math', 2, 'Lecture Notes', 'pub.pdf', 'pub.pdf', 15, 'active', 'public', 'cc_by', 'h_pub')",
            (xyz_id,)
        )
        db.commit()
    yield test_app
    os.close(db_fd)
    if os.path.exists(db_path):
        os.unlink(db_path)


def test_guest_library_and_detail_access(app):
    """Guests see active public files on /library and /library/<id>, never private files or preview/download."""
    client = app.test_client()

    res_list = client.get('/library')
    assert res_list.status_code == 200
    assert b'Public Open Guide' in res_list.data
    assert b'Private XYZ Doc' not in res_list.data
    assert b'Sign in to unlock' in res_list.data

    res_pub = client.get('/library/2')
    assert res_pub.status_code == 200
    assert b'Public Open Guide' in res_pub.data

    res_priv = client.get('/library/1')
    assert res_priv.status_code == 404

    # Guest cannot preview or download
    assert client.get('/preview/2').status_code == 302
    assert client.get('/download/2').status_code == 302

    # Landing page shows real public count
    res_home = client.get('/')
    assert res_home.status_code == 200
    assert b'Public library (1 resource)' in res_home.data


def test_public_signup_honeypot_ratelimit_and_isolation(app):
    """Public sign-up derives internal email, awards PUBLIC_SIGNUP_BONUS, enforces honeypot/rate limit, and isolates private files."""
    client = app.test_client()

    # Honeypot rejection
    res_hp = client.post('/register/public', data={
        'username': 'botuser',
        'password': 'password123',
        'agree_terms': 'on',
        'website': 'http://spam.example'
    })
    assert res_hp.status_code == 400

    # Valid public signup
    res_ok = client.post('/register/public', data={
        'username': 'pub_student1',
        'password': 'password123',
        'agree_terms': 'on',
    }, follow_redirects=True)
    assert res_ok.status_code == 200

    with app.app_context():
        db = get_db()
        u = db.execute("SELECT * FROM users WHERE username = 'pub_student1'").fetchone()
        assert u is not None
        assert u['email'] == 'pub_student1@eduspace.public'
        assert u['credits'] == 10

    # Consent and check isolation
    client.post('/consent', data={'agree_consent': 'on'}, follow_redirects=True)
    assert client.get('/file/1').status_code == 404
    assert client.get('/preview/1').status_code == 404
    assert client.get('/download/1').status_code == 404
    assert client.get('/file/2').status_code == 200
    dash = client.get('/dashboard')
    assert b'Public member' in dash.data

    # Domain check for public email
    dc = client.get('/api/domain-check?email=anyone@eduspace.public')
    assert dc.status_code == 200
    assert dc.get_json()['tier'] == 'public'

    # Rate limit check (limit=3 per IP, 1 already used above)
    client.post('/logout')
    for i in range(2, 4):
        r = client.post('/register/public', data={
            'username': f'pub_student{i}',
            'password': 'password123',
            'agree_terms': 'on',
        })
        assert r.status_code in (200, 302)
        client.post('/logout')
    r_limited = client.post('/register/public', data={
        'username': 'pub_student_over',
        'password': 'password123',
        'agree_terms': 'on',
    })
    assert r_limited.status_code == 429


def test_public_file_autohide_and_admin_restore(app):
    """3 distinct reporters auto-hide a public file; admin can restore it."""
    client = app.test_client()
    for email in ('alice@xyz.edu', 'bob@xyz.edu', 'carol@xyz.edu'):
        client.post('/login', data={'email': email, 'password': 'password123'})
        client.post('/file/2/report', data={'reason': 'Needs review'})
        client.post('/logout')

    with app.app_context():
        db = get_db()
        f = db.execute("SELECT status FROM files WHERE id = 2").fetchone()
        assert f['status'] == 'hidden'

    # Hidden file absent from /library
    assert client.get('/library/2').status_code == 404

    # Admin sees hidden file and restores it
    client.post('/login', data={'email': 'admin@xyz.edu', 'password': 'password123'})
    adm = client.get('/admin')
    assert b'Auto-Hidden Files' in adm.data
    assert b'Public Open Guide' in adm.data
    client.post('/admin/file/2/restore', follow_redirects=True)

    with app.app_context():
        db = get_db()
        f = db.execute("SELECT status FROM files WHERE id = 2").fetchone()
        assert f['status'] == 'active'
