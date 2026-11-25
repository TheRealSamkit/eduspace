"""
Centralised visibility and access-control helpers for EduSpace.

Enforces institutional isolation, public library rules, and status-based
moderation visibility across files and resource requests.
"""


def _field(obj, key, default=None):
    """Safely read a key from a sqlite3.Row or dict."""
    if obj is None:
        return default
    try:
        return obj[key]
    except (KeyError, IndexError, TypeError):
        return default


def is_public_member(user):
    """
    Return True if the user belongs to the public (non-partner) university tier.

    Args:
        user (Row|dict|None): Authenticated user record.

    Returns:
        bool: True if user is a public member.
    """
    return bool(user and _field(user, 'university_kind') == 'public')


def can_view_file(user, file):
    """
    Determine whether a user (or guest when user is None) may view a file.

    Rules:
    - Status other than 'active' ('hidden' or 'removed') is visible only to
      admins (within their scope: public files or their own university's private
      files) and to the uploader. Never visible to guests or other students.
    - Active files with visibility='public' are visible to everyone.
    - Active files with visibility='university' are visible only to logged-in
      partner-university users of the SAME university_id (never to guests or
      public-member accounts).

    Args:
        user (Row|dict|None): Current user or None for guest.
        file (Row|dict|None): File record.

    Returns:
        bool: True if access is permitted.
    """
    if file is None:
        return False

    status = _field(file, 'status', 'active')
    visibility = _field(file, 'visibility', 'university')
    file_uni_id = _field(file, 'university_id')
    uploader_id = _field(file, 'uploader_id')

    if status != 'active':
        if user is None:
            return False
        user_id = _field(user, 'id')
        if user_id == uploader_id:
            return True
        if _field(user, 'is_admin'):
            if visibility == 'public':
                return True
            if not is_public_member(user) and _field(user, 'university_id') == file_uni_id:
                return True
        return False

    if visibility == 'public':
        return True

    if visibility == 'university':
        if user is None or is_public_member(user):
            return False
        return _field(user, 'university_id') == file_uni_id

    return False


def file_visibility_where(user, scope='university', alias='f'):
    """
    Build a SQL WHERE fragment and parameters for listing active files.

    Args:
        user (Row|dict|None): Current user or None for guest.
        scope (str): 'university' (partner library), 'public' (public library),
            or 'visible' (all active files the user can view, e.g. bookmarks).
        alias (str): Table alias for files in the query.

    Returns:
        tuple: (sql_condition: str, params: list)
    """
    if scope == 'public':
        return f"{alias}.visibility = 'public' AND {alias}.status = 'active'", []

    if scope == 'university':
        if user is None or is_public_member(user):
            return "1 = 0", []
        return (
            f"{alias}.university_id = ? AND {alias}.visibility = 'university' AND {alias}.status = 'active'",
            [_field(user, 'university_id')]
        )

    if scope == 'visible':
        if user is None or is_public_member(user):
            return f"{alias}.visibility = 'public' AND {alias}.status = 'active'", []
        return (
            f"({alias}.visibility = 'public' OR "
            f"({alias}.visibility = 'university' AND {alias}.university_id = ?)) "
            f"AND {alias}.status = 'active'",
            [_field(user, 'university_id')]
        )

    return "1 = 0", []


def can_view_request(user, req):
    """
    Determine whether an authenticated user may view a resource request.

    Args:
        user (Row|dict|None): Current user or None for guest.
        req (Row|dict|None): Resource request record.

    Returns:
        bool: True if access is permitted.
    """
    if user is None or req is None:
        return False

    visibility = _field(req, 'visibility', 'university')
    if visibility == 'public':
        return True

    if visibility == 'university':
        if is_public_member(user):
            return False
        return _field(user, 'university_id') == _field(req, 'university_id')

    return False


def request_visibility_where(user, alias='rr'):
    """
    Build a SQL WHERE fragment and parameters for listing visible resource requests.

    Args:
        user (Row|dict|None): Current user.
        alias (str): Table alias for resource_requests.

    Returns:
        tuple: (sql_condition: str, params: list)
    """
    if user is None:
        return "1 = 0", []
    if is_public_member(user):
        return f"{alias}.visibility = 'public'", []
    return (
        f"({alias}.visibility = 'public' OR ({alias}.visibility = 'university' AND {alias}.university_id = ?))",
        [_field(user, 'university_id')]
    )
