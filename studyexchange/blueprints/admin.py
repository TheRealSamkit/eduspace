"""
Administrator moderation, baseline evaluation entry, and data export routes.

Depends on Flask, db.get_db, config.Config, and studyexchange.security.admin_required.
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
    cursor = db.cursor()
    try:
        cursor.execute("BEGIN IMMEDIATE")
        file = cursor.execute("SELECT * FROM files WHERE id = ?", (file_id,)).fetchone()
        if not file:
            abort(404, description="File not found.")

        cursor.execute("UPDATE files SET status = 'removed' WHERE id = ?", (file_id,))

        upload_ledger = cursor.execute(
            "SELECT amount FROM ledger WHERE file_id = ? AND user_id = ? AND reason = 'upload' AND amount > 0",
            (file_id, file['uploader_id'])
        ).fetchone()

        reversal_amount = upload_ledger['amount'] if upload_ledger else current_app.config.get('UPLOAD_REWARD', Config.UPLOAD_REWARD)

        cursor.execute(
            "UPDATE users SET credits = MAX(0, credits - ?) WHERE id = ?",
            (reversal_amount, file['uploader_id'])
        )

        cursor.execute(
            """
            INSERT INTO ledger (user_id, amount, reason, file_id)
            VALUES (?, ?, 'reversal', ?)
            """,
            (file['uploader_id'], -reversal_amount, file_id)
        )

        cursor.execute("UPDATE reports SET status = 'resolved' WHERE file_id = ?", (file_id,))

        db.commit()
        flash(f"Material '{file['title']}' removed and {reversal_amount} credits reversed from uploader.", "success")
    except Exception:
        db.rollback()
        flash("Failed to remove material due to a database error.", "danger")

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
    allowed_tables = {
        'events': (
            'SELECT id, session_id, user_id, event_type, page, detail, ts FROM events',
            ['id', 'session_id', 'user_id', 'event_type', 'page', 'detail', 'ts']
        ),
        'tasks': (
            'SELECT id, user_id, task_name, method, started_at, ended_at, duration_sec, clicks, errors, success FROM tasks',
            ['id', 'user_id', 'task_name', 'method', 'started_at', 'ended_at', 'duration_sec', 'clicks', 'errors', 'success']
        ),
        'sus_responses': (
            'SELECT id, user_id, q1, q2, q3, q4, q5, q6, q7, q8, q9, q10, score, created_at FROM sus_responses',
            ['id', 'user_id', 'q1', 'q2', 'q3', 'q4', 'q5', 'q6', 'q7', 'q8', 'q9', 'q10', 'score', 'created_at']
        ),
        'feedback': (
            'SELECT id, user_id, text, usability_issue, created_at FROM feedback',
            ['id', 'user_id', 'text', 'usability_issue', 'created_at']
        ),
        'users_anonymized': (
            """
            SELECT u.id, u.university_id, un.name as university_name, u.credits, u.is_admin, u.created_at
            FROM users u
            JOIN universities un ON u.university_id = un.id
            """,
            ['id', 'university_id', 'university_name', 'credits', 'is_admin', 'created_at']
        ),
        'files': (
            """
            SELECT f.id, f.university_id, f.subject, f.semester, f.type, f.size, f.status, f.created_at
            FROM files f
            """,
            ['id', 'university_id', 'subject', 'semester', 'type', 'size', 'status', 'created_at']
        ),
        'downloads': (
            'SELECT id, user_id, file_id, created_at FROM downloads',
            ['id', 'user_id', 'file_id', 'created_at']
        ),
        'ledger': (
            'SELECT id, user_id, amount, reason, file_id, created_at FROM ledger',
            ['id', 'user_id', 'amount', 'reason', 'file_id', 'created_at']
        )
    }

    if table_name not in allowed_tables:
        abort(404, description="Dataset not available for export.")

    query, headers = allowed_tables[table_name]
    db = get_db()
    rows = db.execute(query).fetchall()

    si = io.StringIO()
    cw = csv.writer(si)
    cw.writerow(headers)
    for row in rows:
        cw.writerow([row[col] for col in headers])

    output = make_response(si.getvalue())
    output.headers["Content-Disposition"] = f"attachment; filename=studyexchange_{table_name}.csv"
    output.headers["Content-type"] = "text/csv"
    return output
