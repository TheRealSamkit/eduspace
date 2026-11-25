"""
Application lifecycle hooks and context processors for EduSpace.

Manages per-request session tracking, authentication state hydration,
research consent gating, CSRF verification, and cache headers.
Depends on Flask, db.get_db, and eduspace.security.get_csrf_token.
"""

import uuid
from flask import request, session, g, redirect, url_for, abort
from db import get_db
from eduspace.security import get_csrf_token


def init_hooks(app):
    """
    Register context processors and request lifecycle hooks on the Flask application.

    Args:
        app (Flask): The Flask application instance.
    """

    @app.context_processor
    def inject_global_template_data():
        """
        Expose current user, CSRF generator, and config to Jinja templates.

        Returns:
            dict: Template context containing current_user, csrf_token, and config.
        """
        user_id = session.get('user_id')
        fresh_user = None
        if user_id:
            try:
                db = get_db()
                fresh_user = db.execute(
                    """
                    SELECT u.id, u.email, u.username, u.credits, u.is_admin,
                           u.university_id, un.name as university_name,
                           un.domain as university_domain, un.kind as university_kind
                    FROM users u
                    JOIN universities un ON u.university_id = un.id
                    WHERE u.id = ?
                    """,
                    (user_id,)
                ).fetchone()
                g.user = fresh_user
            except Exception:
                fresh_user = getattr(g, 'user', None)

        return {
            'current_user': fresh_user,
            'csrf_token': get_csrf_token,
            'config': app.config
        }

    @app.before_request
    def load_user_and_session():
        """
        Hydrate request state:
        1. Manages study_session_id tracking cookie.
        2. Hydrates g.user from session.
        3. Gates unconsented users to /consent.
        4. Validates CSRF tokens on POST requests.
        5. Logs page view events for research analytics.
        """
        # 1. Manage session_id cookie
        session_id = request.cookies.get('study_session_id')
        if not session_id:
            session_id = uuid.uuid4().hex
            g.new_session_id = session_id
        g.session_id = session_id

        # 2. Load authenticated user
        g.user = None
        user_id = session.get('user_id')
        if user_id:
            db = get_db()
            user = db.execute(
                """
                SELECT u.id, u.email, u.username, u.credits, u.is_admin,
                       u.university_id, un.name as university_name,
                       un.domain as university_domain, un.kind as university_kind
                FROM users u
                JOIN universities un ON u.university_id = un.id
                WHERE u.id = ?
                """,
                (user_id,)
            ).fetchone()
            if user:
                g.user = user
            else:
                session.clear()

        # 3. Check research consent for authenticated users
        if g.user:
            db = get_db()
            consent = db.execute(
                "SELECT 1 FROM consents WHERE user_id = ?",
                (g.user['id'],)
            ).fetchone()
            g.has_consented = bool(consent)

            # Redirect unconsented users to /consent (endpoints use blueprint prefix)
            allowed_endpoints = {
                'auth.consent', 'auth.logout', 'static',
                'api.api_event', 'api.api_credits', 'api.api_me', 'api.api_domain_check'
            }
            if not g.has_consented and request.endpoint and request.endpoint not in allowed_endpoints:
                return redirect(url_for('auth.consent'))
        else:
            g.has_consented = False

        # 4. CSRF Validation on POST
        if request.method == 'POST':
            client_token = request.form.get('csrf_token') or request.headers.get('X-CSRFToken')
            expected_token = session.get('csrf_token')
            if not app.config.get('TESTING'):
                if not client_token or not expected_token or client_token != expected_token:
                    if request.endpoint not in {'api.api_event'}:
                        abort(400, description="Invalid or missing CSRF token.")

        # 5. Server-side page view event logging (ignore static and api)
        if request.method == 'GET' and request.endpoint and request.endpoint not in {
            'static', 'api.api_event', 'api.api_me', 'api.api_domain_check'
        }:
            try:
                db = get_db()
                db.execute(
                    """
                    INSERT INTO events (session_id, user_id, event_type, page, detail)
                    VALUES (?, ?, 'page_view', ?, ?)
                    """,
                    (g.session_id, g.user['id'] if g.user else None, request.path, request.user_agent.string[:200])
                )
                db.commit()
            except Exception:
                pass

    @app.after_request
    def set_session_cookie(response):
        """
        Persist session cookie and apply no-store cache headers to non-static assets.

        Args:
            response (Response): Outgoing Flask response.

        Returns:
            Response: Modified response with headers and cookies.
        """
        if hasattr(g, 'new_session_id'):
            response.set_cookie(
                'study_session_id',
                g.new_session_id,
                max_age=30 * 24 * 3600,
                httponly=True,
                samesite='Lax'
            )
        # Apply strict no-store cache-control for security & research measurement accuracy
        if not request.path.startswith('/static/'):
            response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
            response.headers['Pragma'] = 'no-cache'
            response.headers['Expires'] = '0'
        return response
