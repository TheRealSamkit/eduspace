"""
Access and viewability helpers for EduSpace study materials.

Determines whether a user has unlocked a file (uploader, admin, or prior
downloader) and classifies supported inline-viewable file types.
"""


def is_file_unlocked(db, user, file):
    """
    Return True if the user is entitled to view the full unredacted file.

    Unlocked for: the uploader, administrators, or users who already downloaded it.
    """
    if not user or not file:
        return False
    if user['id'] == file['uploader_id'] or bool(user['is_admin']):
        return True
    row = db.execute(
        "SELECT 1 FROM downloads WHERE user_id = ? AND file_id = ?",
        (user['id'], file['id'])
    ).fetchone()
    return row is not None


def get_unlocked_file_ids(db, user, file_ids):
    """
    Return the subset of file_ids that the user has unlocked.

    Args:
        db: SQLite database connection.
        user: Current user row/dict or None.
        file_ids (iterable[int]): Candidate file IDs.

    Returns:
        set[int]: Unlocked file IDs.
    """
    ids = list(file_ids or [])
    if not user or not ids:
        return set()
    if bool(user['is_admin']):
        return set(ids)

    placeholders = ','.join('?' for _ in ids)
    uploaded_rows = db.execute(
        f"SELECT id FROM files WHERE uploader_id = ? AND id IN ({placeholders})",
        [user['id']] + ids
    ).fetchall()
    downloaded_rows = db.execute(
        f"SELECT file_id FROM downloads WHERE user_id = ? AND file_id IN ({placeholders})",
        [user['id']] + ids
    ).fetchall()
    return {row['id'] for row in uploaded_rows} | {row['file_id'] for row in downloaded_rows}


def get_view_kind(filename):
    """Classify filename into 'pdf', 'image', or 'unsupported'."""
    ext = filename.rsplit('.', 1)[-1].lower() if '.' in (filename or '') else ''
    if ext == 'pdf':
        return 'pdf'
    if ext in ('png', 'jpg', 'jpeg'):
        return 'image'
    return 'unsupported'
