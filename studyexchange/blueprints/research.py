"""
HCI research evaluation routes for StudyExchange.

Includes interactive test mode tasks, 10-item System Usability Scale (SUS) survey,
and qualitative usability feedback collection.
Depends on Flask, db.get_db, and studyexchange.security.login_required.
"""

from flask import (
    Blueprint, render_template, request, redirect,
    url_for, flash, g
)
from db import get_db
from studyexchange.security import login_required

bp = Blueprint('research', __name__)


@bp.route('/task', methods=['GET'])
@login_required
def task_page():
    """
    Render HCI research evaluation task runner interface.

    Returns:
        Response: Rendered task.html with task selection and historical runs.
    """
    db = get_db()
    my_tasks = db.execute(
        "SELECT * FROM tasks WHERE user_id = ? ORDER BY id DESC LIMIT 20",
        (g.user['id'],)
    ).fetchall()

    predefined_tasks = [
        {"id": 1, "name": "Find and download notes for Computer Networks, semester 4"},
        {"id": 2, "name": "Locate the highest rated study guide for Calculus"},
        {"id": 3, "name": "Upload study material for semester 3 and verify credit addition"},
        {"id": 4, "name": "Search for exam past papers and filter by semester"}
    ]

    return render_template('task.html', my_tasks=my_tasks, predefined_tasks=predefined_tasks)


@bp.route('/task/complete', methods=['POST'])
@login_required
def task_complete():
    """
    Record task evaluation metrics from prototype interactive session.

    Returns:
        Response: Redirect to task_page with flash status.
    """
    task_name = request.form.get('task_name', '').strip()
    started_at = request.form.get('started_at')
    ended_at = request.form.get('ended_at')
    duration_sec = request.form.get('duration_sec', type=float) or 0.0
    clicks = request.form.get('clicks', 0, type=int)
    errors = request.form.get('errors', 0, type=int)
    success = 1 if request.form.get('success') in ['1', 'true', 'True'] else 0

    if not task_name:
        flash("Invalid task submission.", "danger")
        return redirect(url_for('research.task_page'))

    db = get_db()
    db.execute(
        """
        INSERT INTO tasks (user_id, task_name, method, started_at, ended_at, duration_sec, clicks, errors, success)
        VALUES (?, ?, 'prototype', ?, ?, ?, ?, ?, ?)
        """,
        (g.user['id'], task_name, started_at, ended_at, duration_sec, clicks, errors, success)
    )
    db.commit()

    if success:
        flash(
            f"Task '{task_name}' recorded as SUCCESS! Duration: {duration_sec}s, Clicks: {clicks}, Errors: {errors}.",
            "success"
        )
    else:
        flash(f"Task '{task_name}' recorded as Abandoned. Telemetry saved for evaluation.", "warning")

    return redirect(url_for('research.task_page'))


@bp.route('/sus', methods=['GET', 'POST'])
@login_required
def sus_survey():
    """
    Standard 10-Item System Usability Scale (SUS) survey:
    - Radios 1-5 for each question.
    - Calculates SUS score:
      Odd items: (item - 1)
      Even items: (5 - item)
      Score = Sum * 2.5

    Returns:
        Response: Rendered sus.html or redirect upon submission.
    """
    sus_items = [
        "I think that I would like to use this system frequently.",
        "I found the system unnecessarily complex.",
        "I thought the system was easy to use.",
        "I think that I would need the support of a technical person to be able to use this system.",
        "I found the various functions in this system were well integrated.",
        "I thought there was too much inconsistency in this system.",
        "I would imagine that most people would learn to use this system very quickly.",
        "I found the system very cumbersome to use.",
        "I felt very confident using the system.",
        "I needed to learn a lot of things before I could get going with this system."
    ]

    if request.method == 'POST':
        answers = []
        for i in range(1, 11):
            val = request.form.get(f'q{i}', type=int)
            if val is None or not (1 <= val <= 5):
                flash(f"Please rate item {i} (value between 1 and 5).", "warning")
                return render_template('sus.html', items=sus_items), 400
            answers.append(val)

        # Compute SUS score: odd (index 0,2,4,6,8) -> x - 1; even (1,3,5,7,9) -> 5 - x
        odd_sum = sum(answers[i] - 1 for i in [0, 2, 4, 6, 8])
        even_sum = sum(5 - answers[i] for i in [1, 3, 5, 7, 9])
        sus_score = (odd_sum + even_sum) * 2.5

        db = get_db()
        db.execute(
            """
            INSERT INTO sus_responses (user_id, q1, q2, q3, q4, q5, q6, q7, q8, q9, q10, score)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (g.user['id'], *answers, sus_score)
        )
        db.commit()

        flash("Thank you! Your System Usability Scale evaluation has been recorded.", "success")
        return redirect(url_for('research.sus_survey', submitted=1))

    submitted = bool(request.args.get('submitted'))
    return render_template('sus.html', items=sus_items, submitted=submitted)


@bp.route('/feedback', methods=['GET', 'POST'])
@login_required
def feedback_page():
    """
    Collect qualitative user feedback and reported usability issues.

    Returns:
        Response: Rendered feedback.html or redirect to library.browse upon submission.
    """
    if request.method == 'POST':
        text = request.form.get('text', '').strip()
        usability_issue = request.form.get('usability_issue', '').strip()

        if not text:
            flash("Please enter your feedback comments.", "warning")
            return render_template('feedback.html')

        db = get_db()
        db.execute(
            """
            INSERT INTO feedback (user_id, text, usability_issue)
            VALUES (?, ?, ?)
            """,
            (g.user['id'], text, usability_issue if usability_issue else None)
        )
        db.commit()
        flash("Thank you for your valuable feedback! It will help improve StudyExchange.", "success")
        return redirect(url_for('library.browse'))

    return render_template('feedback.html')
