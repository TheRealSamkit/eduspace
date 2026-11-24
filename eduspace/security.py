"""
Security helpers and authorization decorators for EduSpace.

Depends on Flask (session, g, request, redirect, url_for, flash, abort)
and secrets.
"""

import secrets
from functools import wraps
from flask import session, g, request, redirect, url_for, flash, abort


def get_csrf_token():
    """
    Generate or retrieve a CSRF token stored in session.

    Returns:
        str: 32-character hexadecimal token.
    Side effects:
        Stores new token in session['csrf_token'] if not present.
    """
    if 'csrf_token' not in session:
        session['csrf_token'] = secrets.token_hex(16)
    return session['csrf_token']


def login_required(f):
    """
    Decorator ensuring user is authenticated.

    Args:
        f (callable): View function to wrap.

    Returns:
        callable: Decorated view function that redirects to login if unauthenticated.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if g.user is None:
            flash("Please log in to access this page.", "warning")
            return redirect(url_for('auth.login', next=request.url))
        return f(*args, **kwargs)
    return decorated_function


def admin_required(f):
    """
    Decorator ensuring user is an administrator.

    Args:
        f (callable): View function to wrap.

    Returns:
        callable: Decorated view function that enforces admin role or returns 403.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if g.user is None:
            flash("Administrator access required.", "warning")
            return redirect(url_for('auth.login', next=request.url))
        if not g.user['is_admin']:
            abort(403, description="Forbidden: Administrator privileges required.")
        return f(*args, **kwargs)
    return decorated_function
