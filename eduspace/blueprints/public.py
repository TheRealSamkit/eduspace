"""
Public library routes for EduSpace.

Allows guests and authenticated users to browse and inspect public-visibility
study materials while requiring authentication for preview, download, and actions.
"""

from flask import Blueprint, render_template, request, redirect, url_for, g, abort
from db import get_db
from eduspace.services.files import query_browse_materials, get_bookmarked_file_ids
from eduspace.services.telemetry import log_event_entry

bp = Blueprint('public', __name__)


@bp.route('/library')
def public_library():
    """
    Display active public-visibility study materials for guests and logged-in users.

    Returns:
        Response: Rendered public_library.html.
    """
    search_query = request.args.get('q', '').strip()
    subject_filter = request.args.get('subject', '').strip()
    semester_filter = request.args.get('semester', '').strip()
    type_filter = request.args.get('type', '').strip()
    sort_by = request.args.get('sort', 'newest')
    page = max(1, request.args.get('page', 1, type=int))

    db = get_db()
    result = query_browse_materials(
        db=db,
        user=g.user,
        search_query=search_query,
        subject_filter=subject_filter,
        semester_filter=semester_filter,
        type_filter=type_filter,
        sort_by=sort_by,
        page=page,
        per_page=9,
        scope='public'
    )

    if g.user is None:
        try:
            log_event_entry(db, g.session_id, None, 'public_view_guest', request.path, 'listing')
        except Exception:
            pass

    bookmarked_ids = get_bookmarked_file_ids(db, g.user['id']) if g.user else set()

    return render_template(
        'public_library.html',
        files=result['files'],
        total_items=result['total_items'],
        page=page,
        total_pages=result['total_pages'],
        search_query=search_query,
        subject_filter=subject_filter,
        semester_filter=semester_filter,
        type_filter=type_filter,
        sort_by=sort_by,
        subjects=result['subjects'],
        bookmarked_ids=bookmarked_ids
    )


@bp.route('/library/<int:file_id>')
def public_detail(file_id):
    """
    Guest-accessible public material detail page; redirects logged-in users to /file/<id>.

    Returns:
        Response: Redirect or rendered public_detail.html, or 404 if not public/active.
    """
    db = get_db()
    file = db.execute(
        """
        SELECT f.*, u.username as uploader_username,
               COALESCE(AVG(r.stars), 0.0) as avg_rating,
               COUNT(DISTINCT r.id) as rating_count,
               COUNT(DISTINCT d.id) as download_count
        FROM files f
        JOIN users u ON f.uploader_id = u.id
        LEFT JOIN ratings r ON f.id = r.file_id
        LEFT JOIN downloads d ON f.id = d.file_id
        WHERE f.id = ? AND f.visibility = 'public' AND f.status = 'active'
        GROUP BY f.id
        """,
        (file_id,)
    ).fetchone()

    if not file:
        abort(404, description="Public material not found.")

    if g.user:
        return redirect(url_for('library.file_detail', file_id=file_id))

    try:
        log_event_entry(db, g.session_id, None, 'public_view_guest', request.path, f"file_id={file_id}")
    except Exception:
        pass

    return render_template('public_detail.html', file=file)
