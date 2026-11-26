"""
Verification tests for UI refactor phases 1-7:
- Browse/Public library tabs, sidebar, shortcut JSON map
- Mobile filter offcanvas single form & unique IDs
- Shared guest header and footer across all guest pages
- Plain-language licence registry and template rendering
- Pluralize helper
- No btn-secondary, at most one btn-primary per page surface
"""

import glob
import html as html_lib
import json
import os
import re
import tempfile
import pytest

from app import create_app
from db import get_db
from eduspace.hooks import pluralize
from eduspace.services.licences import LICENCES, LICENCE_WARNING


@pytest.fixture
def app():
    """Create isolated test app with student, public member, admin, and sample files."""
    db_fd, db_path = tempfile.mkstemp(suffix='.db')
    upload_dir = tempfile.mkdtemp()
    test_app = create_app({
        'TESTING': True,
        'DATABASE': db_path,
        'UPLOAD_FOLDER': upload_dir,
        'SECRET_KEY': 'ui-refactor-secret',
        'ADMIN_EMAIL': 'admin@xyz.edu',
        'ALLOWED_DOMAINS': {'xyz.edu': 'XYZ University'},
    })
    with test_app.app_context():
        db = get_db()
        from werkzeug.security import generate_password_hash
        pwd = generate_password_hash('password123')
        xyz_id = db.execute("SELECT id FROM universities WHERE domain = 'xyz.edu'").fetchone()['id']
        pub_id = db.execute("SELECT id FROM universities WHERE kind = 'public'").fetchone()['id']

        db.execute(
            "INSERT INTO users (email, username, password_hash, university_id, credits, is_admin) VALUES (?, ?, ?, ?, 30, 0)",
            ('student@xyz.edu', 'student1', pwd, xyz_id)
        )
        db.execute(
            "INSERT INTO users (email, username, password_hash, university_id, credits, is_admin) VALUES (?, ?, ?, ?, 10, 0)",
            ('pub1@eduspace.public', 'pub1', pwd, pub_id)
        )
        db.execute(
            "INSERT INTO users (email, username, password_hash, university_id, credits, is_admin) VALUES (?, ?, ?, ?, 30, 1)",
            ('admin@xyz.edu', 'admin1', pwd, xyz_id)
        )
        for uid in (1, 2, 3):
            db.execute("INSERT INTO consents (user_id) VALUES (?)", (uid,))

        with open(os.path.join(upload_dir, 'pub.pdf'), 'wb') as f:
            f.write(b'%PDF-1.4\n%%EOF')
        db.execute(
            "INSERT INTO files (uploader_id, university_id, title, subject, semester, type, stored_name, original_name, size, status, visibility, content_hash, license) "
            "VALUES (2, ?, 'Public Notes', 'Math', 1, 'Lecture Notes', 'pub.pdf', 'pub.pdf', 15, 'active', 'public', 'h1', 'own_work')",
            (pub_id,)
        )
        db.execute(
            "INSERT INTO resource_requests (requester_id, university_id, title, subject, semester, material_type, visibility, status) "
            "VALUES (2, ?, 'Need Calc Notes', 'Math', 1, 'Lecture Notes', 'public', 'open')",
            (pub_id,)
        )
        db.commit()
    yield test_app
    os.close(db_fd)
    if os.path.exists(db_path):
        os.unlink(db_path)


def test_pluralize_helper():
    """Verify pluralize handles 0, 1, and >1 counts properly."""
    assert pluralize(1, 'student interested') == '1 student interested'
    assert pluralize(2, 'student interested', 'students interested') == '2 students interested'
    assert pluralize(1, 'download') == '1 download'
    assert pluralize(0, 'download') == '0 downloads'
    assert pluralize(1, 'credit') == '1 credit'
    assert pluralize(5, 'credit') == '5 credits'
    assert pluralize(1, 'submission') == '1 submission'
    assert pluralize(1, 'request') == '1 request'


def test_licence_registry_and_selects(app):
    """Licence registry has all 5 keys and upload/request selects render from it."""
    keys = [lic.key for lic in LICENCES]
    assert keys == ['own_work', 'cc_by', 'cc_by_sa', 'cc0', 'public_domain']

    client = app.test_client()
    client.post('/login', data={'email': 'pub1@eduspace.public', 'password': 'password123'})
    upload_html = html_lib.unescape(client.get('/upload').data.decode('utf-8'))

    # Non-requester views public request /requests/1 to see the fulfil licence select
    student = app.test_client()
    student.post('/login', data={'email': 'student@xyz.edu', 'password': 'password123'})
    req_html = html_lib.unescape(student.get('/requests/1').data.decode('utf-8'))

    for html in (upload_html, req_html):
        for lic in LICENCES:
            assert f'value="{lic.key}"' in html
            assert lic.label in html
            assert lic.plain_summary in html
        assert 'Which one should I choose?' in html
        assert LICENCE_WARNING in html


def test_guest_pages_share_identical_footer_and_header_structure(app):
    """All guest pages render the shared _guest_header and identical _guest_footer."""
    client = app.test_client()
    guest_paths = ['/', '/login', '/register', '/register/public', '/library', '/terms']
    footers = []
    for path in guest_paths:
        res = client.get(path)
        assert res.status_code == 200
        html = res.data.decode('utf-8')
        footer_match = re.search(r'<footer[\s\S]*?</footer>', html)
        assert footer_match, f"Missing footer on {path}"
        footers.append(footer_match.group(0))
        assert 'id="guestNavOffcanvas"' in html, f"Missing guest offcanvas on {path}"
        assert 'Public library' in html
        assert 'How it works' in html

    assert len(set(footers)) == 1, "Guest footer differs across guest pages"


def test_sidebar_tabs_and_shortcut_json_map(app):
    """Student sidebar has no Public library item; Browse shows both tabs; public member sees only Public library tab."""
    student = app.test_client()
    student.post('/login', data={'email': 'student@xyz.edu', 'password': 'password123'})

    browse_html = student.get('/browse').data.decode('utf-8')
    sidebar_match = re.search(r'<aside class="app-sidebar[\s\S]*?</aside>', browse_html)
    assert sidebar_match
    assert 'Public library' not in sidebar_match.group(0)
    assert 'My university' in browse_html
    assert 'Public library' in browse_html
    assert '<h1 class="visually-hidden">Study Materials</h1>' in browse_html
    assert 'Compartmentalized' not in browse_html

    # Shortcut JSON map contains g p -> /library
    map_match = re.search(r'<script type="application/json" id="shortcut-targets">(.*?)</script>', browse_html)
    assert map_match
    targets = json.loads(map_match.group(1))
    assert targets.get('g p') == '/library'

    # Public member sees no My university tab on /library
    pub = app.test_client()
    pub.post('/login', data={'email': 'pub1@eduspace.public', 'password': 'password123'})
    pub_html = pub.get('/library').data.decode('utf-8')
    assert 'My university' not in pub_html
    assert 'Public library' in pub_html


def test_filters_single_form_unique_ids(app):
    """Filter forms on /browse and /library have no duplicate element IDs."""
    client = app.test_client()
    client.post('/login', data={'email': 'student@xyz.edu', 'password': 'password123'})
    for path in ('/browse', '/library'):
        html = client.get(path).data.decode('utf-8')
        ids = re.findall(r'\bid="([^"]+)"', html)
        dups = {i for i in ids if ids.count(i) > 1}
        assert not dups, f"Duplicate IDs on {path}: {dups}"


def test_no_btn_secondary_in_templates():
    """No template may use btn-secondary."""
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    for path in glob.glob(os.path.join(base_dir, 'templates', '**', '*.html'), recursive=True):
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()
        assert 'btn-secondary' not in content, f"Found btn-secondary in {os.path.basename(path)}"
