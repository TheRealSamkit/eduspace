"""
Automated Test Suite for StudyExchange
Covers:
1. Domain restriction (allowed domains vs rejected domains)
2. University isolation (browsing and direct download 404 across institutions)
3. Credit economy rules (signup bonus, daily upload cap, download deduction, no negative balance, free re-downloads)
4. Admin takedown & credit reversal
5. System Usability Scale (SUS) score calculation
6. Task telemetry logging (prototype and baseline)
7. Anonymized research dataset exports
"""

import os
import sys
import io
import tempfile
import pytest

# Ensure parent directory is in Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import create_app
from config import Config
from db import get_db, init_db

@pytest.fixture
def app_instance():
    """Create a temporary test database and configured Flask test application."""
    db_fd, db_path = tempfile.mkstemp(suffix='.db')
    upload_dir = tempfile.mkdtemp()

    test_config = {
        'TESTING': True,
        'DATABASE': db_path,
        'UPLOAD_FOLDER': upload_dir,
        'SECRET_KEY': 'test-secret-key',
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
    # clean upload temp files
    for root, dirs, files in os.walk(upload_dir, topdown=False):
        for f in files:
            os.remove(os.path.join(root, f))
        os.rmdir(root)

@pytest.fixture
def client(app_instance):
    """Test client."""
    return app_instance.test_client()

def register_user(client, username, email, password="password123"):
    """Helper to register and consent a student."""
    client.post('/logout', follow_redirects=True)
    res = client.post('/register', data={
        'username': username,
        'email': email,
        'password': password,
        'agree_terms': '1'
    }, follow_redirects=True)
    # Complete consent
    client.post('/consent', data={'agree_consent': '1'}, follow_redirects=True)
    return res

def login_user(client, email, password="password123"):
    """Helper to log in."""
    return client.post('/login', data={'email': email, 'password': password}, follow_redirects=True)

# -------------------------------------------------------------
# 1. Domain Restriction Tests
# -------------------------------------------------------------
def test_domain_restriction(client, app_instance):
    """Verify that only institutional domains in ALLOWED_DOMAINS are permitted."""
    # Disallowed domains
    bad_emails = [
        'student@gmail.com',
        'user@yahoo.com',
        'hacker@unknown.edu',
        'alumni@otheruni.org'
    ]
    for email in bad_emails:
        res = client.post('/register', data={
            'username': 'baduser_' + email.split('@')[0],
            'email': email,
            'password': 'password123',
            'agree_terms': '1'
        }, follow_redirects=True)
        assert b"is not recognized" in res.data

    # Allowed domains
    res_xyz = client.post('/register', data={
        'username': 'student_xyz',
        'email': 'student@xyz.edu',
        'password': 'password123',
        'agree_terms': '1'
    }, follow_redirects=True)
    assert b"Welcome to StudyExchange" in res_xyz.data

    client.post('/logout', follow_redirects=True)

    res_abc = client.post('/register', data={
        'username': 'student_abc',
        'email': 'student@abc.edu',
        'password': 'password123',
        'agree_terms': '1'
    }, follow_redirects=True)
    assert b"Welcome to StudyExchange" in res_abc.data

# -------------------------------------------------------------
# 2. University Isolation Tests (Critical)
# -------------------------------------------------------------
def test_university_isolation_browse_and_download(client, app_instance):
    """
    CRITICAL TEST:
    A student from XYZ University cannot browse, view, or download files from ABC College.
    Direct access to /download/<id> of another university's file returns 404.
    """
    # 1. Register student at ABC College and upload a document
    register_user(client, 'abc_student', 'student@abc.edu')
    upload_res = client.post('/upload', data={
        'title': 'ABC Secret Lecture Notes',
        'subject': 'Biology',
        'semester': '1',
        'type': 'Lecture Notes',
        'description': 'Proprietary notes for ABC College only.',
        'confirm_copyright': '1',
        'file': (io.BytesIO(b'%PDF-1.4 dummy pdf content'), 'abc_notes.pdf')
    }, follow_redirects=True)
    assert upload_res.status_code == 200

    # Retrieve the file id of the uploaded ABC file
    with app_instance.app_context():
        db = get_db()
        abc_file = db.execute("SELECT id FROM files WHERE title = 'ABC Secret Lecture Notes'").fetchone()
        assert abc_file is not None
        abc_file_id = abc_file['id']

    # Logout ABC student
    client.post('/logout', follow_redirects=True)

    # 2. Register student at XYZ University
    register_user(client, 'xyz_student', 'student@xyz.edu')

    # A. Browse test: ABC file must NOT appear in XYZ browse listing
    browse_res = client.get('/browse')
    assert b'ABC Secret Lecture Notes' not in browse_res.data

    # B. Search test: Searching for the exact title from XYZ returns nothing
    search_res = client.get('/browse?q=ABC+Secret')
    assert b'ABC Secret Lecture Notes' not in search_res.data
    assert b'No files found' in search_res.data

    # C. File detail test: Direct URL to /file/<abc_file_id> returns 404
    detail_res = client.get(f'/file/{abc_file_id}')
    assert detail_res.status_code == 404

    # D. CRITICAL: Direct download of ABC file by XYZ user returns 404
    download_res = client.get(f'/download/{abc_file_id}')
    assert download_res.status_code == 404

    # E. Rating attempt across university boundary returns 404
    rate_res = client.post(f'/file/{abc_file_id}/rate', data={'stars': 5})
    assert rate_res.status_code == 404

# -------------------------------------------------------------
# 3. Credit Rules Tests
# -------------------------------------------------------------
def test_credit_economy_rules(client, app_instance):
    """
    Verify:
    1. Signup bonus (+20)
    2. Upload rewards (+10 each, cap at 3 per day)
    3. 4th upload earns 0 bonus credits (cap reached)
    4. Download cost (-5 credits deducted)
    5. Free re-download
    6. Free download of own uploads
    7. Insufficient credits prevents negative balance
    """
    # 1. Signup bonus check
    register_user(client, 'alice_xyz', 'alice@xyz.edu')
    with app_instance.app_context():
        db = get_db()
        user = db.execute("SELECT credits FROM users WHERE email = 'alice@xyz.edu'").fetchone()
        assert user['credits'] == 20

        # Ledger contains signup
        ledger_signup = db.execute(
            "SELECT amount, reason FROM ledger WHERE user_id = (SELECT id FROM users WHERE email = 'alice@xyz.edu')"
        ).fetchone()
        assert ledger_signup['reason'] == 'signup'
        assert ledger_signup['amount'] == 20

    # 2. Upload rewards and daily cap
    # Upload 1 -> credits become 20 + 10 = 30
    client.post('/upload', data={
        'title': 'Alice Note 1', 'subject': 'Math', 'semester': 1, 'type': 'Summaries',
        'confirm_copyright': '1', 'file': (io.BytesIO(b'%PDF-1.4 file1'), 'f1.pdf')
    }, follow_redirects=True)

    # Upload 2 -> credits become 30 + 10 = 40
    client.post('/upload', data={
        'title': 'Alice Note 2', 'subject': 'Math', 'semester': 1, 'type': 'Summaries',
        'confirm_copyright': '1', 'file': (io.BytesIO(b'%PDF-1.4 file2'), 'f2.pdf')
    }, follow_redirects=True)

    # Upload 3 -> credits become 40 + 10 = 50
    client.post('/upload', data={
        'title': 'Alice Note 3', 'subject': 'Math', 'semester': 1, 'type': 'Summaries',
        'confirm_copyright': '1', 'file': (io.BytesIO(b'%PDF-1.4 file3'), 'f3.pdf')
    }, follow_redirects=True)

    # Upload 4 -> DAILY CAP REACHED! Credits stay at 50, but ledger gets 0 amount upload row
    upload4_res = client.post('/upload', data={
        'title': 'Alice Note 4', 'subject': 'Math', 'semester': 1, 'type': 'Summaries',
        'confirm_copyright': '1', 'file': (io.BytesIO(b'%PDF-1.4 file4'), 'f4.pdf')
    }, follow_redirects=True)
    assert b"Daily reward limit of 3 reached" in upload4_res.data

    with app_instance.app_context():
        db = get_db()
        user = db.execute("SELECT credits FROM users WHERE email = 'alice@xyz.edu'").fetchone()
        assert user['credits'] == 50

    # 3. Own uploads are free
    with app_instance.app_context():
        db = get_db()
        f1 = db.execute("SELECT id FROM files WHERE title = 'Alice Note 1'").fetchone()
    dl_own = client.get(f"/download/{f1['id']}")
    assert dl_own.status_code == 200
    with app_instance.app_context():
        db = get_db()
        user = db.execute("SELECT credits FROM users WHERE email = 'alice@xyz.edu'").fetchone()
        assert user['credits'] == 50  # No deduction for own upload

    # 4. Another user downloads Alice's file -> -5 credits
    client.post('/logout', follow_redirects=True)
    register_user(client, 'bob_xyz', 'bob@xyz.edu')  # starts with 20 credits
    dl_res = client.get(f"/download/{f1['id']}")
    assert dl_res.status_code == 200

    with app_instance.app_context():
        db = get_db()
        bob = db.execute("SELECT credits FROM users WHERE email = 'bob@xyz.edu'").fetchone()
        assert bob['credits'] == 15  # 20 - 5 = 15

    # 5. Bob re-downloads -> Free (still 15 credits)
    client.get(f"/download/{f1['id']}")
    with app_instance.app_context():
        db = get_db()
        bob = db.execute("SELECT credits FROM users WHERE email = 'bob@xyz.edu'").fetchone()
        assert bob['credits'] == 15

    # 6. Insufficient credits prevents negative balance
    with app_instance.app_context():
        db = get_db()
        # Drain Bob's credits to 2 credits
        db.execute("UPDATE users SET credits = 2 WHERE email = 'bob@xyz.edu'")
        db.commit()
        f2 = db.execute("SELECT id FROM files WHERE title = 'Alice Note 2'").fetchone()

    # Bob attempts to download a new file costing 5 credits
    dl_fail = client.get(f"/download/{f2['id']}", follow_redirects=True)
    assert b"Insufficient credits" in dl_fail.data

    with app_instance.app_context():
        db = get_db()
        bob = db.execute("SELECT credits FROM users WHERE email = 'bob@xyz.edu'").fetchone()
        assert bob['credits'] == 2  # Credits never went negative!

# -------------------------------------------------------------
# 4. Admin Moderation & Credit Reversal Test
# -------------------------------------------------------------
def test_admin_removal_and_reversal(client, app_instance):
    """Admin can remove an infringing file and reverse the uploader's reward."""
    # 1. Register student at XYZ and upload a file
    register_user(client, 'author_xyz', 'author@xyz.edu')
    client.post('/upload', data={
        'title': 'Infringing Copyright Book', 'subject': 'Law', 'semester': 2, 'type': 'Summaries',
        'confirm_copyright': '1', 'file': (io.BytesIO(b'%PDF-1.4 lawbook'), 'law.pdf')
    }, follow_redirects=True)

    with app_instance.app_context():
        db = get_db()
        author = db.execute("SELECT id, credits FROM users WHERE email = 'author@xyz.edu'").fetchone()
        assert author['credits'] == 30  # 20 bonus + 10 upload
        file_row = db.execute("SELECT id FROM files WHERE title = 'Infringing Copyright Book'").fetchone()
        target_file_id = file_row['id']

    client.post('/logout', follow_redirects=True)

    # 2. Register admin (admin@xyz.edu)
    register_user(client, 'admin_user', 'admin@xyz.edu')

    # Admin removes file
    remove_res = client.post(f"/admin/file/{target_file_id}/remove", follow_redirects=True)
    assert remove_res.status_code == 200

    with app_instance.app_context():
        db = get_db()
        # File status is 'removed'
        f = db.execute("SELECT status FROM files WHERE id = ?", (target_file_id,)).fetchone()
        assert f['status'] == 'removed'

        # Author's credits reversed from 30 back to 20
        author = db.execute("SELECT id, credits FROM users WHERE email = 'author@xyz.edu'").fetchone()
        assert author['credits'] == 20

        # Ledger has reversal
        rev = db.execute("SELECT amount, reason FROM ledger WHERE user_id = ? AND reason = 'reversal'", (author['id'],)).fetchone()
        assert rev is not None
        assert rev['amount'] == -10

# -------------------------------------------------------------
# 5. System Usability Scale (SUS) Scoring Test
# -------------------------------------------------------------
def test_sus_scoring(client, app_instance):
    """
    Standard SUS 10-Item Scoring:
    Odd items (q1, q3, q5, q7, q9): value - 1
    Even items (q2, q4, q6, q8, q10): 5 - value
    Score = sum * 2.5
    """
    register_user(client, 'sus_student', 'sus@xyz.edu')

    # Perfect score submission: all odd items 5, all even items 1
    # Odd contributions: 5-1 = 4 each (x5 = 20)
    # Even contributions: 5-1 = 4 each (x5 = 20)
    # Sum = 40 -> Score = 40 * 2.5 = 100.0
    res = client.post('/sus', data={
        'q1': 5, 'q2': 1, 'q3': 5, 'q4': 1, 'q5': 5,
        'q6': 1, 'q7': 5, 'q8': 1, 'q9': 5, 'q10': 1
    }, follow_redirects=True)
    assert b"Thank you" in res.data

    with app_instance.app_context():
        db = get_db()
        row = db.execute("SELECT score FROM sus_responses ORDER BY id DESC LIMIT 1").fetchone()
        assert row['score'] == 100.0

    # Middle neutral score submission: all 3s
    # Odd contributions: 3-1 = 2 each (x5 = 10)
    # Even contributions: 5-3 = 2 each (x5 = 10)
    # Sum = 20 -> Score = 20 * 2.5 = 50.0
    client.post('/sus', data={
        'q1': 3, 'q2': 3, 'q3': 3, 'q4': 3, 'q5': 3,
        'q6': 3, 'q7': 3, 'q8': 3, 'q9': 3, 'q10': 3
    }, follow_redirects=True)

    with app_instance.app_context():
        db = get_db()
        row = db.execute("SELECT score FROM sus_responses ORDER BY id DESC LIMIT 1").fetchone()
        assert row['score'] == 50.0

# -------------------------------------------------------------
# 6. Task Logging & Anonymized CSV Export Tests
# -------------------------------------------------------------
def test_task_logging_and_csv_anonymization(client, app_instance):
    """Verify task telemetry recording and anonymized dataset exports."""
    register_user(client, 'tester_xyz', 'tester@xyz.edu')

    # Log prototype task
    task_res = client.post('/task/complete', data={
        'task_name': 'Find CS101 Notes',
        'started_at': '2026-11-21T10:00:00Z',
        'ended_at': '2026-11-21T10:00:25Z',
        'duration_sec': 25.4,
        'clicks': 6,
        'errors': 0,
        'success': '1'
    }, follow_redirects=True)
    assert task_res.status_code == 200

    with app_instance.app_context():
        db = get_db()
        task = db.execute("SELECT * FROM tasks WHERE task_name = 'Find CS101 Notes'").fetchone()
        assert task is not None
        assert task['method'] == 'prototype'
        assert task['clicks'] == 6
        assert task['success'] == 1

    client.post('/logout', follow_redirects=True)

    # Log in as admin to test CSV exports
    register_user(client, 'admin_exp', 'admin@xyz.edu')

    # Test baseline entry by facilitator
    base_res = client.post('/admin/baseline', data={
        'task_name': 'Locate notes on Discord',
        'duration_sec': 142.0,
        'clicks': 18,
        'errors': 2,
        'success': '1'
    }, follow_redirects=True)
    assert base_res.status_code == 200

    # Test Anonymized Users CSV export
    csv_res = client.get('/admin/export/users_anonymized')
    assert csv_res.status_code == 200
    csv_text = csv_res.data.decode('utf-8')
    assert 'email' not in csv_text.lower()
    assert 'password' not in csv_text.lower()
    assert 'university_name' in csv_text
    assert 'credits' in csv_text


# -------------------------------------------------------------
# 7. Phase 1 Verification Tests
# -------------------------------------------------------------
def test_registration_atomic_success(client, app_instance):
    """
    Assert registration through the real HTTP route:
    - HTTP 302/200, no 500 error
    - User exists exactly once in users table
    - Ledger has exactly one signup row
    - User is logged in and redirected to consent with success flash
    """
    client.post('/logout', follow_redirects=True)
    res = client.post('/register', data={
        'username': 'atomic_user',
        'email': 'atomic_user@xyz.edu',
        'password': 'password123',
        'agree_terms': '1'
    }, follow_redirects=False)

    # Must redirect to /consent
    assert res.status_code == 302
    assert res.headers.get('Location') == '/consent'

    # Follow to consent page
    consent_page = client.get('/consent')
    assert consent_page.status_code == 200
    assert b"Welcome to StudyExchange, atomic_user" in consent_page.data

    with app_instance.app_context():
        db = get_db()
        users = db.execute("SELECT * FROM users WHERE email = 'atomic_user@xyz.edu'").fetchall()
        assert len(users) == 1
        u = users[0]
        assert u['username'] == 'atomic_user'
        assert u['credits'] == 20

        ledger_rows = db.execute(
            "SELECT * FROM ledger WHERE user_id = ? AND reason = 'signup'",
            (u['id'],)
        ).fetchall()
        assert len(ledger_rows) == 1
        assert ledger_rows[0]['amount'] == 20


def test_credit_ui_fresh_rendered_html(client, app_instance):
    """
    Assert the credit balance shown in the rendered HTML updates immediately
    after each credit-changing action (signup, upload, download).
    """
    # 1. Register user (starts with 20 credits)
    register_user(client, 'credit_user1', 'credit1@xyz.edu')
    dash1 = client.get('/dashboard')
    assert dash1.status_code == 200
    assert b'class="credit-balance-val">20<' in dash1.data

    # 2. Upload file -> +10 credits (total 30 credits)
    upload_res = client.post('/upload', data={
        'title': 'Credit Sync Note',
        'subject': 'Physics',
        'semester': 1,
        'type': 'Lecture Notes',
        'description': 'Notes to test credit UI freshness',
        'confirm_copyright': '1',
        'file': (io.BytesIO(b'%PDF-1.4 sample content'), 'sync_test.pdf')
    }, follow_redirects=True)
    assert upload_res.status_code == 200
    # The rendered file_detail page immediately reflects 30 credits in the navbar
    assert b'class="credit-balance-val">30<' in upload_res.data

    # Also verify dashboard renders 30 credits fresh from DB
    dash2 = client.get('/dashboard')
    assert b'class="credit-balance-val">30<' in dash2.data

    # Get file id
    with app_instance.app_context():
        db = get_db()
        f = db.execute("SELECT id FROM files WHERE title = 'Credit Sync Note'").fetchone()
        f_id = f['id']

    # 3. Second user downloads file -> 20 - 5 = 15 credits
    register_user(client, 'credit_user2', 'credit2@xyz.edu')
    file_page = client.get(f'/file/{f_id}')
    assert b'class="credit-balance-val">20<' in file_page.data

    # Download file
    dl_res = client.get(f'/download/{f_id}')
    assert dl_res.status_code == 200

    # Next render of browse or dashboard immediately renders 15 credits
    dash3 = client.get('/dashboard')
    assert b'class="credit-balance-val">15<' in dash3.data
    assert b'class="credit-balance-val">20<' not in dash3.data
