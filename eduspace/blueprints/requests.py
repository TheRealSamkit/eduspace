"""
Resource requests blueprint for EduSpace.

Provides request listing, creation, interest toggling, fulfilment upload,
submission acceptance with credit payout, and closing.
"""

import os
from flask import (
    Blueprint, render_template, request, redirect,
    url_for, flash, g, abort, jsonify, current_app
)
from config import Config
from db import get_db
from eduspace.security import login_required
from eduspace.services.credits import process_upload_reward
from eduspace.services.files import (
    validate_upload_input, save_uploaded_file, find_duplicate_in_scope
)
from eduspace.services.requests import (
    compute_request_reward, create_request, query_requests,
    get_request_detail, toggle_request_interest,
    submit_file_to_request, accept_submission
)
from eduspace.services.telemetry import log_event_entry
from eduspace.services.visibility import can_view_request

bp = Blueprint('requests', __name__)


def _reward_params():
    """Return (base, bonus, cap) from current_app.config."""
    cfg = current_app.config
    return (
        cfg.get('REQUEST_BASE_REWARD', Config.REQUEST_BASE_REWARD),
        cfg.get('REQUEST_INTEREST_BONUS', Config.REQUEST_INTEREST_BONUS),
        cfg.get('REQUEST_BONUS_CAP', Config.REQUEST_BONUS_CAP),
    )


@bp.route('/requests', methods=['GET', 'POST'])
@login_required
def list_requests():
    """List visible resource requests or create a new request."""
    db = get_db()
    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        subject = request.form.get('subject', '').strip()
        semester = request.form.get('semester', type=int)
        material_type = request.form.get('material_type', '').strip()
        description = request.form.get('description', '').strip()
        visibility = request.form.get('visibility', 'university').strip()

        if not title or not subject or not semester or not (1 <= semester <= 12) or not material_type:
            flash("Please complete all required request fields.", "danger")
            return redirect(url_for('requests.list_requests'))

        max_open = current_app.config.get('MAX_OPEN_REQUESTS_PER_USER', Config.MAX_OPEN_REQUESTS_PER_USER)
        req_id, err = create_request(db, g.user, title, subject, semester, material_type, description, visibility, max_open)
        if err:
            flash(err, "warning")
            return redirect(url_for('requests.list_requests'))

        try:
            log_event_entry(db, g.session_id, g.user['id'], 'request_create', request.path, f"req_id={req_id}")
        except Exception:
            pass
        flash("Resource request posted.", "success")
        return redirect(url_for('requests.request_detail', request_id=req_id))

    status_filter = request.args.get('status', '').strip()
    search_query = request.args.get('q', '').strip()
    subject_filter = request.args.get('subject', '').strip()
    rows, subjects = query_requests(db, g.user, status_filter, search_query, subject_filter)
    base, bonus, cap = _reward_params()

    items = []
    for r in rows:
        item = dict(r)
        item['current_reward'] = compute_request_reward(r['interest_count'], base, bonus, cap)
        items.append(item)

    return render_template(
        'requests.html',
        requests_list=items,
        subjects=subjects,
        status_filter=status_filter,
        search_query=search_query,
        subject_filter=subject_filter
    )


@bp.route('/requests/<int:request_id>')
@login_required
def request_detail(request_id):
    """Display resource request details, reward, and submissions."""
    db = get_db()
    req, subs = get_request_detail(db, request_id, g.user)
    if not req:
        abort(404, description="Request not found or access restricted.")

    base, bonus, cap = _reward_params()
    current_reward = compute_request_reward(req['interest_count'], base, bonus, cap)
    return render_template(
        'request_detail.html',
        req=req,
        submissions=subs,
        current_reward=current_reward
    )


@bp.route('/api/requests/<int:request_id>/interest', methods=['POST'])
@login_required
def api_toggle_interest(request_id):
    """Toggle current user's interest in a request and return updated reward."""
    db = get_db()
    base, bonus, cap = _reward_params()
    ok, interested, count, reward, err = toggle_request_interest(db, request_id, g.user, base, bonus, cap)
    if not ok:
        return jsonify({'error': err}), 400

    evt = 'request_interest_add' if interested else 'request_interest_remove'
    try:
        log_event_entry(db, g.session_id, g.user['id'], evt, request.path, f"req_id={request_id}")
    except Exception:
        pass
    return jsonify({'interested': interested, 'count': count, 'reward': reward}), 200


@bp.route('/requests/<int:request_id>/submit', methods=['POST'])
@login_required
def submit_to_request(request_id):
    """Upload a material fulfilling a request and link it as a pending submission."""
    db = get_db()
    req = db.execute("SELECT * FROM resource_requests WHERE id = ?", (request_id,)).fetchone()
    if not can_view_request(g.user, req):
        abort(404, description="Request not found.")
    if req['requester_id'] == g.user['id']:
        flash("You cannot submit a file to your own request.", "warning")
        return redirect(url_for('requests.request_detail', request_id=request_id))
    if req['status'] not in ('open', 'answered'):
        flash("This request is no longer accepting submissions.", "warning")
        return redirect(url_for('requests.request_detail', request_id=request_id))

    title = request.form.get('title', '').strip() or req['title']
    description = request.form.get('description', '').strip()
    confirm_copyright = request.form.get('confirm_copyright')
    uploaded_file = request.files.get('file')
    license_val = request.form.get('license', '').strip() or None
    valid_licenses = {code for code, _ in current_app.config.get('LICENSE_CHOICES', Config.LICENSE_CHOICES)}

    allowed_exts = current_app.config.get('ALLOWED_EXT', Config.ALLOWED_EXT)
    errors, orig_name, ext = validate_upload_input(
        title, req['subject'], req['semester'], req['material_type'], confirm_copyright, uploaded_file, allowed_exts
    )
    if req['visibility'] == 'public' and license_val not in valid_licenses:
        errors.append("Please select a valid licence for public submissions.")
    if errors:
        for err in errors:
            flash(err, "danger")
        return redirect(url_for('requests.request_detail', request_id=request_id))

    max_bytes = current_app.config.get('MAX_CONTENT_LENGTH', Config.MAX_CONTENT_LENGTH)
    upload_dir = current_app.config.get('UPLOAD_FOLDER', Config.UPLOAD_FOLDER)
    random_name, file_size, content_hash, size_err = save_uploaded_file(uploaded_file, upload_dir, ext, max_bytes)
    if size_err:
        flash(size_err, "danger")
        return redirect(url_for('requests.request_detail', request_id=request_id))

    cursor = db.cursor()
    stored_path = os.path.join(upload_dir, random_name)
    try:
        cursor.execute("BEGIN IMMEDIATE")
        dup = find_duplicate_in_scope(cursor, content_hash, req['visibility'], g.user['university_id'])
        if dup:
            db.rollback()
            if os.path.exists(stored_path):
                os.remove(stored_path)
            flash("This exact file is already in the library.", "warning")
            return redirect(url_for('requests.request_detail', request_id=request_id))

        cursor.execute(
            """
            INSERT INTO files (
                uploader_id, university_id, title, subject, semester, type,
                description, stored_name, original_name, size, status,
                visibility, content_hash, license
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'active', ?, ?, ?)
            """,
            (
                g.user['id'], g.user['university_id'], title, req['subject'],
                req['semester'], req['material_type'], description, random_name,
                orig_name, file_size, req['visibility'], content_hash,
                license_val if req['visibility'] == 'public' else None
            )
        )
        file_id = cursor.lastrowid
        max_rew = current_app.config.get('MAX_REWARDED_UPLOADS_PER_DAY', Config.MAX_REWARDED_UPLOADS_PER_DAY)
        rew_amt = current_app.config.get('UPLOAD_REWARD', Config.UPLOAD_REWARD)
        process_upload_reward(db, g.user['id'], file_id, max_rew, rew_amt)

        ok, sub_err = submit_file_to_request(cursor, request_id, file_id, g.user['id'])
        if not ok:
            db.rollback()
            if os.path.exists(stored_path):
                os.remove(stored_path)
            flash(sub_err, "warning")
            return redirect(url_for('requests.request_detail', request_id=request_id))

        db.commit()
    except Exception:
        db.rollback()
        if os.path.exists(stored_path):
            os.remove(stored_path)
        flash("Could not submit material due to a database error.", "danger")
        return redirect(url_for('requests.request_detail', request_id=request_id))

    try:
        log_event_entry(db, g.session_id, g.user['id'], 'request_submit', request.path, f"req_id={request_id},file_id={file_id}")
    except Exception:
        pass
    flash("Material submitted to request!", "success")
    return redirect(url_for('requests.request_detail', request_id=request_id))


@bp.route('/requests/<int:request_id>/accept/<int:submission_id>', methods=['POST'])
@login_required
def accept_request_submission(request_id, submission_id):
    """Accept a pending submission and pay the request reward to the submitter."""
    db = get_db()
    base, bonus, cap = _reward_params()
    max_per_day = current_app.config.get('MAX_REQUEST_REWARDS_PER_DAY', Config.MAX_REQUEST_REWARDS_PER_DAY)
    ok, paid, err = accept_submission(db, request_id, submission_id, g.user['id'], base, bonus, cap, max_per_day)
    if not ok:
        flash(err, "warning")
        return redirect(url_for('requests.request_detail', request_id=request_id))

    try:
        log_event_entry(db, g.session_id, g.user['id'], 'request_accept', request.path, f"req_id={request_id},paid={paid}")
    except Exception:
        pass
    msg = f"Submission accepted! {paid} credits awarded to the contributor." if paid > 0 \
        else "Submission accepted! (Contributor reached daily request reward cap.)"
    flash(msg, "success")
    return redirect(url_for('requests.request_detail', request_id=request_id))


@bp.route('/requests/<int:request_id>/close', methods=['POST'])
@login_required
def close_request_route(request_id):
    """Close an open or answered request (requester only)."""
    db = get_db()
    req = db.execute("SELECT * FROM resource_requests WHERE id = ?", (request_id,)).fetchone()
    if not req or req['requester_id'] != g.user['id']:
        abort(403, description="Only the requester can close this request.")
    if req['status'] in ('open', 'answered'):
        db.execute("UPDATE resource_requests SET status = 'closed' WHERE id = ?", (request_id,))
        db.commit()
        flash("Request closed.", "info")
    return redirect(url_for('requests.request_detail', request_id=request_id))
