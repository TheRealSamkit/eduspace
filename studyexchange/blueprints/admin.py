"""
Administrator moderation, baseline evaluation entry, and data export routes.

Depends on Flask, db.get_db, config.Config, studyexchange.security, and studyexchange.services.
"""

import io
import csv
from flask import (
    Blueprint, render_template, request, redirect,
    url_for, flash, g, abort, make_response, current_app
)
from config import Config
from db import get_db
from studyexchange.security import admin_required
from studyexchange.services.files import takedown_file_admin
from studyexchange.services.exports import get_export_dataset

bp = Blueprint('admin', __name__)


@bp.route('/admin')
@admin_required
def admin_panel():
    """
    Administrator overview:
    - Reports moderation.
    - System statistics.
    - Direct export triggers.

    Returns:
        Response: Rendered admin.html with statistics and open moderation reports.
    """
    db = get_db()

    stats = {
        'users_count': db.execute("SELECT COUNT(*) FROM users").fetchone()[0],
        'files_count': db.execute("SELECT COUNT(*) FROM files WHERE status = 'active'").fetchone()[0],
        'downloads_count': db.execute("SELECT COUNT(*) FROM downloads").fetchone()[0],
        'reports_count': db.execute("SELECT COUNT(*) FROM reports WHERE status = 'open'").fetchone()[0],
        'tasks_count': db.execute("SELECT COUNT(*) FROM tasks").fetchone()[0],
        'sus_count': db.execute("SELECT COUNT(*) FROM sus_responses").fetchone()[0]
    }

    reports = db.execute(
        """
        SELECT r.*, f.title as file_title, f.status as file_status,
               reporter.username as reporter_username,
               uploader.username as uploader_username, uploader.id as uploader_id,
               un.name as university_name
        FROM reports r
        JOIN files f ON r.file_id = f.id
        JOIN users reporter ON r.user_id = reporter.id
        JOIN users uploader ON f.uploader_id = uploader.id
        JOIN universities un ON f.university_id = un.id
        WHERE r.status = 'open'
        ORDER BY r.created_at DESC
        """
    ).fetchall()

    return render_template('admin.html', stats=stats, reports=reports)


@bp.route('/admin/report/<int:report_id>/resolve', methods=['POST'])
@admin_required
def resolve_report(report_id):
    """
    Mark an open moderation report as resolved without removing material.

    Args:
        report_id (int): Primary key of report.

    Returns:
        Response: Redirect to admin panel.
    """
    db = get_db()
    db.execute("UPDATE reports SET status = 'resolved' WHERE id = ?", (report_id,))
    db.commit()
    flash("Report resolved.", "success")
    return redirect(url_for('admin.admin_panel'))


@bp.route('/admin/file/<int:file_id>/remove', methods=['POST'])
@admin_required
def remove_file_admin(file_id):
    """
    Takedown violating material:
    - Marks file status as 'removed'.
    - Reverses uploader credit reward in ledger.
    - Resolves associated moderation reports.

    Args:
        file_id (int): Primary key of file.

    Returns:
        Response: Redirect to admin panel.
    """
    db = get_db()
    default_reward = current_app.config.get('UPLOAD_REWARD', Config.UPLOAD_REWARD)
    success, title, reversed_credits = takedown_file_admin(db, file_id, default_reward)

    if not success:
        abort(404, description="File not found.")

    flash(f"Material '{title}' removed and {reversed_credits} credits reversed from uploader.", "success")
    return redirect(url_for('admin.admin_panel'))


@bp.route('/admin/baseline', methods=['GET', 'POST'])
@admin_required
def admin_baseline():
    """
    Facilitator entry form to record baseline study task measurements.

    Returns:
        Response: Rendered admin_baseline.html or redirect after submission.
    """
    if request.method == 'POST':
        task_name = request.form.get('task_name', '').strip()
        duration_sec = request.form.get('duration_sec', type=float)
        clicks = request.form.get('clicks', 0, type=int)
        errors = request.form.get('errors', 0, type=int)
        success = 1 if request.form.get('success') == '1' else 0

        if not task_name or duration_sec is None or duration_sec < 0:
            flash("Please provide a valid task name and duration in seconds.", "danger")
            return render_template('admin_baseline.html')

        db = get_db()
        db.execute(
            """
            INSERT INTO tasks (user_id, task_name, method, duration_sec, clicks, errors, success, started_at, ended_at)
            VALUES (?, ?, 'baseline', ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """,
            (g.user['id'], task_name, duration_sec, clicks, errors, success)
        )
        db.commit()
        flash("Baseline measurement recorded successfully.", "success")
        return redirect(url_for('admin.admin_baseline'))

    db = get_db()
    baselines = db.execute(
        "SELECT * FROM tasks WHERE method = 'baseline' ORDER BY id DESC LIMIT 30"
    ).fetchall()
    return render_template('admin_baseline.html', baselines=baselines)


@bp.route('/admin/export/<string:table_name>')
@admin_required
def admin_export_csv(table_name):
    """
    Export anonymised research datasets to CSV.

    Args:
        table_name (str): Table/view identifier.

    Returns:
        Response: CSV download attachment.
    """
    db = get_db()
    export_result = get_export_dataset(db, table_name)
    if not export_result:
        abort(404, description="Dataset not available for export.")

    headers, rows, filename = export_result

    si = io.StringIO()
    cw = csv.writer(si)
    cw.writerow(headers)
    for row in rows:
        cw.writerow([row[col] for col in headers])

    output = make_response(si.getvalue())
    output.headers["Content-Disposition"] = f"attachment; filename={filename}"
    output.headers["Content-type"] = "text/csv"
    return output
