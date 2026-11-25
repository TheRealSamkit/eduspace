"""
Resource requests business logic for EduSpace.

Handles request creation, interest toggles, submission linking,
atomic reward payout on acceptance, and visibility checks.
"""

from eduspace.services.credits import record_ledger_entry
from eduspace.services.visibility import (
    can_view_request,
    is_public_member,
    request_visibility_where,
)


def compute_request_reward(interested_count, base_reward, bonus_per_interest, bonus_cap):
    """Return total minted reward for fulfilling a request."""
    bonus = min(bonus_cap, max(0, int(interested_count)) * bonus_per_interest)
    return base_reward + bonus


def create_request(db, user, title, subject, semester, material_type, description, visibility, max_open):
    """
    Create a new resource request if the user is below MAX_OPEN_REQUESTS_PER_USER.

    Returns:
        tuple: (request_id: int or None, error: str or None)
    """
    vis = 'public' if is_public_member(user) else ('public' if visibility == 'public' else 'university')
    open_count = db.execute(
        "SELECT COUNT(*) FROM resource_requests WHERE requester_id = ? AND status IN ('open', 'answered')",
        (user['id'],)
    ).fetchone()[0]
    if open_count >= max_open:
        return None, f"You can have at most {max_open} open requests at a time."

    cursor = db.execute(
        """
        INSERT INTO resource_requests (
            requester_id, university_id, visibility, title, subject,
            semester, material_type, description, status
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'open')
        """,
        (user['id'], user['university_id'], vis, title, subject, semester, material_type, description)
    )
    db.commit()
    return cursor.lastrowid, None


def query_requests(db, user, status_filter='', search_query='', subject_filter=''):
    """List resource requests visible to user with interest counts."""
    vis_clause, vis_params = request_visibility_where(user, alias='rr')
    sql = f"""
        SELECT rr.*, u.username as requester_username,
               COUNT(DISTINCT ri.user_id) as interest_count,
               MAX(CASE WHEN ri.user_id = ? THEN 1 ELSE 0 END) as user_interested,
               COUNT(DISTINCT rs.id) as submission_count
        FROM resource_requests rr
        JOIN users u ON rr.requester_id = u.id
        LEFT JOIN request_interest ri ON rr.id = ri.request_id
        LEFT JOIN request_submissions rs ON rr.id = rs.request_id
        WHERE {vis_clause}
    """
    params = [user['id']] + list(vis_params)

    if status_filter == 'mine':
        sql += " AND rr.requester_id = ?"
        params.append(user['id'])
    elif status_filter in ('open', 'answered', 'fulfilled', 'closed'):
        sql += " AND rr.status = ?"
        params.append(status_filter)

    if search_query:
        sql += " AND (rr.title LIKE ? OR rr.subject LIKE ? OR rr.description LIKE ?)"
        term = f"%{search_query}%"
        params.extend([term, term, term])

    if subject_filter:
        sql += " AND rr.subject = ?"
        params.append(subject_filter)

    sql += " GROUP BY rr.id ORDER BY rr.created_at DESC, rr.id DESC"
    rows = db.execute(sql, params).fetchall()

    subjects_raw = db.execute(
        f"SELECT DISTINCT rr.subject FROM resource_requests rr WHERE {vis_clause} ORDER BY rr.subject",
        vis_params
    ).fetchall()
    return rows, [s['subject'] for s in subjects_raw]


def get_request_detail(db, request_id, user):
    """Return (request_row, submissions) if visible to user, else (None, [])."""
    req = db.execute(
        """
        SELECT rr.*, u.username as requester_username,
               COUNT(DISTINCT ri.user_id) as interest_count,
               MAX(CASE WHEN ri.user_id = ? THEN 1 ELSE 0 END) as user_interested
        FROM resource_requests rr
        JOIN users u ON rr.requester_id = u.id
        LEFT JOIN request_interest ri ON rr.id = ri.request_id
        WHERE rr.id = ?
        GROUP BY rr.id
        """,
        (user['id'], request_id)
    ).fetchone()
    if not can_view_request(user, req):
        return None, []

    subs = db.execute(
        """
        SELECT rs.*, f.title as file_title, f.original_name, f.size, f.status as file_status,
               u.username as submitter_username
        FROM request_submissions rs
        JOIN files f ON rs.file_id = f.id
        JOIN users u ON rs.submitter_id = u.id
        WHERE rs.request_id = ?
        ORDER BY rs.created_at ASC, rs.id ASC
        """,
        (request_id,)
    ).fetchall()
    return req, subs


def toggle_request_interest(db, request_id, user, base_reward, bonus_per_interest, bonus_cap):
    """
    Toggle interest in a visible open/answered request (forbidden for requester).

    Returns:
        tuple: (ok: bool, interested: bool, count: int, reward: int, error: str or None)
    """
    req = db.execute("SELECT * FROM resource_requests WHERE id = ?", (request_id,)).fetchone()
    if not can_view_request(user, req):
        return False, False, 0, 0, "Request not found."
    if req['requester_id'] == user['id']:
        return False, False, 0, 0, "You cannot mark interest in your own request."
    if req['status'] not in ('open', 'answered'):
        return False, False, 0, 0, "This request is no longer open."

    existing = db.execute(
        "SELECT 1 FROM request_interest WHERE request_id = ? AND user_id = ?",
        (request_id, user['id'])
    ).fetchone()
    if existing:
        db.execute("DELETE FROM request_interest WHERE request_id = ? AND user_id = ?", (request_id, user['id']))
        interested = False
    else:
        db.execute("INSERT INTO request_interest (request_id, user_id) VALUES (?, ?)", (request_id, user['id']))
        interested = True
    db.commit()

    count = db.execute("SELECT COUNT(*) FROM request_interest WHERE request_id = ?", (request_id,)).fetchone()[0]
    reward = compute_request_reward(count, base_reward, bonus_per_interest, bonus_cap)
    return True, interested, count, reward, None


def submit_file_to_request(cursor, request_id, file_id, submitter_id):
    """Link an uploaded file as a pending submission and mark request answered."""
    existing = cursor.execute(
        "SELECT 1 FROM request_submissions WHERE request_id = ? AND file_id = ?",
        (request_id, file_id)
    ).fetchone()
    if existing:
        return False, "This file has already been submitted to this request."

    cursor.execute(
        "INSERT INTO request_submissions (request_id, file_id, submitter_id, status) VALUES (?, ?, ?, 'pending')",
        (request_id, file_id, submitter_id)
    )
    cursor.execute(
        "UPDATE resource_requests SET status = 'answered' WHERE id = ? AND status = 'open'",
        (request_id,)
    )
    return True, None


def accept_submission(db, request_id, submission_id, requester_id, base_reward, bonus_per_interest, bonus_cap, max_rewards_per_day):
    """
    Atomically accept one pending submission, mark request fulfilled, and pay reward.

    Returns:
        tuple: (ok: bool, paid: int, error: str or None)
    """
    cursor = db.cursor()
    try:
        cursor.execute("BEGIN IMMEDIATE")
        req = cursor.execute("SELECT * FROM resource_requests WHERE id = ?", (request_id,)).fetchone()
        if not req or req['requester_id'] != requester_id:
            db.rollback()
            return False, 0, "Only the requester can accept a submission."
        if req['status'] not in ('open', 'answered') or req['accepted_submission_id'] is not None:
            db.rollback()
            return False, 0, "This request has already been fulfilled or closed."

        sub = cursor.execute(
            "SELECT * FROM request_submissions WHERE id = ? AND request_id = ?",
            (submission_id, request_id)
        ).fetchone()
        if not sub or sub['status'] != 'pending':
            db.rollback()
            return False, 0, "Submission not found or already processed."

        interest_count = cursor.execute(
            "SELECT COUNT(*) FROM request_interest WHERE request_id = ?", (request_id,)
        ).fetchone()[0]
        reward = compute_request_reward(interest_count, base_reward, bonus_per_interest, bonus_cap)

        rewards_today = cursor.execute(
            """
            SELECT COUNT(*) FROM ledger
            WHERE user_id = ? AND reason = 'request_reward' AND amount > 0
              AND date(created_at) = date('now')
            """,
            (sub['submitter_id'],)
        ).fetchone()[0]
        paid = 0 if rewards_today >= max_rewards_per_day else reward

        cursor.execute("UPDATE request_submissions SET status = 'accepted' WHERE id = ?", (submission_id,))
        cursor.execute(
            "UPDATE request_submissions SET status = 'rejected' WHERE request_id = ? AND id != ? AND status = 'pending'",
            (request_id, submission_id)
        )
        cursor.execute(
            """
            UPDATE resource_requests
            SET status = 'fulfilled', accepted_submission_id = ?, reward_paid = ?, fulfilled_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (submission_id, paid, request_id)
        )
        if paid > 0:
            cursor.execute("UPDATE users SET credits = credits + ? WHERE id = ?", (paid, sub['submitter_id']))
            record_ledger_entry(cursor, sub['submitter_id'], paid, 'request_reward', sub['file_id'])

        db.commit()
        return True, paid, None
    except Exception:
        db.rollback()
        return False, 0, "Could not accept submission due to a database error."
