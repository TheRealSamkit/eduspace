"""
Public and informational page routes for StudyExchange.

Includes landing page, terms of service, and browser favicon.
Depends on Flask (Blueprint, render_template, redirect, url_for, g).
"""

from flask import Blueprint, render_template, redirect, url_for, g

bp = Blueprint('pages', __name__)


@bp.route('/')
def index():
    """
    Public landing page or redirect to repository if already logged in.

    Returns:
        Response: Redirect to library.browse if authenticated, else rendered index.html.
    """
    if g.user:
        return redirect(url_for('library.browse'))
    return render_template('index.html')


@bp.route('/terms')
def terms_page():
    """
    Display terms of service, copyright policy, and takedown procedures.

    Returns:
        Response: Rendered terms.html.
    """
    return render_template('terms.html')


@bp.route('/favicon.ico')
def favicon():
    """
    Handle browser favicon request without generating 404 logs.

    Returns:
        tuple: Empty response with 204 No Content.
    """
    return ("", 204)
