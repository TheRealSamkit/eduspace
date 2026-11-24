"""
Core library routes for EduSpace.

Includes repository browsing, search/filter, material detail views, ratings,
reporting, and credit-deducted file downloads with institutional isolation.
Depends on Flask, db.get_db, and eduspace.services.
"""

from flask import (
    Blueprint, render_template, request, redirect,
    url_for, flash, g, abort, send_from_directory, current_app
)
from config import Config
from db import get_db
from eduspace.security import login_required
from eduspace.services.files import query_browse_materials, get_file_detail_isolated
from eduspace.services.credits import process_download_transaction

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

    db = get_db()
    result = query_browse_materials(
        db=db,
        university_id=g.user['university_id'],
        search_query=search_query,
        subject_filter=subject_filter,
        semester_filter=semester_filter,
        type_filter=type_filter,
        sort_by=sort_by,
        page=page,
        per_page=9
    )

    return render_template(
        'browse.html',
        files=result['files'],
        total_items=result['total_items'],
        page=page,
        total_pages=result['total_pages'],
        search_query=search_query,
        subject_filter=subject_filter,
        semester_filter=semester_filter,
        type_filter=type_filter,
        sort_by=sort_by,
        subjects=result['subjects']
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
    file = get_file_detail_isolated(db, file_id, g.user['university_id'])
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
    # Strict university isolation check
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
    success, err_msg = process_download_transaction(
        db=db,
        user_id=g.user['id'],
        file_id=file_id,
        cost=cost,
        is_uploader=is_uploader,
        already_downloaded=already_downloaded
    )

    if not success:
        flash(err_msg, "danger")
        return redirect(url_for('library.file_detail', file_id=file_id))

    upload_folder = current_app.config.get('UPLOAD_FOLDER', Config.UPLOAD_FOLDER)
    return send_from_directory(
        upload_folder,
        file['stored_name'],
        as_attachment=True,
        download_name=file['original_name']
    )
