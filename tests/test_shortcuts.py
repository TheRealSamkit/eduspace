"""
Tests for Phase 5: Keyboard Shortcuts and Tooltips.
Verifies shortcut definitions, script loading, markup attributes,
and role-based visibility.
"""

import os
import re
import sys
import tempfile
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from app import create_app
from db import init_db, get_db


@pytest.fixture
def app():
    """Create test application."""
    db_fd, db_path = tempfile.mkstemp(suffix='.db')
    upload_dir = tempfile.mkdtemp()

    test_config = {
        'TESTING': True,
        'DATABASE': db_path,
        'UPLOAD_FOLDER': upload_dir,
        'SECRET_KEY': 'test-secret',
        'ADMIN_EMAIL': 'admin@xyz.edu',
        'ALLOWED_DOMAINS': {
            'xyz.edu': 'XYZ University',
            'abc.edu': 'ABC College'
        }
    }
    test_app = create_app(test_config)
    with test_app.app_context():
        init_db(test_app)
        # Seed test users
        db = get_db()
        from werkzeug.security import generate_password_hash
        pwd = generate_password_hash('password123')
        db.execute(
            "INSERT INTO users (email, username, password_hash, university_id, credits, is_admin) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            ('student@xyz.edu', 'student_user', pwd, 1, 20, 0)
        )
        db.execute(
            "INSERT INTO users (email, username, password_hash, university_id, credits, is_admin) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            ('admin@xyz.edu', 'admin_user', pwd, 1, 20, 1)
        )
        db.execute("INSERT INTO consents (user_id) VALUES (1)")
        db.execute("INSERT INTO consents (user_id) VALUES (2)")
        db.commit()
    yield test_app

    os.close(db_fd)
    try:
        os.unlink(db_path)
    except OSError:
        pass


@pytest.fixture
def client(app):
    return app.test_client()


def test_shortcuts_js_definitions():
    """Verify static/js/shortcuts.js has no conflicting keys and follows shortcut conventions."""
    js_path = os.path.join(os.path.dirname(__file__), '..', 'static', 'js', 'shortcuts.js')
    assert os.path.exists(js_path), "static/js/shortcuts.js must exist"

    with open(js_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # Extract all key: '...' inside SHORTCUTS_DEF
    match = re.search(r'const SHORTCUTS_DEF\s*=\s*\[(.*?)\];', content, re.DOTALL)
    assert match, "SHORTCUTS_DEF array must be defined"

    array_body = match.group(1)
    keys = re.findall(r"key:\s*['\"]([^'\"]+)['\"]", array_body)
    assert len(keys) >= 10, f"Expected at least 10 shortcuts defined, found {len(keys)}"

    # Check for no duplicates
    assert len(keys) == len(set(keys)), f"Duplicate shortcut keys found: {keys}"

    # Verify no numeric keys (0-9) or Enter used
    for k in keys:
        assert not re.search(r'\d', k), f"Shortcut key '{k}' must not use digits (0-9)"
        assert 'enter' not in k.lower(), f"Shortcut key '{k}' must not use Enter"

    # Verify presence of expected core shortcuts
    expected = ['g b', 'g p', 'g v', 'g r', 'g u', 'g d', 'g t', 'g s', 'g f', 'g a', 'g l', 't', '/', '?', 'Escape']
    for exp in expected:
        assert exp in keys, f"Expected shortcut '{exp}' in SHORTCUTS_DEF"


def test_shortcuts_markup_for_student(client):
    """Verify data-shortcut and tooltip attributes rendered for a standard student."""
    # Login as student
    client.post('/login', data={'email': 'student@xyz.edu', 'password': 'password123'}, follow_redirects=True)
    res = client.get('/browse')
    assert res.status_code == 200
    html = res.data.decode('utf-8')

    # Script tags loaded
    assert 'shortcuts.js' in html
    assert 'toast.js' in html

    # Student navigation shortcuts present
    student_shortcuts = ['g b', 'g p', 'g v', 'g r', 'g u', 'g d', 'g t', 'g s', 'g f']
    for sc in student_shortcuts:
        assert f'data-shortcut="{sc}"' in html, f"Missing data-shortcut='{sc}' for student"
        assert f'aria-keyshortcuts="{sc}"' in html, f"Missing aria-keyshortcuts='{sc}' for student"

    # Admin navigation shortcuts NOT present
    assert 'data-shortcut="g a"' not in html
    assert 'data-shortcut="g l"' not in html

    # Help modal trigger in user dropdown
    assert 'id="btn-shortcuts-modal"' in html

    # Tooltip attributes present on topbar / navigation
    assert 'data-bs-toggle="tooltip"' in html


def test_shortcuts_markup_for_admin(client):
    """Verify admin navigation shortcuts are rendered when logged in as admin."""
    client.post('/login', data={'email': 'admin@xyz.edu', 'password': 'password123'}, follow_redirects=True)
    res = client.get('/dashboard')
    assert res.status_code == 200
    html = res.data.decode('utf-8')

    # Both student and admin shortcuts present
    for sc in ['g b', 'g u', 'g d', 'g a', 'g l']:
        assert f'data-shortcut="{sc}"' in html, f"Missing data-shortcut='{sc}' for admin"


def test_shortcuts_markup_for_guest(client):
    """Verify guests do not see navigation shortcuts."""
    res = client.get('/login')
    assert res.status_code == 200
    html = res.data.decode('utf-8')

    assert 'data-shortcut="g b"' not in html
    assert 'data-shortcut="g u"' not in html
    assert 'data-shortcut="g a"' not in html
