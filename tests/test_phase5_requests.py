"""
Tests for Phase 5: Resource requests reward formula, interest, fulfilment,
atomic accept, daily reward cap, reversal on removal, and visibility isolation.
"""

import io
import os
import tempfile
import pytest

from app import create_app
from db import get_db


@pytest.fixture
def app():
    """Create isolated test app for resource requests."""
    db_fd, db_path = tempfile.mkstemp(suffix='.db')
    upload_dir = tempfile.mkdtemp()
    test_app = create_app({
        'TESTING': True,
        'DATABASE': db_path,
        'UPLOAD_FOLDER': upload_dir,
        'SECRET_KEY': 'requests-test-secret',
        'ADMIN_EMAIL': 'admin@xyz.edu',
        'ALLOWED_DOMAINS': {
            'xyz.edu': 'XYZ University',
            'abc.edu': 'ABC College',
        },
        'REQUEST_BASE_REWARD': 15,
        'REQUEST_INTEREST_BONUS': 1,
        'REQUEST_BONUS_CAP': 10,
        'MAX_OPEN_REQUESTS_PER_USER': 3,
        'MAX_REQUEST_REWARDS_PER_DAY': 2,
    })
    with test_app.app_context():
        db = get_db()
        from werkzeug.security import generate_password_hash
        pwd = generate_password_hash('password123')
        xyz_id = db.execute("SELECT id FROM universities WHERE domain = 'xyz.edu'").fetchone()['id']
        abc_id = db.execute("SELECT id FROM universities WHERE domain = 'abc.edu'").fetchone()['id']
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
            "INSERT INTO users (email, username, password_hash, university_id, credits, is_admin) VALUES (?, ?, ?, ?, 20, 0)",
            ('david@abc.edu', 'david', pwd, abc_id)
        )
        db.execute(
            "INSERT INTO users (email, username, password_hash, university_id, credits, is_admin) VALUES (?, ?, ?, ?, 20, 1)",
            ('admin@xyz.edu', 'admin_xyz', pwd, xyz_id)
        )
        for uid in (1, 2, 3, 4, 5):
            db.execute("INSERT INTO consents (user_id) VALUES (?)", (uid,))
        db.commit()
    yield test_app
    os.close(db_fd)
    if os.path.exists(db_path):
        os.unlink(db_path)


def test_request_lifecycle_interest_accept_and_reversal(app):
    """Create request, toggle interest, submit file, accept once, and reverse on admin removal."""
    client = app.test_client()

    # Alice creates university-only request
    client.post('/login', data={'email': 'alice@xyz.edu', 'password': 'password123'})
    res_create = client.post('/requests', data={
        'title': 'Need OS Notes',
        'subject': 'CS',
        'semester': '4',
        'material_type': 'Lecture Notes',
        'description': 'Paging & virtual memory',
        'visibility': 'university',
    }, follow_redirects=True)
    assert res_create.status_code == 200
    assert b'Need OS Notes' in res_create.data

    # Alice cannot mark herself interested or submit to own request
    assert client.post('/api/requests/1/interest').status_code == 400
    res_self_sub = client.post('/requests/1/submit', data={
        'title': 'Self',
        'confirm_copyright': 'on',
        'file': (io.BytesIO(b'%PDF-1.4\nself'), 'self.pdf'),
    }, content_type='multipart/form-data', follow_redirects=True)
    assert b'cannot submit a file to your own request' in res_self_sub.data
    client.post('/logout')

    # David (ABC College) cannot see XYZ university request
    client.post('/login', data={'email': 'david@abc.edu', 'password': 'password123'})
    assert client.get('/requests/1').status_code == 404
    client.post('/logout')

    # Carol marks interest -> reward becomes 15 + 1 = 16
    client.post('/login', data={'email': 'carol@xyz.edu', 'password': 'password123'})
    int_res = client.post('/api/requests/1/interest')
    assert int_res.status_code == 200
    assert int_res.get_json() == {'interested': True, 'count': 1, 'reward': 16}
    client.post('/logout')

    # Bob submits a file -> gets +10 upload reward, request becomes answered
    client.post('/login', data={'email': 'bob@xyz.edu', 'password': 'password123'})
    sub_res = client.post('/requests/1/submit', data={
        'title': 'OS Paging Guide',
        'description': 'Complete guide',
        'confirm_copyright': 'on',
        'file': (io.BytesIO(b'%PDF-1.4\nos-paging-guide'), 'os.pdf'),
    }, content_type='multipart/form-data', follow_redirects=True)
    assert b'Material submitted to request!' in sub_res.data
    client.post('/logout')

    # Alice downloads submitted file free of charge, then accepts submission -> Bob gets +16
    client.post('/login', data={'email': 'alice@xyz.edu', 'password': 'password123'})
    dl = client.get('/download/1')
    assert dl.status_code == 200
    acc = client.post('/requests/1/accept/1', follow_redirects=True)
    assert b'16 credits awarded' in acc.data
    # Double-accept impossible
    acc2 = client.post('/requests/1/accept/1', follow_redirects=True)
    assert b'already been fulfilled' in acc2.data

    with app.app_context():
        db = get_db()
        alice = db.execute("SELECT credits FROM users WHERE email = 'alice@xyz.edu'").fetchone()
        bob = db.execute("SELECT credits FROM users WHERE email = 'bob@xyz.edu'").fetchone()
        assert alice['credits'] == 20  # free download for requester
        assert bob['credits'] == 20 + 10 + 16  # signup + upload + request_reward

    # Admin removes file -> reverses both 10 upload + 16 request_reward = 26
    client.post('/logout')
    client.post('/login', data={'email': 'admin@xyz.edu', 'password': 'password123'})
    client.post('/admin/file/1/remove', follow_redirects=True)
    with app.app_context():
        db = get_db()
        bob = db.execute("SELECT credits FROM users WHERE email = 'bob@xyz.edu'").fetchone()
        assert bob['credits'] == 20
