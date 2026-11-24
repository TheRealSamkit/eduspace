"""
Authentication, registration, session termination, and research consent routes.

Depends on Flask, werkzeug.security, db.get_db, and eduspace.services.credits.
"""

import sqlite3
from flask import (
    Blueprint, render_template, request, redirect,
    url_for, flash, session, g, current_app
)
from werkzeug.security import generate_password_hash, check_password_hash
from config import Config
from db import get_db
from eduspace.services.credits import record_ledger_entry

bp = Blueprint('auth', __name__)


def validate_registration_form(username, email, password, agree_terms, allowed_domains):
    """
    Validate student registration form inputs and institutional domain.

    Args:
        username (str): Proposed username.
        email (str): Institutional email address.
        password (str): Password.
        agree_terms (str or None): Agreement checkbox value.
        allowed_domains (dict): Whitelisted domain mappings.

    Returns:
        tuple: (errors: list of str, domain: str)
    """
    errors = []
    if not username or len(username) < 3:
        errors.append("Username must be at least 3 characters.")
    if not email or '@' not in email:
        errors.append("A valid email address is required.")
    if not password or len(password) < 8:
        errors.append("Password must be at least 8 characters long.")
    if not agree_terms:
        errors.append("You must agree to the Terms of Service and Copyright policy.")

    domain = email.split('@')[-1] if '@' in email else ''
    if domain not in allowed_domains:
        errors.append(
            f"Email domain '@{domain}' is not recognized. "
            f"Only allowed universities can register: {', '.join(['@' + d for d in allowed_domains.keys()])}."
        )
    return errors, domain


def create_user_account(db, email, username, pwd_hash, uni_id, is_admin, signup_bonus):
    """
    Atomically insert user record and initial signup bonus ledger entry.

    Args:
        db: SQLite database connection.
        email (str): User email.
        username (str): Public username.
        pwd_hash (str): Password hash.
        uni_id (int): University primary key.
        is_admin (int): 1 if admin, 0 otherwise.
        signup_bonus (int): Initial credits awarded on registration.

    Returns:
        int: Created user primary key.
    """
    cursor = db.cursor()
    cursor.execute("BEGIN IMMEDIATE")
    cursor.execute(
        """
        INSERT INTO users (email, username, password_hash, university_id, credits, is_admin)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (email, username, pwd_hash, uni_id, signup_bonus, is_admin)
    )
    user_id = cursor.lastrowid
    record_ledger_entry(cursor, user_id, signup_bonus, 'signup', None)
    db.commit()
    return user_id


@bp.route('/register', methods=['GET', 'POST'])
def register():
    """
    Register a new student account:
    - Validates institutional domain against ALLOWED_DOMAINS.
    - Creates university mapping if needed.
    - Atomic transaction: inserts user and awards initial signup credits in ledger.

    Returns:
        Response: Redirect to consent on success, or rendered register.html on GET/error.
    """
    if g.user:
        return redirect(url_for('library.browse'))

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        agree_terms = request.form.get('agree_terms')

        allowed_domains = current_app.config.get('ALLOWED_DOMAINS', Config.ALLOWED_DOMAINS)
        errors, domain = validate_registration_form(username, email, password, agree_terms, allowed_domains)
        if errors:
            for err in errors:
                flash(err, "danger")
            return render_template('register.html', username=username, email=email)

        db = get_db()
        uni = db.execute("SELECT id FROM universities WHERE domain = ?", (domain,)).fetchone()
        if not uni:
            uni_name = allowed_domains.get(domain, domain.upper())
            cursor = db.execute("INSERT INTO universities (name, domain) VALUES (?, ?)", (uni_name, domain))
            uni_id = cursor.lastrowid
        else:
            uni_id = uni['id']

        existing = db.execute(
            "SELECT email, username FROM users WHERE email = ? OR username = ?",
            (email, username)
        ).fetchone()
        if existing:
            msg = "An account with that email already exists. Please log in." if existing['email'] == email \
                else "That username is already taken. Please choose another."
            flash(msg, "warning")
            return render_template('register.html', username=username, email=email)

        pwd_hash = generate_password_hash(password)
        is_admin = 1 if email == current_app.config.get('ADMIN_EMAIL', Config.ADMIN_EMAIL) else 0
        signup_bonus = current_app.config.get('SIGNUP_BONUS', Config.SIGNUP_BONUS)

        try:
            user_id = create_user_account(db, email, username, pwd_hash, uni_id, is_admin, signup_bonus)
        except sqlite3.IntegrityError:
            db.rollback()
            flash("An account with that email or username already exists. Please log in.", "warning")
            return render_template('register.html', username=username, email=email)
        except Exception as e:
            db.rollback()
            current_app.logger.error("Registration transaction error: %s", e, exc_info=True)
            flash("Registration failed due to a server error. Please try again.", "danger")
            return render_template('register.html', username=username, email=email)

        session['user_id'] = user_id
        flash(f"Welcome to EduSpace, {username}! You have received {signup_bonus} bonus credits.", "success")
        return redirect(url_for('auth.consent'))

    return render_template('register.html')


@bp.route('/consent', methods=['GET', 'POST'])
def consent():
    """
    Academic research consent gate presented before accessing platform features.

    Returns:
        Response: Redirect to browse upon agreement, or rendered consent.html.
    """
    if not g.user:
        return redirect(url_for('auth.login'))

    if request.method == 'POST':
        agreed = request.form.get('agree_consent')
        if agreed:
            db = get_db()
            db.execute("INSERT OR IGNORE INTO consents (user_id) VALUES (?)", (g.user['id'],))
            db.commit()
            flash("Thank you for consenting to anonymised academic evaluation.", "success")
            return redirect(url_for('library.browse'))
        else:
            flash("Please check the agreement box to proceed.", "warning")

    return render_template('consent.html')


@bp.route('/login', methods=['GET', 'POST'])
def login():
    """
    Authenticate an existing student or administrator.

    Returns:
        Response: Redirect to target or browse on success, or rendered login.html on error.
    """
    if g.user:
        return redirect(url_for('library.browse'))

    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')

        db = get_db()
        user = db.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()

        if user and check_password_hash(user['password_hash'], password):
            session['user_id'] = user['id']
            flash(f"Welcome back, {user['username']}!", "success")
            next_url = request.args.get('next')
            if next_url and next_url.startswith('/'):
                return redirect(next_url)
            return redirect(url_for('library.browse'))
        else:
            flash("Invalid email or password. Please try again.", "danger")

    return render_template('login.html')


@bp.route('/logout', methods=['GET', 'POST'])
def logout():
    """
    Log out active user, clear session, and invalidate tracking cookies.

    Returns:
        Response: Redirect to login with cleared cookies.
    """
    session.clear()
    flash("You have been logged out.", "info")
    resp = redirect(url_for('auth.login'))
    resp.delete_cookie(current_app.config.get('SESSION_COOKIE_NAME', 'session'))
    resp.delete_cookie('study_session_id')
    return resp
