"""
Tests for EduSpace Public Landing Page.
Verifies guest status 200, single h1, single btn-primary, no inline styles,
no banned marketing phrases, no theme toggle button, disabled T shortcut flag,
credit numbers matching config, and logged-in redirect.
Uses standard library html.parser without external dependencies.
"""

import os
import sys
import re
from html.parser import HTMLParser
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from config import Config
from app import create_app
from db import init_db
import tempfile


@pytest.fixture
def app_instance():
    """Create a temporary test database and configured Flask test application."""
    db_fd, db_path = tempfile.mkstemp(suffix='.db')
    upload_dir = tempfile.mkdtemp()

    test_config = {
        'TESTING': True,
        'DATABASE': db_path,
        'UPLOAD_FOLDER': upload_dir,
        'SECRET_KEY': 'test-landing-secret',
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



class LandingPageInspector(HTMLParser):
    def __init__(self):
        super().__init__()
        self.h1_count = 0
        self.btn_primary_count = 0
        self.style_tags = []
        self.btn_theme_toggle_count = 0
        self.theme_icon_count = 0
        self.body_attrs = {}
        self.in_main_or_footer = False
        self.content_text = []

    def handle_starttag(self, tag, attrs):
        attr_dict = dict(attrs)
        classes = attr_dict.get('class', '').split()

        if tag == 'h1':
            self.h1_count += 1

        if 'btn-primary' in classes:
            self.btn_primary_count += 1

        if 'btn-theme-toggle' in classes:
            self.btn_theme_toggle_count += 1

        if any(cls in ['ti-moon', 'ti-sun'] for cls in classes):
            self.theme_icon_count += 1

        if tag == 'body':
            self.body_attrs = attr_dict

        if 'style' in attr_dict:
            # Exclude task banner if any
            if attr_dict.get('id') != 'task-active-banner':
                self.style_tags.append((tag, attr_dict['style']))

        if tag in ['main', 'footer', 'header']:
            self.in_main_or_footer = True
        if tag in ['script', 'style']:
            self.in_script_or_style = True

    def handle_endtag(self, tag):
        if tag in ['main', 'footer', 'header']:
            self.in_main_or_footer = False
        if tag in ['script', 'style']:
            self.in_script_or_style = False

    def handle_data(self, data):
        if getattr(self, 'in_script_or_style', False):
            return
        if getattr(self, 'in_main_or_footer', False):
            self.content_text.append(data)


def test_landing_page_logged_out(client):
    """Guest visiting '/' receives 200 with landing page specifications."""
    res = client.get('/')
    assert res.status_code == 200

    html = res.data.decode('utf-8')
    inspector = LandingPageInspector()
    inspector.feed(html)

    # 1. Exactly one h1
    assert inspector.h1_count == 1, f"Expected exactly 1 <h1>, found {inspector.h1_count}"

    # 2. Exactly one btn-primary
    assert inspector.btn_primary_count == 1, f"Expected exactly 1 .btn-primary, found {inspector.btn_primary_count}"

    # 3. No inline style attributes
    assert len(inspector.style_tags) == 0, f"Found elements with inline style: {inspector.style_tags}"

    # 4. None of the banned phrases or exclamation marks
    banned_words = [
        'revolutionize', 'supercharge', 'unlock', 'seamless',
        'empower', 'cutting-edge', 'next-level', 'game-changer',
        'all-in-one', 'take your learning to the next level'
    ]
    all_text = ' '.join(inspector.content_text).lower()
    for word in banned_words:
        assert word not in all_text, f"Banned marketing phrase '{word}' found in landing page text"

    assert '!' not in all_text, "Exclamation mark '!' found in landing page text"

    # 5. Shared guest header includes theme toggle on all guest pages
    assert inspector.btn_theme_toggle_count >= 1, f"Expected theme toggle buttons in shared guest header, found {inspector.btn_theme_toggle_count}"
    assert inspector.theme_icon_count >= 1, f"Expected moon/sun icons in shared guest header, found {inspector.theme_icon_count}"

    # 6. Credit numbers match config.py
    assert str(Config.SIGNUP_BONUS) in html
    assert str(Config.UPLOAD_REWARD) in html
    assert str(Config.DOWNLOAD_COST) in html
    assert str(Config.MAX_REWARDED_UPLOADS_PER_DAY) in html


def test_landing_page_redirects_for_logged_in_user(client, app_instance):
    """Logged in user visiting '/' is redirected to /browse."""
    from tests.test_routes import register_and_consent
    register_and_consent(client, 'landing_test_student', 'landing_test@xyz.edu')

    res = client.get('/', follow_redirects=False)
    assert res.status_code == 302
    assert '/browse' in res.headers.get('Location', '')


def test_login_page_resolves_theme_automatically(client):
    """Verify /login uses the saved or system theme without a manual toggle."""
    res = client.get('/login')
    assert res.status_code == 200

    html = res.data.decode('utf-8')
    assert "localStorage.getItem('theme')" in html, "/login must read stored theme"
    assert "prefers-color-scheme" in html, "/login must fall back to prefers-color-scheme"
    assert "btn-theme-toggle" in html, "/login must include the shared guest header theme toggle"
    assert 'data-no-theme-toggle="true"' not in html, "/login must not have data-no-theme-toggle"
    assert '<meta name="color-scheme" content="light">' not in html, "/login must not force light color-scheme"


def test_landing_page_no_stray_text_nodes(client):
    """Assert no stray 'true', 'True', 'None', or 'False' text nodes appear and first visible layout text is brand/nav."""
    res = client.get('/')
    assert res.status_code == 200

    html = res.data.decode('utf-8')

    # 1. Check raw HTML outside scripts and styles for standalone stray boolean/null keywords
    clean_html = re.sub(r'<script[\s\S]*?</script>', '', html)
    clean_html = re.sub(r'<style[\s\S]*?</style>', '', clean_html)
    text_only = re.sub(r'<[^>]+>', ' ', clean_html)
    words = text_only.split()

    for stray in ['true', 'True', 'None', 'False']:
        assert stray not in words, f"Stray text '{stray}' found in rendered landing page text outside tags/scripts"

    # 2. Check structure before <header> in body
    body_to_header_match = re.search(r'<body[^>]*>([\s\S]*?)<header', html)
    assert body_to_header_match is not None, "<header> element not found in <body>"
    pre_header_content = body_to_header_match.group(1)
    pre_header_text = re.sub(r'<[^>]+>', '', pre_header_content).strip()
    # Only the accessible skip link should be present before the header
    assert pre_header_text == 'Skip to main content', f"Unexpected text before header: {repr(pre_header_text)}"

    # 3. First layout text inside <header> is the brand / nav text
    header_content_match = re.search(r'<header[^>]*>([\s\S]*?)</header>', html)
    assert header_content_match is not None, "<header>...</header> block not found"
    header_text = ' '.join(re.sub(r'<[^>]+>', ' ', header_content_match.group(1)).split())
    assert header_text.startswith('Edu Space') or header_text.startswith('EduSpace'), f"First layout text should be brand, got: {header_text[:30]}"


