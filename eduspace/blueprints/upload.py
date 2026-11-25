"""
Upload route for EduSpace.

Handles material submission, copyright affirmation, storage, and daily reward crediting.
Depends on Flask, db.get_db, and eduspace.services.
"""

import os
from flask import (
    Blueprint, render_template, request, redirect,
    url_for, flash, g, current_app
)
from markupsafe import Markup
from config import Config
from db import get_db
from eduspace.security import login_required
from eduspace.services.files import (
    validate_upload_input, save_uploaded_file, find_duplicate_in_scope
)
from eduspace.services.credits import process_upload_reward
from eduspace.services.telemetry import log_event_entry
from eduspace.services.visibility import can_view_file

bp = Blueprint('upload', __name__)


@bp.route('/upload', methods=['GET', 'POST'])
@login_required
def upload_file():
    """
    Upload study material:
    - Validates file type, size, extension, required metadata.
    - Requires copyright affirmation checkbox.
    - Assigns random stored filename.
    - Implements daily upload reward cap (MAX_REWARDED_UPLOADS_PER_DAY).
    - Always logs upload in the ledger (with reward or 0 credits).

    Returns:
        Response: Redirect to file_detail on success, or rendered upload.html on GET/error.
    """
    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        subject = request.form.get('subject', '').strip()
        semester = request.form.get('semester', type=int)
        file_type = request.form.get('type', '').strip()
        description = request.form.get('description', '').strip()
        confirm_copyright = request.form.get('confirm_copyright')
        uploaded_file = request.files.get('file')

        allowed_exts = current_app.config.get('ALLOWED_EXT', Config.ALLOWED_EXT)
        errors, original_filename, ext = validate_upload_input(
            title, subject, semester, file_type, confirm_copyright, uploaded_file, allowed_exts
        )
        if errors:
            for err in errors:
                flash(err, "danger")
            return render_template('upload.html')

        max_bytes = current_app.config.get('MAX_CONTENT_LENGTH', Config.MAX_CONTENT_LENGTH)
        upload_dir = current_app.config.get('UPLOAD_FOLDER', Config.UPLOAD_FOLDER)
        random_filename, file_size, content_hash, size_err = save_uploaded_file(
            uploaded_file, upload_dir, ext, max_bytes
        )
        if size_err:
            max_mb = current_app.config.get('MAX_FILE_MB', Config.MAX_FILE_MB)
            flash(f"File exceeds maximum allowed size of {max_mb}MB.", "danger")
            return render_template('upload.html')

        db = get_db()
        cursor = db.cursor()
        stored_path = os.path.join(upload_dir, random_filename)
        visibility = 'university'

        try:
            cursor.execute("BEGIN IMMEDIATE")
            dup = find_duplicate_in_scope(cursor, content_hash, visibility, g.user['university_id'])
            if dup:
                db.rollback()
                if os.path.exists(stored_path):
                    os.remove(stored_path)
                try:
                    log_event_entry(
                        db, g.session_id, g.user['id'],
                        'duplicate_blocked', request.path, f"existing_id={dup['id']}"
                    )
                except Exception:
                    pass
                if dup['status'] in ('removed', 'hidden'):
                    flash("This file was removed by moderators and cannot be uploaded again.", "danger")
                elif can_view_file(g.user, dup):
                    link = url_for('library.file_detail', file_id=dup['id'])
                    flash(
                        Markup(
                            f'This exact file is already in the library. '
                            f'<a href="{link}" class="fw-semibold text-decoration-underline">View existing file</a>'
                        ),
                        "warning"
                    )
                else:
                    flash("This exact file is already in the library.", "warning")
                return render_template('upload.html')

            cursor.execute(
                """
                INSERT INTO files (
                    uploader_id, university_id, title, subject, semester,
                    type, description, stored_name, original_name, size,
                    status, visibility, content_hash
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'active', ?, ?)
                """,
                (
                    g.user['id'], g.user['university_id'], title, subject,
                    semester, file_type, description, random_filename,
                    original_filename, file_size, visibility, content_hash
                )
            )
            file_id = cursor.lastrowid

            max_rewarded = current_app.config.get('MAX_REWARDED_UPLOADS_PER_DAY', Config.MAX_REWARDED_UPLOADS_PER_DAY)
            reward_amount = current_app.config.get('UPLOAD_REWARD', Config.UPLOAD_REWARD)
            _, msg = process_upload_reward(db, g.user['id'], file_id, max_rewarded, reward_amount)

            db.commit()
            flash(msg, "success")
            return redirect(url_for('library.file_detail', file_id=file_id))
        except Exception:
            db.rollback()
            if os.path.exists(stored_path):
                os.remove(stored_path)
            flash("Failed to save material due to a database error.", "danger")
            return render_template('upload.html')

    return render_template('upload.html')
