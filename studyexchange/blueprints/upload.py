"""
Upload route for StudyExchange.

Handles material submission, copyright affirmation, storage, and daily reward crediting.
Depends on Flask, werkzeug.utils, db.get_db, and studyexchange.security.login_required.
"""

import os
import uuid
from flask import (
    Blueprint, render_template, request, redirect,
    url_for, flash, g, current_app
)
from werkzeug.utils import secure_filename
from config import Config
from db import get_db
from studyexchange.security import login_required

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

        errors = []
        if not title:
            errors.append("Document title is required.")
        if not subject:
            errors.append("Subject is required.")
        if not semester or not (1 <= semester <= 12):
            errors.append("Please specify a valid semester (1 to 12).")
        if not file_type:
            errors.append("Material type is required.")
        if not confirm_copyright:
            errors.append("You must confirm you own this material or have the right to share it.")
        if not uploaded_file or not uploaded_file.filename:
            errors.append("Please select a file to upload.")

        original_filename = secure_filename(uploaded_file.filename) if uploaded_file else ""
        ext = original_filename.rsplit('.', 1)[-1].lower() if '.' in original_filename else ""
        allowed_exts = current_app.config.get('ALLOWED_EXT', Config.ALLOWED_EXT)
        if ext not in allowed_exts:
            errors.append(f"Invalid file extension '.{ext}'. Allowed formats: {', '.join(allowed_exts)}.")

        if errors:
            for err in errors:
                flash(err, "danger")
            return render_template('upload.html')

        uploaded_file.seek(0, os.SEEK_END)
        file_size = uploaded_file.tell()
        uploaded_file.seek(0)
        max_bytes = current_app.config.get('MAX_CONTENT_LENGTH', Config.MAX_CONTENT_LENGTH)
        if file_size > max_bytes:
            flash(
                f"File exceeds maximum allowed size of {current_app.config.get('MAX_FILE_MB', Config.MAX_FILE_MB)}MB.",
                "danger"
            )
            return render_template('upload.html')

        random_filename = f"{uuid.uuid4().hex}.{ext}"
        upload_dir = current_app.config.get('UPLOAD_FOLDER', Config.UPLOAD_FOLDER)
        os.makedirs(upload_dir, exist_ok=True)
        stored_path = os.path.join(upload_dir, random_filename)
        uploaded_file.save(stored_path)

        db = get_db()
        cursor = db.cursor()

        try:
            cursor.execute(
                """
                INSERT INTO files (
                    uploader_id, university_id, title, subject, semester,
                    type, description, stored_name, original_name, size, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'active')
                """,
                (
                    g.user['id'], g.user['university_id'], title, subject,
                    semester, file_type, description, random_filename,
                    original_filename, file_size
                )
            )
            file_id = cursor.lastrowid

            max_rewarded = current_app.config.get('MAX_REWARDED_UPLOADS_PER_DAY', Config.MAX_REWARDED_UPLOADS_PER_DAY)
            reward_amount = current_app.config.get('UPLOAD_REWARD', Config.UPLOAD_REWARD)

            rewarded_today = cursor.execute(
                """
                SELECT COUNT(*) FROM ledger
                WHERE user_id = ? AND reason = 'upload' AND amount > 0
                AND date(created_at) = date('now')
                """,
                (g.user['id'],)
            ).fetchone()[0]

            if rewarded_today < max_rewarded:
                earned = reward_amount
                cursor.execute("UPDATE users SET credits = credits + ? WHERE id = ?", (earned, g.user['id']))
                msg = f"Material uploaded successfully! You earned {earned} credits."
            else:
                earned = 0
                msg = f"Material uploaded successfully! (Daily reward limit of {max_rewarded} reached; 0 credits earned)."

            cursor.execute(
                """
                INSERT INTO ledger (user_id, amount, reason, file_id)
                VALUES (?, ?, 'upload', ?)
                """,
                (g.user['id'], earned, file_id)
            )

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
