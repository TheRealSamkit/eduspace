"""
User personal dashboard route for StudyExchange.

Displays credit ledger history, uploaded materials, and downloaded documents.
Depends on Flask, db.get_db, and studyexchange.security.login_required.
"""

from flask import Blueprint, render_template, g
from db import get_db
from studyexchange.security import login_required

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

    downloads = db.execute(
        """
        SELECT d.created_at as downloaded_at, f.id as file_id, f.title, f.subject,
               f.semester, f.type, f.size, f.status, u.username as uploader_username
        FROM downloads d
        JOIN files f ON d.file_id = f.id
        JOIN users u ON f.uploader_id = u.id
        WHERE d.user_id = ? AND f.university_id = ?
        ORDER BY d.created_at DESC
        """,
        (user_id, g.user['university_id'])
    ).fetchall()

    return render_template(
        'dashboard.html',
        ledger=ledger,
        uploads=uploads,
        downloads=downloads
    )
