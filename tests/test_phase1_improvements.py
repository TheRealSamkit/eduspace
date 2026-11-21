"""
Tests for Phase 1 & 2 Security, Cache-Control, Auth, API, and SUS Validation improvements.
"""

import os
import sys
import tempfile
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import create_app
from db import init_db, get_db

@pytest.fixture
def app_instance():
    db_fd, db_path = tempfile.mkstemp(suffix='.db')
    upload_dir = tempfile.mkdtemp()

    test_config = {
        'TESTING': True,
        'DATABASE': db_path,
        'UPLOAD_FOLDER': upload_dir,
        'SECRET_KEY': 'test-phase1-secret',
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
        try:
            os.remove(db_path)
        except Exception:
            pass
    for root, dirs, files in os.walk(upload_dir, topdown=False):
        for f in files:
            try:
                os.remove(os.path.join(root, f))
            except Exception:
                pass
        try:
            os.rmdir(root)
        except Exception:
            pass

@pytest.fixture
def client(app_instance):
    return app_instance.test_client()

def register_and_login(client, username='phase1_user', email='phase1@xyz.edu', password='password123'):
    """Helper to create user, consent, and log in."""
    res = client.post('/register', data={
        'username': username,
        'email': email,
        'password': password,
        'agree_terms': 'on'
    }, follow_redirects=True)
    # Complete consent
    client.post('/consent', data={'agree_consent': 'on'}, follow_redirects=True)
    return res

def test_cache_control_headers(client):
    """Verify that all non-static pages carry Cache-Control: no-store, no-cache, must-revalidate, max-age=0."""
    res_login = client.get('/login')
    assert 'no-store' in res_login.headers.get('Cache-Control', '')
    assert res_login.headers.get('Pragma') == 'no-cache'
    assert res_login.headers.get('Expires') == '0'

    res_register = client.get('/register')
    assert 'no-store' in res_register.headers.get('Cache-Control', '')

    res_index = client.get('/')
    assert 'no-store' in res_index.headers.get('Cache-Control', '')

def test_post_logout_redirects_and_cookie_invalidation(client, app_instance):
    """After logout, protected routes redirect to /login and cookies are cleared."""
    register_and_login(client, 'logout_test', 'logout_test@xyz.edu')

    # Confirm user can access browse
    res_browse = client.get('/browse')
    assert res_browse.status_code == 200

    # Log out
    res_logout = client.post('/logout', follow_redirects=False)
    assert res_logout.status_code == 302
    assert '/login' in res_logout.headers['Location']

    # Now verify all protected routes redirect to /login
    protected_urls = ['/browse', '/upload', '/dashboard', '/task', '/sus', '/feedback', '/admin']
    for url in protected_urls:
        res = client.get(url, follow_redirects=False)
        assert res.status_code == 302
        assert '/login' in res.headers['Location']

def test_login_and_register_redirect_when_logged_in(client, app_instance):
    """Logged in users navigating to /login or /register are redirected to /browse."""
    register_and_login(client, 'active_user', 'active@xyz.edu')

    res_login = client.get('/login', follow_redirects=False)
    assert res_login.status_code == 302
    assert '/browse' in res_login.headers['Location']

    res_reg = client.get('/register', follow_redirects=False)
    assert res_reg.status_code == 302
    assert '/browse' in res_reg.headers['Location']

def test_api_me_auth_status(client, app_instance):
    """GET /api/me returns 401 when anonymous and 200 with user profile when authenticated."""
    # Anonymous
    res_anon = client.get('/api/me')
    assert res_anon.status_code == 401
    data_anon = res_anon.get_json()
    assert data_anon['authenticated'] is False

    # Authenticated
    register_and_login(client, 'api_me_user', 'me@xyz.edu')
    res_auth = client.get('/api/me')
    assert res_auth.status_code == 200
    data_auth = res_auth.get_json()
    assert data_auth['authenticated'] is True
    assert data_auth['user']['username'] == 'api_me_user'
    assert data_auth['user']['email'] == 'me@xyz.edu'

def test_api_domain_check(client):
    """GET /api/domain-check returns university name if recognized, 404 if not, and never exposes domain list."""
    # Valid university email
    res_valid = client.get('/api/domain-check?email=student@xyz.edu')
    assert res_valid.status_code == 200
    data_valid = res_valid.get_json()
    assert data_valid['valid'] is True
    assert data_valid['university_name'] == 'XYZ University'
    assert 'ALLOWED_DOMAINS' not in data_valid
    assert 'domains' not in data_valid

    # Unsupported email domain
    res_unsupported = client.get('/api/domain-check?email=student@gmail.com')
    assert res_unsupported.status_code == 404
    data_unsupported = res_unsupported.get_json()
    assert data_unsupported['valid'] is False
    assert 'ALLOWED_DOMAINS' not in data_unsupported

    # Malformed email
    res_bad = client.get('/api/domain-check?email=notanemail')
    assert res_bad.status_code == 400

def test_sus_server_side_validation(client, app_instance):
    """Ensure missing questions or out-of-range answers are rejected with HTTP 400."""
    register_and_login(client, 'sus_val_user', 'sus_val@xyz.edu')

    # Missing questions (e.g. only 5 questions provided)
    res_missing = client.post('/sus', data={'q1': 3, 'q2': 3, 'q3': 3})
    assert res_missing.status_code == 400
    assert b"Please rate" in res_missing.data or b"must be rated" in res_missing.data

    # Out of range question value (e.g. 6)
    valid_data = {f'q{i}': 3 for i in range(1, 11)}
    valid_data['q5'] = 6
    res_out_of_range = client.post('/sus', data=valid_data)
    assert res_out_of_range.status_code == 400

    # Valid complete submission succeeds
    valid_data['q5'] = 4
    res_ok = client.post('/sus', data=valid_data, follow_redirects=True)
    assert res_ok.status_code == 200
    assert b"Thank you" in res_ok.data
