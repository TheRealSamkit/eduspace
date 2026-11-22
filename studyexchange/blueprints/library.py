"""
Core library routes for StudyExchange.

Includes repository browsing, search/filter, material detail views, ratings,
reporting, and credit-deducted file downloads with institutional isolation.
Depends on Flask, db.get_db, and studyexchange.security.login_required.
"""

from flask import (
    Blueprint, render_template, request, redirect,
    url_for, flash, g, abort, send_from_directory, current_app
)
from config import Config
from db import get_db
from studyexchange.security import login_required

bp = Blueprint('library', __name__)


@bp.route('/browse')
@login_required
def browse():
    """
    Browse and search study material with university isolation.

    Returns:
        Response: Rendered browse.html with isolated files and filter options.
    """
    search_query = request.args.get('q', '').strip()
    subject_filter = request.args.get('subject', '').strip()
    semester_filter = request.args.get('semester', '').strip()
    type_filter = request.args.get('type', '').strip()
    sort_by = request.args.get('sort', 'newest')
    page = max(1, request.args.get('page', 1, type=int))
    per_page = 9

    db = get_db()

    # Base query with university isolation and active status
    sql_base = """
        FROM files f
        JOIN users u ON f.uploader_id = u.id
        LEFT JOIN ratings r ON f.id = r.file_id
        LEFT JOIN downloads d ON f.id = d.file_id
        WHERE f.university_id = ? AND f.status = 'active'
    """
    params = [g.user['university_id']]

    if search_query:
        sql_base += " AND (f.title LIKE ? OR f.subject LIKE ? OR f.description LIKE ?)"
        term = f"%{search_query}%"
        params.extend([term, term, term])

    if subject_filter:
        sql_base += " AND f.subject = ?"
        params.append(subject_filter)

    if semester_filter:
        sql_base += " AND f.semester = ?"
        params.append(semester_filter)

    if type_filter:
        sql_base += " AND f.type = ?"
        params.append(type_filter)

    count_sql = f"SELECT COUNT(DISTINCT f.id) {sql_base}"
    total_items = db.execute(count_sql, params).fetchone()[0]
    total_pages = max(1, (total_items + per_page - 1) // per_page)
    offset = (page - 1) * per_page

    order_clause = "ORDER BY f.created_at DESC"
    if sort_by == 'top_rated':
        order_clause = "ORDER BY avg_rating DESC, rating_count DESC, f.created_at DESC"
    elif sort_by == 'most_downloaded':
        order_clause = "ORDER BY download_count DESC, f.created_at DESC"
    elif sort_by == 'oldest':
        order_clause = "ORDER BY f.created_at ASC"

    select_sql = f"""
        SELECT f.id, f.title, f.subject, f.semester, f.type, f.description,
               f.size, f.created_at, u.username as uploader_username,
               COALESCE(AVG(r.stars), 0.0) as avg_rating,
               COUNT(DISTINCT r.id) as rating_count,
               COUNT(DISTINCT d.id) as download_count
        {sql_base}
        GROUP BY f.id
        {order_clause}
        LIMIT ? OFFSET ?
    """
    query_params = list(params) + [per_page, offset]
    files = db.execute(select_sql, query_params).fetchall()

    subjects = db.execute(
        "SELECT DISTINCT subject FROM files WHERE university_id = ? AND status = 'active' ORDER BY subject",
        (g.user['university_id'],)
    ).fetchall()

    return render_template(
        'browse.html',
        files=files,
        total_items=total_items,
        page=page,
        total_pages=total_pages,
        search_query=search_query,
        subject_filter=subject_filter,
        semester_filter=semester_filter,
        type_filter=type_filter,
        sort_by=sort_by,
        subjects=[s['subject'] for s in subjects]
    )


@bp.route('/file/<int:file_id>')
@login_required
def file_detail(file_id):
    """
    Display document metadata, rating breakdown, and download availability.

    Args:
        file_id (int): Primary key of the file.

    Returns:
        Response: Rendered file_detail.html or 404 if not found / different university.
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
        WHERE f.id = ? AND f.university_id = ? AND f.status = 'active'
        GROUP BY f.id
        """,
        (file_id, g.user['university_id'])
    ).fetchone()

    if not file:
        abort(404, description="Material not found or access restricted to its institution.")

    is_uploader = (file['uploader_id'] == g.user['id'])
    already_downloaded = db.execute(
        "SELECT 1 FROM downloads WHERE user_id = ? AND file_id = ?",
        (g.user['id'], file_id)
    ).fetchone() is not None

    user_rating = db.execute(
        "SELECT stars FROM ratings WHERE user_id = ? AND file_id = ?",
        (g.user['id'], file_id)
    ).fetchone()

    return render_template(
        'file_detail.html',
        file=file,
        is_uploader=is_uploader,
        already_downloaded=already_downloaded,
        user_stars=user_rating['stars'] if user_rating else None
    )


@bp.route('/file/<int:file_id>/rate', methods=['POST'])
@login_required
def rate_file(file_id):
    """
    Submit or update 1-5 star user rating.

    Args:
        file_id (int): Primary key of the file to rate.

    Returns:
        Response: Redirect to file_detail page.
    """
    db = get_db()
    file = db.execute(
        "SELECT id FROM files WHERE id = ? AND university_id = ? AND status = 'active'",
        (file_id, g.user['university_id'])
    ).fetchone()

    if not file:
        abort(404, description="Material not found or access restricted.")

    stars = request.form.get('stars', type=int)
    if not stars or not (1 <= stars <= 5):
        flash("Please choose a rating between 1 and 5 stars.", "warning")
        return redirect(url_for('library.file_detail', file_id=file_id))

    db.execute(
        """
        INSERT INTO ratings (user_id, file_id, stars)
        VALUES (?, ?, ?)
        ON CONFLICT(user_id, file_id) DO UPDATE SET stars = excluded.stars
        """,
        (g.user['id'], file_id, stars)
    )
    db.commit()
    flash(f"Thank you! You rated this material {stars} star{'s' if stars > 1 else ''}.", "success")
    return redirect(url_for('library.file_detail', file_id=file_id))


@bp.route('/file/<int:file_id>/report', methods=['POST'])
@login_required
def report_file(file_id):
    """
    Submit moderation report for copyright infringement or inappropriate content.

    Args:
        file_id (int): Primary key of the file.

    Returns:
        Response: Redirect to file_detail page.
    """
    db = get_db()
    file = db.execute(
        "SELECT id FROM files WHERE id = ? AND university_id = ? AND status = 'active'",
        (file_id, g.user['university_id'])
    ).fetchone()

    if not file:
        abort(404, description="Material not found or access restricted.")

    reason = request.form.get('reason', '').strip()
    if not reason:
        flash("Please provide a reason for reporting this file.", "warning")
        return redirect(url_for('library.file_detail', file_id=file_id))

    db.execute(
        """
        INSERT INTO reports (user_id, file_id, reason, status)
        VALUES (?, ?, ?, 'open')
        """,
        (g.user['id'], file_id, reason)
    )
    db.commit()
    flash("Your report has been received and will be reviewed by university administrators.", "info")
    return redirect(url_for('library.file_detail', file_id=file_id))


@bp.route('/download/<int:file_id>')
@login_required
def download_file(file_id):
    """
    Deduct download credits and send file attachment.

    Args:
        file_id (int): Primary key of the file.

    Returns:
        Response: File attachment or redirect on error.
    """
    db = get_db()
    file = db.execute(
        "SELECT * FROM files WHERE id = ? AND university_id = ? AND status = 'active'",
        (file_id, g.user['university_id'])
    ).fetchone()

    if not file:
        abort(404, description="Material not found or access restricted to students of its institution.")

    is_uploader = (file['uploader_id'] == g.user['id'])
    already_downloaded = db.execute(
        "SELECT 1 FROM downloads WHERE user_id = ? AND file_id = ?",
        (g.user['id'], file_id)
    ).fetchone() is not None

    cost = current_app.config.get('DOWNLOAD_COST', Config.DOWNLOAD_COST)

    # Atomic credit balance verification and deduction
    cursor = db.cursor()
    try:
        cursor.execute("BEGIN IMMEDIATE")

        if not is_uploader and not already_downloaded:
            user_record = cursor.execute(
                "SELECT credits FROM users WHERE id = ?",
                (g.user['id'],)
            ).fetchone()

            if not user_record or user_record['credits'] < cost:
                db.rollback()
                flash(
                    f"Insufficient credits! Downloading this document requires {cost} credits. "
                    f"Your current balance is {g.user['credits']}. Upload study materials to earn more.",
                    "danger"
                )
                return redirect(url_for('library.file_detail', file_id=file_id))

            cursor.execute(
                "UPDATE users SET credits = credits - ? WHERE id = ?",
                (cost, g.user['id'])
            )
            cursor.execute(
                """
                INSERT INTO ledger (user_id, amount, reason, file_id)
                VALUES (?, ?, 'download', ?)
                """,
                (g.user['id'], -cost, file_id)
            )

        if not already_downloaded:
            cursor.execute(
                "INSERT INTO downloads (user_id, file_id) VALUES (?, ?)",
                (g.user['id'], file_id)
            )

        db.commit()
    except Exception:
        db.rollback()
        flash("An error occurred during download processing. Please try again.", "danger")
        return redirect(url_for('library.file_detail', file_id=file_id))

    upload_folder = current_app.config.get('UPLOAD_FOLDER', Config.UPLOAD_FOLDER)
    return send_from_directory(
        upload_folder,
        file['stored_name'],
        as_attachment=True,
        download_name=file['original_name']
    )
