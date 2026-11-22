"""
HCI research evaluation routes for StudyExchange.

Includes interactive test mode tasks, 10-item System Usability Scale (SUS) survey,
and qualitative usability feedback collection.
Depends on Flask, db.get_db, studyexchange.security, and studyexchange.services.
"""

from flask import (
    Blueprint, render_template, request, redirect,
    url_for, flash, g
)
from db import get_db
from studyexchange.security import login_required
from studyexchange.services.sus import (
    SUS_ITEMS, validate_and_extract_sus_answers,
    calculate_sus_score, record_sus_evaluation
)
from studyexchange.services.telemetry import record_task_metric, record_user_feedback

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
    record_task_metric(
        db=db,
        user_id=g.user['id'],
        task_name=task_name,
        method='prototype',
        started_at=started_at,
        ended_at=ended_at,
        duration_sec=duration_sec,
        clicks=clicks,
        errors=errors,
        success=success
    )

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
    if request.method == 'POST':
        answers, invalid_idx = validate_and_extract_sus_answers(request.form)
        if answers is None:
            flash(f"Please rate item {invalid_idx} (value between 1 and 5).", "warning")
            return render_template('sus.html', items=SUS_ITEMS), 400

        sus_score = calculate_sus_score(answers)
        db = get_db()
        record_sus_evaluation(db, g.user['id'], answers, sus_score)

        flash("Thank you! Your System Usability Scale evaluation has been recorded.", "success")
        return redirect(url_for('research.sus_survey', submitted=1))

    submitted = bool(request.args.get('submitted'))
    return render_template('sus.html', items=SUS_ITEMS, submitted=submitted)


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
        record_user_feedback(db, g.user['id'], text, usability_issue)
        flash("Thank you for your valuable feedback! It will help improve StudyExchange.", "success")
        return redirect(url_for('library.browse'))

    return render_template('feedback.html')
