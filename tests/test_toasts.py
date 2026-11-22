"""
Tests for Phase 2 Toast notification rendering and alert elimination.

Asserts:
- After register, upload, download (success and insufficient credits), login failure, and logout,
  the response HTML (after following redirects) contains a .toast with the right category and message text.
- Contains no leftover .alert flash banner anywhere.
"""

import io
import os
import sys
import tempfile
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import create_app
from db import init_db, get_db


@pytest.fixture
def app_instance():
    """Create test application instance with temporary database."""
    db_fd, db_path = tempfile.mkstemp(suffix='.db')
    upload_dir = tempfile.mkdtemp()

    test_config = {
        'TESTING': True,
        'DATABASE': db_path,
        'UPLOAD_FOLDER': upload_dir,
        'SECRET_KEY': 'toast-test-secret',
        'ADMIN_EMAIL': 'admin@xyz.edu',
        'ALLOWED_DOMAINS': {
            'xyz.edu': 'XYZ University',
            'abc.edu': 'ABC College'
        },
        'SIGNUP_BONUS': 20,
        'UPLOAD_REWARD': 10,
        'DOWNLOAD_COST': 5,
        'MAX_REWARDED_UPLOADS_PER_DAY': 3,
        'MAX_FILE_MB': 10,
        'MAX_CONTENT_LENGTH': 10 * 1024 * 1024,
        'ALLOWED_EXT': {'pdf', 'pptx', 'docx', 'png', 'jpg'}
    }

    app = create_app(test_config)

    with app.app_context():
        init_db(app)

    yield app

    os.close(db_fd)
    if os.path.exists(db_path):
        os.remove(db_path)
    for root, dirs, files in os.walk(upload_dir, topdown=False):
        for f in files:
            os.remove(os.path.join(root, f))
        os.rmdir(root)


@pytest.fixture
def client(app_instance):
    return app_instance.test_client()


def test_toast_on_registration(client):
    """After register, response contains a .toast with success category and no .alert flash banner."""
    res = client.post('/register', data={
        'username': 'toast_user',
        'email': 'toast@xyz.edu',
        'password': 'password123',
        'agree_terms': '1'
    }, follow_redirects=True)

    html = res.data.decode('utf-8')
    assert 'class="toast' in html or "class='toast" in html or "toast align-items-center" in html
    assert 'text-bg-success' in html
    assert 'Welcome to StudyExchange, toast_user!' in html
    # Ensure no leftover flash .alert
    assert 'alert-dismissible' not in html
    assert 'alert-success' not in html


def test_toast_on_login_failure(client):
    """After login failure, response contains a .toast with danger category and no .alert flash banner."""
    res = client.post('/login', data={
        'email': 'nonexistent@xyz.edu',
        'password': 'wrongpassword'
    }, follow_redirects=True)

    html = res.data.decode('utf-8')
    assert 'toast' in html
    assert 'text-bg-danger' in html
    assert 'Invalid email or password' in html
    assert 'alert-dismissible' not in html
    assert 'alert-danger' not in html


def test_toast_on_logout(client):
    """After logout, response contains a .toast with info category and no .alert flash banner."""
    # Register and login first
    client.post('/register', data={
        'username': 'logout_user',
        'email': 'logout@xyz.edu',
        'password': 'password123',
        'agree_terms': '1'
    }, follow_redirects=True)

    res = client.post('/logout', follow_redirects=True)
    html = res.data.decode('utf-8')
    assert 'toast' in html
    assert 'text-bg-info' in html
    assert 'You have been logged out' in html
    assert 'alert-dismissible' not in html
    assert 'alert-info' not in html


def test_toast_on_upload(client):
    """After upload, response contains a .toast with success category and no .alert flash banner."""
    client.post('/register', data={
        'username': 'uploader_user',
        'email': 'uploader@xyz.edu',
        'password': 'password123',
        'agree_terms': '1'
    }, follow_redirects=True)
    client.post('/consent', data={'agree_consent': '1'}, follow_redirects=True)

    res = client.post('/upload', data={
        'title': 'Algorithms Summary',
        'subject': 'Computer Science',
        'semester': '2',
        'type': 'Study Guide',
        'description': 'Algorithms notes.',
        'confirm_copyright': '1',
        'file': (io.BytesIO(b'%PDF-1.4 dummy pdf'), 'algo.pdf')
    }, follow_redirects=True)

    html = res.data.decode('utf-8')
    assert 'toast' in html
    assert 'text-bg-success' in html
    assert 'Material uploaded successfully!' in html
    assert 'alert-dismissible' not in html
    assert 'alert-success' not in html


def test_toast_on_download_insufficient_credits(client, app_instance):
    """After download attempt with insufficient credits, response contains a .toast with danger category."""
    # User 1 uploads file
    client.post('/register', data={
        'username': 'author_user',
        'email': 'author@xyz.edu',
        'password': 'password123',
        'agree_terms': '1'
    }, follow_redirects=True)
    client.post('/consent', data={'agree_consent': '1'}, follow_redirects=True)

    client.post('/upload', data={
        'title': 'Discrete Math',
        'subject': 'Mathematics',
        'semester': '1',
        'type': 'Lecture Notes',
        'description': 'Math notes.',
        'confirm_copyright': '1',
        'file': (io.BytesIO(b'%PDF-1.4 dummy pdf'), 'math.pdf')
    }, follow_redirects=True)

    with app_instance.app_context():
        db = get_db()
        file_row = db.execute("SELECT id FROM files WHERE title = 'Discrete Math'").fetchone()
        file_id = file_row['id']

    # User 2 logs in and drains credits to 0
    client.post('/logout', follow_redirects=True)
    client.post('/register', data={
        'username': 'poor_user',
        'email': 'poor@xyz.edu',
        'password': 'password123',
        'agree_terms': '1'
    }, follow_redirects=True)
    client.post('/consent', data={'agree_consent': '1'}, follow_redirects=True)

    with app_instance.app_context():
        db = get_db()
        db.execute("UPDATE users SET credits = 0 WHERE email = 'poor@xyz.edu'")
        db.commit()

    # Attempt download
    res = client.get(f'/download/{file_id}', follow_redirects=True)
    html = res.data.decode('utf-8')
    assert 'toast' in html
    assert 'text-bg-danger' in html
    assert 'Insufficient credits!' in html
    assert 'alert-dismissible' not in html
    assert 'alert-danger' not in html
