"""
Smoke tests for  routes.
Iterates app.url_map for GET routes under four security contexts:
1. Anonymous user
2. Normal student user (alice@xyz.edu)
3. Other-university student user (david@abc.edu)
4. Admin user (admin@xyz.edu)

Asserts:
- No route ever crashes or returns 500.
- Anonymous users are cleanly redirected on protected routes.
- Normal students receive 403 on admin routes.
- Admin receives 200 on admin routes.
- Unknown URL returns custom 404 page with HTTP 404.
- Cross-university file access returns HTTP 404.
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
    """Create a temporary test database and configured Flask test application."""
    db_fd, db_path = tempfile.mkstemp(suffix='.db')
    upload_dir = tempfile.mkdtemp()

    test_config = {
        'TESTING': True,
        'DATABASE': db_path,
        'UPLOAD_FOLDER': upload_dir,
        'SECRET_KEY': 'test-routes-secret',
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

def register_and_consent(client, username, email, password="password123"):
    client.post('/logout', follow_redirects=True)
    res = client.post('/register', data={
        'username': username,
        'email': email,
        'password': password,
        'agree_terms': '1'
    }, follow_redirects=True)
    client.post('/consent', data={'agree_consent': '1'}, follow_redirects=True)
    return res

def upload_test_file(client, title="Lecture Notes 101"):
    return client.post('/upload', data={
        'title': title,
        'subject': 'Computer Science',
        'semester': '1',
        'type': 'Lecture Notes',
        'description': 'Introductory lecture material.',
        'confirm_copyright': '1',
        'file': (io.BytesIO(b'%PDF-1.4 test dummy content'), 'notes.pdf')
    }, follow_redirects=True)


# ---------------------------------------------------------------------------
# Route Smoke Tests
# ---------------------------------------------------------------------------

def test_routes_anonymous(client, app_instance):
    """Anonymous user accessing GET routes: no 500, protected routes redirect to login."""
    # Public routes should be 200
    for path in ['/', '/register', '/login', '/terms']:
        res = client.get(path)
        assert res.status_code == 200, f"Expected 200 for public route {path}, got {res.status_code}"

    # Protected routes should redirect to login (302)
    protected_paths = [
        '/browse',
        '/upload',
        '/dashboard',
        '/task',
        '/sus',
        '/feedback',
        '/admin',
        '/admin/baseline',
        '/admin/export/events'
    ]
    for path in protected_paths:
        res = client.get(path)
        assert res.status_code == 302, f"Expected 302 redirect for protected route {path}, got {res.status_code}"
        assert '/login' in res.headers.get('Location', ''), f"Expected redirect to /login for {path}"


def test_routes_student(client, app_instance):
    """Normal student (alice@xyz.edu): accesses student pages (200), forbidden on admin (403), no 500."""
    register_and_consent(client, 'alice_student', 'alice@xyz.edu')

    # Logged-in root redirects to browse
    res_root = client.get('/')
    assert res_root.status_code == 302
    assert '/browse' in res_root.headers.get('Location', '')

    # Student routes must succeed with 200
    student_routes = [
        '/browse',
        '/upload',
        '/dashboard',
        '/task',
        '/sus',
        '/feedback',
        '/terms',
        '/api/credits'
    ]
    for path in student_routes:
        res = client.get(path)
        assert res.status_code == 200, f"Expected 200 for student route {path}, got {res.status_code}"
        assert res.status_code != 500

    # Student cannot access admin routes (must return 403 Forbidden)
    admin_routes = [
        '/admin',
        '/admin/baseline',
        '/admin/export/events',
        '/admin/export/users_anonymized'
    ]
    for path in admin_routes:
        res = client.get(path)
        assert res.status_code == 403, f"Expected 403 Forbidden for admin route {path}, got {res.status_code}"


def test_routes_admin(client, app_instance):
    """Admin user (admin@xyz.edu): accesses admin routes with 200, no 500."""
    register_and_consent(client, 'site_admin', 'admin@xyz.edu')

    admin_routes = [
        '/admin',
        '/admin/baseline',
        '/admin/export/events',
        '/admin/export/tasks',
        '/admin/export/sus_responses',
        '/admin/export/feedback',
        '/admin/export/users_anonymized',
        '/admin/export/files',
        '/admin/export/downloads',
        '/admin/export/ledger'
    ]
    for path in admin_routes:
        res = client.get(path)
        assert res.status_code == 200, f"Expected 200 for admin route {path}, got {res.status_code}"
        assert res.status_code != 500


def test_routes_other_university_student_isolation(client, app_instance):
    """Other-university student (david@abc.edu) accessing file of XYZ university student gets 404."""
    # Alice from XYZ uploads a file
    register_and_consent(client, 'alice_xyz', 'alice@xyz.edu')
    upload_test_file(client, "XYZ Proprietary Exam")

    with app_instance.app_context():
        db = get_db()
        f_row = db.execute("SELECT id FROM files WHERE title = 'XYZ Proprietary Exam'").fetchone()
        assert f_row is not None
        alice_file_id = f_row['id']

    # David from ABC logs in
    register_and_consent(client, 'david_abc', 'david@abc.edu')

    # David views detail of Alice's file -> 404
    detail_res = client.get(f'/file/{alice_file_id}')
    assert detail_res.status_code == 404
    assert b"Resource Not Found" in detail_res.data or b"Not Found" in detail_res.data

    # David downloads Alice's file -> 404
    dl_res = client.get(f'/download/{alice_file_id}')
    assert dl_res.status_code == 404


def test_routes_unknown_url_custom_404(client, app_instance):
    """Unknown route returns custom 404 page and HTTP status 404."""
    res = client.get('/some-nonexistent-path-that-never-exists')
    assert res.status_code == 404
    assert b"404 - Not Found" in res.data
    assert b"Back to Safety" in res.data


def test_all_registered_get_routes_iterated(client, app_instance):
    """Iterate app.url_map to guarantee that no GET route generates a 500 error."""
    register_and_consent(client, 'test_user', 'user@xyz.edu')

    # We map route parameter names to benign dummy values for testing
    param_samples = {
        'file_id': 99999,
        'report_id': 99999,
        'table_name': 'events',
        'filename': 'css/custom.css'
    }

    with app_instance.app_context():
        for rule in app_instance.url_map.iter_rules():
            if 'GET' in rule.methods:
                kwargs = {}
                for arg in rule.arguments:
                    kwargs[arg] = param_samples.get(arg, 1)

                try:
                    from flask import url_for
                    target_url = url_for(rule.endpoint, **kwargs)
                except Exception:
                    continue

                res = client.get(target_url)
                # It can be 200, 302, 403, or 404 - but NEVER 500!
                assert res.status_code != 500, f"Route {target_url} returned 500 Internal Server Error!"
