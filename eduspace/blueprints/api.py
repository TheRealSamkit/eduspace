"""
JSON API endpoints for client-side state, domain validation, telemetry, and live credit sync.

Depends on Flask, db.get_db, and eduspace.services.telemetry.
"""

from flask import Blueprint, request, jsonify, session, g, current_app
from db import get_db
from eduspace.security import login_required
from eduspace.services.telemetry import log_event_entry
from eduspace.services.visibility import can_view_file

bp = Blueprint('api', __name__)


@bp.route('/api/me', methods=['GET'])
def api_me():
    """
    Lightweight auth status check for clients and bfcache validation.

    Returns:
        tuple: JSON status object and HTTP status code.
    """
    if not g.user:
        return jsonify({'authenticated': False}), 401
    return jsonify({
        'authenticated': True,
        'user': {
            'id': g.user['id'],
            'username': g.user['username'],
            'email': g.user['email'],
            'university_id': g.user['university_id'],
            'university_name': g.user['university_name'],
            'credits': g.user['credits'],
            'is_admin': bool(g.user['is_admin'])
        }
    }), 200


@bp.route('/api/domain-check', methods=['GET'])
def api_domain_check():
    """
    Validate university institutional domain for registration.

    Returns:
        tuple: JSON object with domain recognition info, or 400/404.
    """
    email = request.args.get('email', '').strip().lower()
    if not email or '@' not in email:
        return jsonify({'valid': False, 'message': 'Invalid email format'}), 400

    domain = email.split('@')[-1]
    allowed_domains = current_app.config.get('ALLOWED_DOMAINS', {})
    if domain in allowed_domains:
        return jsonify({
            'valid': True,
            'domain': domain,
            'university_name': allowed_domains[domain]
        }), 200
    else:
        return jsonify({
            'valid': False,
            'message': 'This email domain is not supported yet'
        }), 404


@bp.route('/api/credits', methods=['GET'])
def api_credits():
    """
    Return fresh credit balance for the authenticated user as JSON.

    Returns:
        tuple: JSON object containing credit balance and logged_in flag.
    """
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'credits': 0, 'logged_in': False}), 200
    db = get_db()
    row = db.execute("SELECT credits FROM users WHERE id = ?", (user_id,)).fetchone()
    credits = row['credits'] if row else 0
    return jsonify({'credits': credits, 'logged_in': True}), 200


@bp.route('/api/event', methods=['POST'])
def api_event():
    """
    Receive telemetry events from client-side JS (clicks, validation errors, shortcuts).

    Returns:
        tuple: JSON acknowledgement and HTTP status code.
    """
    data = request.get_json(silent=True) or {}
    event_type = data.get('event_type', 'unknown')
    page = data.get('page', request.referrer or '/')
    detail = data.get('detail', '')

    try:
        db = get_db()
        log_event_entry(
            db=db,
            session_id=g.session_id,
            user_id=g.user['id'] if g.user else None,
            event_type=event_type,
            page=page,
            detail=detail
        )
        return jsonify({'status': 'ok'}), 200
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@bp.route('/api/bookmark/<int:file_id>', methods=['POST'])
@login_required
def api_toggle_bookmark(file_id):
    """
    Toggle a bookmark for a visible active file for the authenticated user.

    Returns:
        tuple: JSON {bookmarked: bool, count: int} and HTTP status code.
    """
    db = get_db()
    file = db.execute("SELECT * FROM files WHERE id = ?", (file_id,)).fetchone()
    if not can_view_file(g.user, file) or file['status'] != 'active':
        return jsonify({'error': 'Material not found or access restricted.'}), 404

    existing = db.execute(
        "SELECT id FROM bookmarks WHERE user_id = ? AND file_id = ?",
        (g.user['id'], file_id)
    ).fetchone()

    if existing:
        db.execute("DELETE FROM bookmarks WHERE id = ?", (existing['id'],))
        bookmarked = False
        evt = 'bookmark_remove'
    else:
        db.execute(
            "INSERT INTO bookmarks (user_id, file_id) VALUES (?, ?)",
            (g.user['id'], file_id)
        )
        bookmarked = True
        evt = 'bookmark_add'
    db.commit()

    count = db.execute(
        "SELECT COUNT(*) FROM bookmarks WHERE file_id = ?",
        (file_id,)
    ).fetchone()[0]

    try:
        log_event_entry(db, g.session_id, g.user['id'], evt, request.path, f"file_id={file_id}")
    except Exception:
        pass

    return jsonify({'bookmarked': bookmarked, 'count': count}), 200
