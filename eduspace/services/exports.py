"""
Research data export services with strict anonymization rules.

Generates CSV dataset exports for academic analysis. Specifically, user emails
and password hashes are stripped from the users dataset.
"""

EXPORT_TABLE_SCHEMAS = {
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


def get_export_dataset(db, table_name):
    """
    Query database for research dataset if table_name is whitelisted.

    Args:
        db: SQLite database connection.
        table_name (str): Identifier for the requested dataset.

    Returns:
        tuple or None: (headers: list of str, rows: list of Row, filename: str) or None.
    """
    if table_name not in EXPORT_TABLE_SCHEMAS:
        return None

    query, headers = EXPORT_TABLE_SCHEMAS[table_name]
    rows = db.execute(query).fetchall()
    filename = f"eduspace_{table_name}.csv"
    return headers, rows, filename
