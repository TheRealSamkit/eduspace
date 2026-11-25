"""
Core library routes for EduSpace.

Includes repository browsing, search/filter, material detail views, ratings,
reporting, and credit-deducted file downloads with institutional isolation.
Depends on Flask, db.get_db, and eduspace.services.
"""

import os
from flask import (
    Blueprint, render_template, request, redirect,
    url_for, flash, g, abort, send_from_directory, send_file,
    jsonify, current_app
)
from config import Config
from db import get_db
from eduspace.security import login_required
from eduspace.services.files import (
    query_browse_materials, get_file_detail_isolated,
    get_bookmarked_file_ids, query_saved_materials
)
from eduspace.services.credits import process_download_transaction
from eduspace.services.visibility import can_view_file, is_public_member
from eduspace.services.preview import (
    is_file_unlocked, get_preview_kind,
    get_or_create_locked_pdf, get_or_create_locked_image
)
from eduspace.services.telemetry import log_event_entry

bp = Blueprint('library', __name__)


@bp.route('/browse')
@login_required
def browse():
    """
    Browse and search study material with university isolation.

    Returns:
        Response: Rendered browse.html with isolated files and filter options.
    """
    if is_public_member(g.user):
        return redirect(url_for('public.public_library'))

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
        scope='university'
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
        subjects=result['subjects'],
        bookmarked_ids=get_bookmarked_file_ids(db, g.user['id'])
    )


@bp.route('/saved')
@login_required
def saved():
    """
    Display materials bookmarked by the current user that they are still permitted to view.

    Returns:
        Response: Rendered saved.html.
    """
    search_query = request.args.get('q', '').strip()
    sort_by = request.args.get('sort', 'newest')
    page = max(1, request.args.get('page', 1, type=int))

    db = get_db()
    result = query_saved_materials(db, g.user, search_query, sort_by, page, per_page=9)
    return render_template(
        'saved.html',
        files=result['files'],
        total_items=result['total_items'],
        page=page,
        total_pages=result['total_pages'],
        search_query=search_query,
        sort_by=sort_by,
        bookmarked_ids=get_bookmarked_file_ids(db, g.user['id'])
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
    file = get_file_detail_isolated(db, file_id, g.user)
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

    is_bookmarked = db.execute(
        "SELECT 1 FROM bookmarks WHERE user_id = ? AND file_id = ?",
        (g.user['id'], file_id)
    ).fetchone() is not None

    return render_template(
        'file_detail.html',
        file=file,
        is_uploader=is_uploader,
        already_downloaded=already_downloaded,
        is_bookmarked=is_bookmarked,
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
    file = db.execute("SELECT * FROM files WHERE id = ?", (file_id,)).fetchone()

    if not can_view_file(g.user, file) or file['status'] != 'active':
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
    file = db.execute("SELECT * FROM files WHERE id = ?", (file_id,)).fetchone()

    if not can_view_file(g.user, file) or file['status'] != 'active':
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
    if file['visibility'] == 'public':
        threshold = current_app.config.get('REPORTS_TO_AUTOHIDE', Config.REPORTS_TO_AUTOHIDE)
        distinct_reporters = db.execute(
            "SELECT COUNT(DISTINCT user_id) FROM reports WHERE file_id = ? AND status = 'open'",
            (file_id,)
        ).fetchone()[0]
        if distinct_reporters >= threshold:
            db.execute("UPDATE files SET status = 'hidden' WHERE id = ? AND status = 'active'", (file_id,))
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
    file = db.execute("SELECT * FROM files WHERE id = ?", (file_id,)).fetchone()

    if not can_view_file(g.user, file) or file['status'] != 'active':
        abort(404, description="Material not found or access restricted to students of its institution.")

    is_uploader = (file['uploader_id'] == g.user['id'])
    is_request_requester = db.execute(
        """
        SELECT 1 FROM request_submissions rs
        JOIN resource_requests rr ON rs.request_id = rr.id
        WHERE rs.file_id = ? AND rr.requester_id = ?
        """,
        (file_id, g.user['id'])
    ).fetchone() is not None
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
        is_uploader=(is_uploader or is_request_requester),
        already_downloaded=already_downloaded
    )

    if not success:
        flash(err_msg, "danger")
        return redirect(url_for('library.file_detail', file_id=file_id))

    if file['visibility'] == 'public':
        try:
            log_event_entry(db, g.session_id, g.user['id'], 'public_download', request.path, f"file_id={file_id}")
        except Exception:
            pass

    upload_folder = current_app.config.get('UPLOAD_FOLDER', Config.UPLOAD_FOLDER)
    return send_from_directory(
        upload_folder,
        file['stored_name'],
        as_attachment=True,
        download_name=file['original_name']
    )


@bp.route('/preview/<int:file_id>')
@login_required
def preview_file(file_id):
    """
    Serve an inline preview of a study material (server-enforced lock for unpaid users).

    Returns:
        Response: Inline PDF/image stream with no-store and nosniff headers, or JSON error.
    """
    db = get_db()
    file = db.execute("SELECT * FROM files WHERE id = ?", (file_id,)).fetchone()
    if not can_view_file(g.user, file):
        abort(404, description="Material not found or access restricted.")

    kind = get_preview_kind(file['original_name'])
    if kind == 'unsupported':
        return jsonify({'error': 'Preview not available for this file type.'}), 415

    upload_folder = current_app.config.get('UPLOAD_FOLDER', Config.UPLOAD_FOLDER)
    source_path = os.path.join(upload_folder, file['stored_name'])
    if not os.path.isfile(source_path):
        return jsonify({'error': 'File not found on server.'}), 404

    unlocked = is_file_unlocked(db, g.user, file)
    content_hash = file['content_hash'] or file['stored_name']
    cache_dir = os.path.join(os.path.dirname(os.path.abspath(upload_folder)), 'previews')
    ext = file['original_name'].rsplit('.', 1)[-1].lower()

    if unlocked:
        target_path = source_path
    else:
        try:
            if kind == 'pdf':
                max_pages = current_app.config.get('PREVIEW_LOCKED_PAGES', Config.PREVIEW_LOCKED_PAGES)
                target_path = get_or_create_locked_pdf(source_path, content_hash, cache_dir, max_pages)
            else:
                max_px = current_app.config.get('PREVIEW_IMAGE_MAX_PX', Config.PREVIEW_IMAGE_MAX_PX)
                target_path = get_or_create_locked_image(source_path, content_hash, ext, cache_dir, max_px)
        except ValueError as exc:
            return jsonify({'error': str(exc)}), 422

    try:
        log_event_entry(
            db, g.session_id, g.user['id'],
            'preview_open', request.path, f"file_id={file_id},locked={not unlocked}"
        )
    except Exception:
        pass

    mimetype = 'application/pdf' if kind == 'pdf' else ('image/png' if ext == 'png' else 'image/jpeg')
    resp = send_file(target_path, mimetype=mimetype, as_attachment=False)
    resp.headers['Cache-Control'] = 'private, no-store'
    resp.headers['X-Content-Type-Options'] = 'nosniff'
    return resp
