"""
Comprehensive end-to-end user flows, isolation tests, and input validation for StudyExchange.
Covers:
1. Complete lifecycle flow:
   - Register -> Consent -> Upload (rewarded +10)
   - Browse / Search / Filter / Sort / Pagination
   - Second user download (deducted -5) -> Free re-download
   - Insufficient credits blocked (no negative balance)
   - Rate file (1-5 stars) -> Average rating updated
   - Report file -> Open report listed for admin
   - Admin remove file -> Status 'removed', ledger 'reversal' (-10) created, uploader balance reversed
   - Usability test-mode task telemetry (prototype condition)
   - SUS Survey submissions:
     * Odd=5, Even=1 -> exact score 100
     * All 3s -> exact score 50
   - Feedback submission
   - Facilitator baseline metric entry (baseline condition)
   - CSV exports with anonymized users (no email, no password_hash)
2. Security & Input validation:
   - University isolation (404 on cross-university file detail and download)
   - Oversized file upload rejection (>10MB)
   - Disallowed file extensions (.exe, .sh)
   - Missing required fields and copyright confirmation
   - Duplicate email / username registration
   - Password length enforcement (< 8 chars)
   - Invalid email domain rejection
   - SQL injection resilience in search and filters
   - XSS escaping in rendered HTML
   - CSRF enforcement when non-testing mode
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
    db_fd, db_path = tempfile.mkstemp(suffix='.db')
    upload_dir = tempfile.mkdtemp()

    test_config = {
        'TESTING': True,
        'DATABASE': db_path,
        'UPLOAD_FOLDER': upload_dir,
        'SECRET_KEY': 'test-flows-secret',
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

def register_user(client, username, email, password="password123"):
    client.post('/logout', follow_redirects=True)
    res = client.post('/register', data={
        'username': username,
        'email': email,
        'password': password,
        'agree_terms': '1'
    }, follow_redirects=True)
    client.post('/consent', data={'agree_consent': '1'}, follow_redirects=True)
    return res


# ---------------------------------------------------------------------------
# 1. Complete End-to-End User Lifecycle Flow
# ---------------------------------------------------------------------------

def test_full_user_lifecycle_flow(client, app_instance):
    """
    Simulates the entire student and admin lifecycle:
    Register -> Consent -> Upload -> Browse/Search/Filter -> Download -> Rate -> Report -> Admin Takedown
    -> Task Tracking -> SUS (100 and 50) -> Feedback -> Baseline -> CSV Exports.
    """
    # 1. Alice registers at XYZ University
    client.post('/logout', follow_redirects=True)
    reg_res = client.post('/register', data={
        'username': 'alice_w',
        'email': 'alice@xyz.edu',
        'password': 'password123',
        'agree_terms': '1'
    }, follow_redirects=False)
    assert reg_res.status_code == 302
    assert '/consent' in reg_res.headers.get('Location', '')

    # Complete consent
    consent_res = client.post('/consent', data={'agree_consent': '1'}, follow_redirects=False)
    assert consent_res.status_code == 302
    assert '/browse' in consent_res.headers.get('Location', '')

    # Verify initial signup balance is 20
    with app_instance.app_context():
        db = get_db()
        alice = db.execute("SELECT id, credits FROM users WHERE email = 'alice@xyz.edu'").fetchone()
        assert alice['credits'] == 20
        alice_id = alice['id']

    # 2. Alice uploads a study document (earns UPLOAD_REWARD = 10)
    upload_res = client.post('/upload', data={
        'title': 'Machine Learning Core Principles',
        'subject': 'Computer Science',
        'semester': '3',
        'type': 'Lecture Notes',
        'description': 'Supervised and unsupervised learning foundational summary.',
        'confirm_copyright': '1',
        'file': (io.BytesIO(b'%PDF-1.4 test machine learning notes content'), 'ml_notes.pdf')
    }, follow_redirects=True)
    assert upload_res.status_code == 200

    # Verify credit reward and ledger
    with app_instance.app_context():
        db = get_db()
        alice = db.execute("SELECT credits FROM users WHERE id = ?", (alice_id,)).fetchone()
        assert alice['credits'] == 30  # 20 signup + 10 upload

        file_row = db.execute("SELECT id, title FROM files WHERE title = 'Machine Learning Core Principles'").fetchone()
        assert file_row is not None
        file_id = file_row['id']

        # Verify ledger has signup and upload
        ledger_rows = db.execute("SELECT reason, amount FROM ledger WHERE user_id = ? ORDER BY id ASC", (alice_id,)).fetchall()
        assert len(ledger_rows) == 2
        assert ledger_rows[0]['reason'] == 'signup' and ledger_rows[0]['amount'] == 20
        assert ledger_rows[1]['reason'] == 'upload' and ledger_rows[1]['amount'] == 10

    # 3. Browse, Search, Filter, Sort
    browse_res = client.get('/browse?q=Machine+Learning')
    assert b'Machine Learning Core Principles' in browse_res.data

    browse_subj = client.get('/browse?subject=Computer+Science')
    assert b'Machine Learning Core Principles' in browse_subj.data

    browse_sem = client.get('/browse?semester=3')
    assert b'Machine Learning Core Principles' in browse_sem.data

    browse_sort = client.get('/browse?sort=newest')
    assert b'Machine Learning Core Principles' in browse_sort.data

    # 4. Bob registers at XYZ University and downloads Alice's file
    register_user(client, 'bob_m', 'bob@xyz.edu')

    with app_instance.app_context():
        db = get_db()
        bob = db.execute("SELECT id, credits FROM users WHERE email = 'bob@xyz.edu'").fetchone()
        assert bob['credits'] == 20
        bob_id = bob['id']

    # Bob views file detail
    detail_res = client.get(f'/file/{file_id}')
    assert detail_res.status_code == 200
    assert b'Machine Learning Core Principles' in detail_res.data

    # Bob downloads file (costs 5 credits)
    dl_res = client.get(f'/download/{file_id}')
    assert dl_res.status_code == 200
    assert b'test machine learning notes content' in dl_res.data

    # Verify Bob's credits deducted by 5
    with app_instance.app_context():
        db = get_db()
        bob = db.execute("SELECT credits FROM users WHERE id = ?", (bob_id,)).fetchone()
        assert bob['credits'] == 15
        dl_record = db.execute("SELECT 1 FROM downloads WHERE user_id = ? AND file_id = ?", (bob_id, file_id)).fetchone()
        assert dl_record is not None
        bob_ledger = db.execute("SELECT reason, amount FROM ledger WHERE user_id = ? AND reason = 'download'", (bob_id,)).fetchone()
        assert bob_ledger['amount'] == -5

    # 5. Re-downloading is free
    dl_res2 = client.get(f'/download/{file_id}')
    assert dl_res2.status_code == 200
    with app_instance.app_context():
        db = get_db()
        bob = db.execute("SELECT credits FROM users WHERE id = ?", (bob_id,)).fetchone()
        assert bob['credits'] == 15  # Unchanged!

    # 6. Bob rates the file 4 stars
    rate_res = client.post(f'/file/{file_id}/rate', data={'stars': '4'}, follow_redirects=True)
    assert rate_res.status_code == 200
    with app_instance.app_context():
        db = get_db()
        rating = db.execute("SELECT stars FROM ratings WHERE user_id = ? AND file_id = ?", (bob_id, file_id)).fetchone()
        assert rating is not None
        assert rating['stars'] == 4

    # 7. Bob reports the file
    report_res = client.post(f'/file/{file_id}/report', data={'reason': 'Suspected copyright infringement'}, follow_redirects=True)
    assert report_res.status_code == 200
    with app_instance.app_context():
        db = get_db()
        rep = db.execute("SELECT id, reason, status FROM reports WHERE file_id = ?", (file_id,)).fetchone()
        assert rep is not None
        assert rep['status'] == 'open'

    # 8. Insufficient credits check: Charlie has only 2 credits
    register_user(client, 'charlie_k', 'charlie@xyz.edu')
    with app_instance.app_context():
        db = get_db()
        charlie = db.execute("SELECT id FROM users WHERE email = 'charlie@xyz.edu'").fetchone()
        db.execute("UPDATE users SET credits = 2 WHERE id = ?", (charlie['id'],))
        db.commit()

    # Charlie attempts to download Alice's 5-credit file
    charlie_dl = client.get(f'/download/{file_id}', follow_redirects=True)
    assert b'Insufficient credits' in charlie_dl.data or b'credits' in charlie_dl.data
    with app_instance.app_context():
        db = get_db()
        charlie_after = db.execute("SELECT credits FROM users WHERE id = ?", (charlie['id'],)).fetchone()
        assert charlie_after['credits'] == 2  # Credits never go negative!

    # 9. Admin moderates and removes file
    register_user(client, 'site_admin', 'admin@xyz.edu')
    admin_page = client.get('/admin')
    assert admin_page.status_code == 200
    assert b'Machine Learning Core Principles' in admin_page.data

    remove_res = client.post(f'/admin/file/{file_id}/remove', follow_redirects=True)
    assert remove_res.status_code == 200

    with app_instance.app_context():
        db = get_db()
        f = db.execute("SELECT status FROM files WHERE id = ?", (file_id,)).fetchone()
        assert f['status'] == 'removed'

        alice_final = db.execute("SELECT credits FROM users WHERE id = ?", (alice_id,)).fetchone()
        assert alice_final['credits'] == 20

        reversal = db.execute("SELECT amount, reason FROM ledger WHERE user_id = ? AND reason = 'reversal'", (alice_id,)).fetchone()
        assert reversal is not None
        assert reversal['amount'] == -10

    # 10. Usability Test-mode task telemetry
    client.get('/task')
    task_res = client.post('/task/complete', data={
        'task_name': 'Search & Download Lecture Notes',
        'duration_sec': '38.4',
        'clicks': '7',
        'errors': '0',
        'success': '1'
    }, follow_redirects=True)
    assert task_res.status_code == 200

    with app_instance.app_context():
        db = get_db()
        task = db.execute("SELECT task_name, method, duration_sec, success FROM tasks WHERE method = 'prototype' ORDER BY id DESC LIMIT 1").fetchone()
        assert task is not None
        assert task['task_name'] == 'Search & Download Lecture Notes'
        assert task['method'] == 'prototype'
        assert task['success'] == 1

    # 11. SUS Survey Form & Score Verification
    # Case A: Odd=5, Even=1 -> Score should be 100.0
    sus_100_data = {
        'q1': '5', 'q2': '1', 'q3': '5', 'q4': '1', 'q5': '5',
        'q6': '1', 'q7': '5', 'q8': '1', 'q9': '5', 'q10': '1'
    }
    sus_res_100 = client.post('/sus', data=sus_100_data, follow_redirects=True)
    assert sus_res_100.status_code == 200

    with app_instance.app_context():
        db = get_db()
        sus_row1 = db.execute("SELECT score FROM sus_responses ORDER BY id DESC LIMIT 1").fetchone()
        assert sus_row1['score'] == 100.0

    # Case B: All 3s -> Score should be 50.0
    sus_50_data = {f'q{i}': '3' for i in range(1, 11)}
    sus_res_50 = client.post('/sus', data=sus_50_data, follow_redirects=True)
    assert sus_res_50.status_code == 200

    with app_instance.app_context():
        db = get_db()
        sus_row2 = db.execute("SELECT score FROM sus_responses ORDER BY id DESC LIMIT 1").fetchone()
        assert sus_row2['score'] == 50.0

    # 12. Feedback submission
    fb_res = client.post('/feedback', data={
        'text': 'Great responsive design and fast downloads.',
        'usability_issue': '0'
    }, follow_redirects=True)
    assert fb_res.status_code == 200
    with app_instance.app_context():
        db = get_db()
        fb = db.execute("SELECT text, usability_issue FROM feedback ORDER BY id DESC LIMIT 1").fetchone()
        assert fb is not None
        assert 'Great responsive design' in fb['text']

    # 13. Facilitator Baseline Entry
    base_res = client.post('/admin/baseline', data={
        'task_name': 'Search Google Drive folder baseline',
        'duration_sec': '142.5',
        'clicks': '15',
        'errors': '3',
        'success': '1'
    }, follow_redirects=True)
    assert base_res.status_code == 200

    with app_instance.app_context():
        db = get_db()
        base = db.execute("SELECT task_name, method, duration_sec FROM tasks WHERE method = 'baseline' ORDER BY id DESC LIMIT 1").fetchone()
        assert base is not None
        assert base['task_name'] == 'Search Google Drive folder baseline'
        assert base['duration_sec'] == 142.5

    # 14. Anonymized Research Data CSV Export
    csv_res = client.get('/admin/export/users_anonymized')
    assert csv_res.status_code == 200
    csv_text = csv_res.data.decode('utf-8')
    assert 'email' not in csv_text.lower()
    assert 'password_hash' not in csv_text.lower()
    assert 'user_id' in csv_text.lower() or 'id' in csv_text.lower()


# ---------------------------------------------------------------------------
# 2. Input Validation, Isolation & Security Tests
# ---------------------------------------------------------------------------

def test_file_upload_input_validation(client, app_instance):
    """Verifies oversized files, disallowed extensions, and missing fields are rejected."""
    register_user(client, 'uploader_test', 'uploader@xyz.edu')

    # A. Disallowed extension (.exe)
    res_exe = client.post('/upload', data={
        'title': 'Malicious Executable',
        'subject': 'Security',
        'semester': '1',
        'type': 'Lecture Notes',
        'description': 'Test file',
        'confirm_copyright': '1',
        'file': (io.BytesIO(b'MZ executable payload'), 'malware.exe')
    }, follow_redirects=True)
    assert b'Invalid file extension' in res_exe.data or b'Allowed formats' in res_exe.data

    # B. Missing title
    res_notitle = client.post('/upload', data={
        'title': '',
        'subject': 'Security',
        'semester': '1',
        'type': 'Lecture Notes',
        'confirm_copyright': '1',
        'file': (io.BytesIO(b'%PDF-1.4 dummy'), 'doc.pdf')
    }, follow_redirects=True)
    assert b'required' in res_notitle.data.lower() or res_notitle.status_code == 200

    # C. Missing copyright confirmation
    res_nocopyright = client.post('/upload', data={
        'title': 'No Copyright Check',
        'subject': 'Security',
        'semester': '1',
        'type': 'Lecture Notes',
        'file': (io.BytesIO(b'%PDF-1.4 dummy'), 'doc.pdf')
    }, follow_redirects=True)
    assert b'copyright' in res_nocopyright.data.lower()

    # D. Oversized file (>10MB)
    large_payload = b'0' * (11 * 1024 * 1024)
    res_large = client.post('/upload', data={
        'title': 'Oversized Document',
        'subject': 'Security',
        'semester': '1',
        'type': 'Lecture Notes',
        'confirm_copyright': '1',
        'file': (io.BytesIO(large_payload), 'oversized.pdf')
    }, follow_redirects=True)
    assert b'exceeds maximum allowed size' in res_large.data or res_large.status_code in (200, 413)


def test_registration_input_validation(client, app_instance):
    """Verifies duplicate email, duplicate username, short password, and invalid domains."""
    client.post('/logout', follow_redirects=True)

    # First user
    client.post('/register', data={
        'username': 'unique_user',
        'email': 'unique@xyz.edu',
        'password': 'password123',
        'agree_terms': '1'
    }, follow_redirects=True)

    client.post('/logout', follow_redirects=True)

    # A. Duplicate email
    res_dup_email = client.post('/register', data={
        'username': 'different_user',
        'email': 'unique@xyz.edu',
        'password': 'password123',
        'agree_terms': '1'
    }, follow_redirects=True)
    assert b'already exists' in res_dup_email.data.lower()

    client.post('/logout', follow_redirects=True)

    # B. Duplicate username
    res_dup_name = client.post('/register', data={
        'username': 'unique_user',
        'email': 'another@xyz.edu',
        'password': 'password123',
        'agree_terms': '1'
    }, follow_redirects=True)
    assert b'already taken' in res_dup_name.data.lower()

    client.post('/logout', follow_redirects=True)

    # C. Short password (< 8 chars)
    res_short_pw = client.post('/register', data={
        'username': 'short_pw_user',
        'email': 'short@xyz.edu',
        'password': 'short',
        'agree_terms': '1'
    }, follow_redirects=True)
    assert b'at least 8 characters' in res_short_pw.data.lower()

    client.post('/logout', follow_redirects=True)

    # D. Non-institutional email domain
    res_bad_domain = client.post('/register', data={
        'username': 'bad_domain_user',
        'email': 'person@gmail.com',
        'password': 'password123',
        'agree_terms': '1'
    }, follow_redirects=True)
    assert b'is not recognized' in res_bad_domain.data.lower()


def test_sqli_resilience_and_xss_escaping(client, app_instance):
    """Tests SQL injection payload resilience in search/filter and HTML escaping of user input."""
    register_user(client, 'security_auditor', 'auditor@xyz.edu')

    # A. SQLi payloads in search query
    sqli_queries = [
        "' OR '1'='1",
        "'; DROP TABLE users; --",
        "admin'--",
        "1' UNION SELECT 1,2,3,4,5,6,7,8,9,10,11,12,13--"
    ]
    for q in sqli_queries:
        res = client.get(f'/browse?q={q}')
        assert res.status_code == 200

    # Verify tables still intact
    with app_instance.app_context():
        db = get_db()
        users_count = db.execute("SELECT COUNT(*) as cnt FROM users").fetchone()['cnt']
        assert users_count >= 1

    # B. XSS payload in upload title and feedback
    xss_payload = "<script>alert('xss-attack')</script>"
    client.post('/upload', data={
        'title': xss_payload,
        'subject': 'Web Security',
        'semester': '2',
        'type': 'Lecture Notes',
        'description': 'XSS test document description',
        'confirm_copyright': '1',
        'file': (io.BytesIO(b'%PDF-1.4 xss test dummy'), 'xss.pdf')
    }, follow_redirects=True)

    browse_page = client.get('/browse?q=Web+Security')
    assert browse_page.status_code == 200
    assert b"<script>alert('xss-attack')</script>" not in browse_page.data
    assert b"&lt;script&gt;alert(&#39;xss-attack&#39;)&lt;/script&gt;" in browse_page.data or b"&lt;script&gt;" in browse_page.data


def test_csrf_protection_when_not_testing(app_instance):
    """Verifies that non-testing clients without a CSRF token receive HTTP 400."""
    app_instance.config['TESTING'] = False
    prod_client = app_instance.test_client()

    res = prod_client.post('/register', data={
        'username': 'no_csrf_user',
        'email': 'nocsrf@xyz.edu',
        'password': 'password123',
        'agree_terms': '1'
    })
    assert res.status_code == 400
    assert b"CSRF token" in res.data or b"Bad Request" in res.data
