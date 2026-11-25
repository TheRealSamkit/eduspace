"""
User personal dashboard route for EduSpace.

Displays credit ledger history, uploaded materials, and downloaded documents.
Depends on Flask, db.get_db, and eduspace.security.login_required.
"""

from flask import Blueprint, render_template, g
from db import get_db
from eduspace.security import login_required
from eduspace.services.visibility import file_visibility_where

bp = Blueprint('dashboard', __name__)


@bp.route('/dashboard')
@login_required
def dashboard():
    """
    Render personal dashboard with credit balance, ledger history, uploads, and downloads.

    Returns:
        Response: Rendered dashboard.html.
    """
    db = get_db()
    user_id = g.user['id']

    ledger = db.execute(
        """
        SELECT l.*, f.title as file_title
        FROM ledger l
        LEFT JOIN files f ON l.file_id = f.id
        WHERE l.user_id = ?
        ORDER BY l.created_at DESC
        LIMIT 50
        """,
        (user_id,)
    ).fetchall()

    uploads = db.execute(
        """
        SELECT f.*,
               COALESCE(AVG(r.stars), 0.0) as avg_rating,
               COUNT(DISTINCT r.id) as rating_count,
               COUNT(DISTINCT d.id) as download_count
        FROM files f
        LEFT JOIN ratings r ON f.id = r.file_id
        LEFT JOIN downloads d ON f.id = d.file_id
        WHERE f.uploader_id = ?
        GROUP BY f.id
        ORDER BY f.created_at DESC
        """,
        (user_id,)
    ).fetchall()

    vis_clause, vis_params = file_visibility_where(g.user, scope='visible', alias='f')
    downloads = db.execute(
        f"""
        SELECT d.created_at as downloaded_at, f.id as file_id, f.title, f.subject,
               f.semester, f.type, f.size, f.status, u.username as uploader_username
        FROM downloads d
        JOIN files f ON d.file_id = f.id
        JOIN users u ON f.uploader_id = u.id
        WHERE d.user_id = ? AND {vis_clause}
        ORDER BY d.created_at DESC
        """,
        [user_id] + vis_params
    ).fetchall()

    return render_template(
        'dashboard.html',
        ledger=ledger,
        uploads=uploads,
        downloads=downloads
    )
