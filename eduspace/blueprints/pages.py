"""
Public and informational page routes for EduSpace.

Includes landing page, terms of service, and browser favicon.
Depends on Flask (Blueprint, render_template, redirect, url_for, g).
"""

from flask import Blueprint, render_template, redirect, url_for, g
from db import get_db
from eduspace.services.visibility import is_public_member

bp = Blueprint('pages', __name__)


@bp.route('/')
def index():
    """
    Public landing page or redirect to repository if already logged in.

    Returns:
        Response: Redirect to library.browse (or public_library for public members), else landing.html.
    """
    if g.user:
        if is_public_member(g.user):
            return redirect(url_for('library.public_library'))
        return redirect(url_for('library.browse'))

    db = get_db()
    public_count = db.execute(
        "SELECT COUNT(*) FROM files WHERE visibility = 'public' AND status = 'active'"
    ).fetchone()[0]
    recent_public_files = db.execute(
        """
        SELECT f.id, f.title, f.subject, f.semester, f.type, f.license,
               u.username as uploader_username
        FROM files f
        JOIN users u ON f.uploader_id = u.id
        WHERE f.visibility = 'public' AND f.status = 'active'
        ORDER BY f.created_at DESC
        LIMIT 4
        """
    ).fetchall()
    return render_template(
        'landing.html',
        force_light=True,
        public_count=public_count,
        recent_public_files=recent_public_files
    )


@bp.route('/terms')
def terms_page():
    """
    Display terms of service, copyright policy, and takedown procedures.

    Returns:
        Response: Rendered terms.html.
    """
    return render_template('terms.html')


@bp.route('/favicon.ico')
def favicon():
    """
    Handle browser favicon request without generating 404 logs.

    Returns:
        tuple: Empty response with 204 No Content.
    """
    return ("", 204)
