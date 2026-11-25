"""
EduSpace application package.

Provides create_app() factory initializing configuration, database,
request lifecycle hooks, error handlers, and modular blueprints.
"""

import os
from flask import Flask
from config import Config
from db import init_app
from eduspace.hooks import init_hooks
from eduspace.blueprints.errors import register_error_handlers
from eduspace.blueprints.pages import bp as pages_bp
from eduspace.blueprints.auth import bp as auth_bp
from eduspace.blueprints.library import bp as library_bp
from eduspace.blueprints.public import bp as public_bp
from eduspace.blueprints.requests import bp as requests_bp
from eduspace.blueprints.upload import bp as upload_bp
from eduspace.blueprints.dashboard import bp as dashboard_bp
from eduspace.blueprints.admin import bp as admin_bp
from eduspace.blueprints.research import bp as research_bp
from eduspace.blueprints.api import bp as api_bp


def create_app(test_config=None):
    """
    Application factory for EduSpace.

    Args:
        test_config (dict, optional): Custom configuration overrides for testing.

    Returns:
        Flask: Fully configured Flask application instance.
    """
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    app = Flask('eduspace', root_path=project_root)
    app.config.from_object(Config)

    if test_config:
        app.config.update(test_config)

    # Initialize SQLite database and ensure upload directory
    init_app(app)

    # Register request lifecycle hooks and global template context
    init_hooks(app)

    # Register global HTTP error handlers
    register_error_handlers(app)

    # Register modular blueprints
    app.register_blueprint(pages_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(library_bp)
    app.register_blueprint(public_bp)
    app.register_blueprint(requests_bp)
    app.register_blueprint(upload_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(research_bp)
    app.register_blueprint(api_bp)

    return app
