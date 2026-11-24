"""
Usage measurement and telemetry services for EduSpace.

Encapsulates event stream logging, HCI task performance metrics,
and user feedback persistence.
"""


def log_event_entry(db, session_id, user_id, event_type, page, detail):
    """
    Persist client or server telemetry event for analytics.

    Args:
        db: SQLite database connection.
        session_id (str): Anonymous/authenticated session tracking identifier.
        user_id (int or None): Authenticated user ID if present.
        event_type (str): Category of event ('page_view', 'user_click', 'validation_error', 'shortcut').
        page (str): Originating path/URL.
        detail (str): Event context or payload.

    Side effects:
        Inserts row into events table.
    """
    db.execute(
        """
        INSERT INTO events (session_id, user_id, event_type, page, detail)
        VALUES (?, ?, ?, ?, ?)
        """,
        (session_id, user_id, event_type, page, str(detail)[:500])
    )
    db.commit()


def record_task_metric(db, user_id, task_name, method, started_at, ended_at, duration_sec, clicks, errors, success):
    """
    Record task usability evaluation metrics (prototype or baseline).

    Args:
        db: SQLite database connection.
        user_id (int): Facilitator or participant user ID.
        task_name (str): Description of the evaluation task.
        method (str): Evaluation method ('prototype' or 'baseline').
        started_at (str): ISO timestamp of start.
        ended_at (str): ISO timestamp of completion.
        duration_sec (float): Total task time in seconds.
        clicks (int): Number of clicks registered.
        errors (int): Number of validation or operational errors.
        success (int): 1 if completed, 0 if abandoned/failed.

    Side effects:
        Inserts row into tasks table.
    """
    db.execute(
        """
        INSERT INTO tasks (user_id, task_name, method, started_at, ended_at, duration_sec, clicks, errors, success)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (user_id, task_name, method, started_at, ended_at, duration_sec, clicks, errors, success)
    )
    db.commit()


def record_user_feedback(db, user_id, text, usability_issue):
    """
    Save qualitative student feedback and usability issues.

    Args:
        db: SQLite database connection.
        user_id (int): User ID submitting feedback.
        text (str): Feedback comment body.
        usability_issue (str or None): Specific usability issue description.

    Side effects:
        Inserts row into feedback table.
    """
    db.execute(
        """
        INSERT INTO feedback (user_id, text, usability_issue)
        VALUES (?, ?, ?)
        """,
        (user_id, text, usability_issue if usability_issue else None)
    )
    db.commit()
