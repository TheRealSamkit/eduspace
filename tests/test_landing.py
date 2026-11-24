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

    # 5. NO theme toggle element (no .btn-theme-toggle, no ti-moon or ti-sun icon)
    assert inspector.btn_theme_toggle_count == 0, f"Expected 0 theme toggle buttons, found {inspector.btn_theme_toggle_count}"
    assert inspector.theme_icon_count == 0, f"Expected 0 moon/sun icons, found {inspector.theme_icon_count}"

    # 6. Page flag disabling T shortcut is present on body
    assert inspector.body_attrs.get('data-no-theme-toggle') == 'true', "Expected data-no-theme-toggle='true' on <body>"

    # 7. Credit numbers match config.py
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
