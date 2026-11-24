"""
File management, repository querying, and institutional isolation services.

Encapsulates file metadata validation, disk persistence, multi-parameter
search queries, and moderation takedowns with strict university isolation.
Depends on os, uuid, and werkzeug.utils.secure_filename.
"""

import os
import uuid
from werkzeug.utils import secure_filename
from eduspace.services.credits import reverse_upload_credits


def validate_upload_input(title, subject, semester, file_type, confirm_copyright, uploaded_file, allowed_exts):
    """
    Validate upload form fields, copyright confirmation, and file presence.

    Args:
        title (str): Document title.
        subject (str): Academic subject.
        semester (int or None): Semester number.
        file_type (str): Material classification (e.g. 'Lecture Notes').
        confirm_copyright (str or None): Copyright confirmation flag.
        uploaded_file: Werkzeug FileStorage object.
        allowed_exts (set): Allowed lowercased file extensions.

    Returns:
        tuple: (errors: list of str, original_filename: str, ext: str)
    """
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
    if ext not in allowed_exts:
        errors.append(f"Invalid file extension '.{ext}'. Allowed formats: {', '.join(sorted(allowed_exts))}.")

    return errors, original_filename, ext


def save_uploaded_file(uploaded_file, upload_dir, ext, max_bytes):
    """
    Verify file size limit and save file with a random UUID filename.

    Args:
        uploaded_file: Werkzeug FileStorage object.
        upload_dir (str): Destination directory on disk.
        ext (str): File extension.
        max_bytes (int): Maximum permitted file size in bytes.

    Returns:
        tuple: (random_filename: str or None, file_size: int, error: str or None)
    Side effects:
        Writes file to disk under upload_dir.
    """
    uploaded_file.seek(0, os.SEEK_END)
    file_size = uploaded_file.tell()
    uploaded_file.seek(0)

    if file_size > max_bytes:
        return None, file_size, "File exceeds maximum allowed size."

    random_filename = f"{uuid.uuid4().hex}.{ext}"
    os.makedirs(upload_dir, exist_ok=True)
    stored_path = os.path.join(upload_dir, random_filename)
    uploaded_file.save(stored_path)
    return random_filename, file_size, None


def query_browse_materials(db, university_id, search_query, subject_filter, semester_filter, type_filter, sort_by, page, per_page=9):
    """
    Execute paginated query for active study materials strictly filtered by university_id.

    Args:
        db: SQLite database connection.
        university_id (int): Student's university ID.
        search_query (str): Optional search query.
        subject_filter (str): Optional subject filter.
        semester_filter (str): Optional semester number filter.
        type_filter (str): Optional file type filter.
        sort_by (str): Sort key ('newest', 'top_rated', 'most_downloaded', 'oldest').
        page (int): Current page number (1-indexed).
        per_page (int): Items per page.

    Returns:
        dict: Query results containing files, total_items, total_pages, and subjects.
    """
    # Strict university isolation filter
    sql_base = """
        FROM files f
        JOIN users u ON f.uploader_id = u.id
        LEFT JOIN ratings r ON f.id = r.file_id
        LEFT JOIN downloads d ON f.id = d.file_id
        WHERE f.university_id = ? AND f.status = 'active'
    """
    params = [university_id]

    if search_query:
        sql_base += " AND (f.title LIKE ? OR f.subject LIKE ? OR f.description LIKE ?)"
        term = f"%{search_query}%"
        params.extend([term, term, term])

    if subject_filter:
        sql_base += " AND f.subject = ?"
        params.append(subject_filter)

    if semester_filter:
        sql_base += " AND f.semester = ?"
        params.append(semester_filter)

    if type_filter:
        sql_base += " AND f.type = ?"
        params.append(type_filter)

    count_sql = f"SELECT COUNT(DISTINCT f.id) {sql_base}"
    total_items = db.execute(count_sql, params).fetchone()[0]
    total_pages = max(1, (total_items + per_page - 1) // per_page)
    offset = (page - 1) * per_page

    order_clause = "ORDER BY f.created_at DESC"
    if sort_by == 'top_rated':
        order_clause = "ORDER BY avg_rating DESC, rating_count DESC, f.created_at DESC"
    elif sort_by == 'most_downloaded':
        order_clause = "ORDER BY download_count DESC, f.created_at DESC"
    elif sort_by == 'oldest':
        order_clause = "ORDER BY f.created_at ASC"

    select_sql = f"""
        SELECT f.id, f.title, f.subject, f.semester, f.type, f.description,
               f.size, f.created_at, u.username as uploader_username,
               COALESCE(AVG(r.stars), 0.0) as avg_rating,
               COUNT(DISTINCT r.id) as rating_count,
               COUNT(DISTINCT d.id) as download_count
        {sql_base}
        GROUP BY f.id
        {order_clause}
        LIMIT ? OFFSET ?
    """
    files = db.execute(select_sql, list(params) + [per_page, offset]).fetchall()

    subjects_raw = db.execute(
        "SELECT DISTINCT subject FROM files WHERE university_id = ? AND status = 'active' ORDER BY subject",
        (university_id,)
    ).fetchall()

    return {
        'files': files,
        'total_items': total_items,
        'total_pages': total_pages,
        'subjects': [s['subject'] for s in subjects_raw]
    }


def get_file_detail_isolated(db, file_id, university_id):
    """
    Fetch single file record with aggregated ratings and download counts.

    Returns None if file does not exist or does not match the user's university_id.

    Args:
        db: SQLite database connection.
        file_id (int): File primary key.
        university_id (int): Student's university ID.

    Returns:
        Row or None: File record or None if unauthorized/missing.
    """
    return db.execute(
        """
        SELECT f.*, u.username as uploader_username,
               COALESCE(AVG(r.stars), 0.0) as avg_rating,
               COUNT(DISTINCT r.id) as rating_count,
               COUNT(DISTINCT d.id) as download_count
        FROM files f
        JOIN users u ON f.uploader_id = u.id
        LEFT JOIN ratings r ON f.id = r.file_id
        LEFT JOIN downloads d ON f.id = d.file_id
        WHERE f.id = ? AND f.university_id = ? AND f.status = 'active'
        GROUP BY f.id
        """,
        (file_id, university_id)
    ).fetchone()


def takedown_file_admin(db, file_id, default_reward):
    """
    Execute administrative takedown of violating content with credit reversal.

    Args:
        db: SQLite database connection.
        file_id (int): Target file ID.
        default_reward (int): Fallback reward amount to reverse.

    Returns:
        tuple: (success: bool, file_title: str or None, reversal_amount: int)
    Side effects:
        Updates file status to 'removed', reverses credits, marks reports resolved.
    """
    cursor = db.cursor()
    try:
        cursor.execute("BEGIN IMMEDIATE")
        file = cursor.execute("SELECT * FROM files WHERE id = ?", (file_id,)).fetchone()
        if not file:
            db.rollback()
            return False, None, 0

        cursor.execute("UPDATE files SET status = 'removed' WHERE id = ?", (file_id,))
        reversal_amount = reverse_upload_credits(cursor, file_id, file['uploader_id'], default_reward)
        cursor.execute("UPDATE reports SET status = 'resolved' WHERE file_id = ?", (file_id,))
        db.commit()
        return True, file['title'], reversal_amount
    except Exception:
        db.rollback()
        return False, None, 0
