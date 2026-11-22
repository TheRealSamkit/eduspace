"""
Global HTTP error handlers for StudyExchange.

Renders custom error pages for client and server status codes.
Depends on Flask (render_template).
"""

from flask import render_template


def register_error_handlers(app):
    """
    Register application-wide HTTP error handlers.

    Args:
        app (Flask): Flask application instance.
    """

    @app.errorhandler(400)
    def bad_request(error):
        """Handle 400 Bad Request."""
        return render_template(
            '404.html',
            error_title="400 - Bad Request",
            error_message=getattr(error, 'description', "Bad request.")
        ), 400

    @app.errorhandler(403)
    def forbidden(error):
        """Handle 403 Forbidden."""
        return render_template(
            '404.html',
            error_title="403 - Forbidden",
            error_message=getattr(error, 'description', "Access forbidden.")
        ), 403

    @app.errorhandler(404)
    def page_not_found(error):
        """Handle 404 Not Found."""
        return render_template(
            '404.html',
            error_title="404 - Not Found",
            error_message=getattr(error, 'description', "The requested page or material could not be found.")
        ), 404

    @app.errorhandler(500)
    def server_error(error):
        """Handle 500 Internal Server Error."""
        return render_template('500.html'), 500
