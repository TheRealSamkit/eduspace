import os
import uuid
import secrets
from datetime import datetime
from functools import wraps
from flask import (
    Flask, render_template, request, redirect, url_for,
    flash, session, g, abort, send_from_directory, jsonify, make_response
)
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

from config import Config
from db import get_db, init_app

def create_app(test_config=None):
    """Application factory for StudyExchange."""
    app = Flask(__name__)
    app.config.from_object(Config)

    if test_config:
        app.config.update(test_config)

    # Initialize SQLite database and ensure upload directory
    init_app(app)

    # ---------------------------------------------------------
    # Context Processors & Template Helpers
    # ---------------------------------------------------------
    @app.context_processor
    def inject_global_template_data():
        """Expose current user (with fresh DB credits on every render), csrf token, and config."""
        user_id = session.get('user_id')
        fresh_user = None
        if user_id:
            try:
                db = get_db()
                fresh_user = db.execute(
                    """
                    SELECT u.id, u.email, u.username, u.credits, u.is_admin,
                           u.university_id, un.name as university_name, un.domain as university_domain
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

    def get_csrf_token():
        """Generate or retrieve a CSRF token stored in session."""
        if 'csrf_token' not in session:
            session['csrf_token'] = secrets.token_hex(16)
        return session['csrf_token']

    # ---------------------------------------------------------
    # Request Hooks: Session Tracking, Auth, Consent & Events
    # ---------------------------------------------------------
    @app.before_request
    def load_user_and_session():
        """
        Runs before every request:
        1. Tracks anonymous or authenticated user with session_id cookie.
        2. Loads logged-in user details, theme, and university information.
        3. Enforces consent agreement before platform usage.
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
                       u.university_id, un.name as university_name, un.domain as university_domain
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

            # Redirect unconsented users to /consent
            allowed_endpoints = {'consent', 'logout', 'static', 'api_event', 'api_credits', 'api_me', 'api_domain_check'}
            if not g.has_consented and request.endpoint and request.endpoint not in allowed_endpoints:
                return redirect(url_for('consent'))
        else:
            g.has_consented = False

        # 4. CSRF Validation on POST
        if request.method == 'POST':
            # Check CSRF token from form or header
            client_token = request.form.get('csrf_token') or request.headers.get('X-CSRFToken')
            expected_token = session.get('csrf_token')
            # Bypass CSRF check if test mode explicitly disables it or if tokens match
            if not app.config.get('TESTING'):
                if not client_token or not expected_token or client_token != expected_token:
                    # Allow json api logging with session if available, else abort
                    if request.endpoint not in {'api_event'}:
                        abort(400, description="Invalid or missing CSRF token.")

        # 5. Server-side page view event logging (ignore static and api)
        if request.method == 'GET' and request.endpoint and request.endpoint not in {'static', 'api_event', 'api_me', 'api_domain_check'}:
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
                # Do not disrupt request flow if event logging fails
                pass

    @app.after_request
    def set_session_cookie(response):
        """Persist session_id cookie if newly generated and apply no-store headers to all non-static responses."""
        if hasattr(g, 'new_session_id'):
            response.set_cookie(
                'study_session_id',
                g.new_session_id,
                max_age=30*24*3600,
                httponly=True,
                samesite='Lax'
            )
        if not request.path.startswith('/static/'):
            response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
            response.headers['Pragma'] = 'no-cache'
            response.headers['Expires'] = '0'
        return response

    # ---------------------------------------------------------
    # Authentication Decorators
    # ---------------------------------------------------------
    def login_required(f):
        """Decorator ensuring user is logged in."""
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if g.user is None:
                flash("Please log in to access this page.", "warning")
                return redirect(url_for('login', next=request.url))
            return f(*args, **kwargs)
        return decorated_function

    def admin_required(f):
        """Decorator ensuring user is an administrator."""
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if g.user is None:
                flash("Administrator access required.", "warning")
                return redirect(url_for('login', next=request.url))
            if not g.user['is_admin']:
                abort(403, description="Forbidden: Administrator privileges required.")
            return f(*args, **kwargs)
        return decorated_function

    # ---------------------------------------------------------
    # Authentication Routes
    # ---------------------------------------------------------
    @app.route('/')
    def index():
        """Public landing page or redirect to browse if logged in."""
        if g.user:
            return redirect(url_for('browse'))
        return render_template('index.html')

    @app.route('/register', methods=['GET', 'POST'])
    def register():
        """
        Student registration:
        - Strict institutional email domain verification (ALLOWED_DOMAINS).
        - Assigns university based on domain.
        - Hashes password (min 8 chars) using werkzeug.
        - Awards SIGNUP_BONUS (20 credits) with a ledger record.
        - Sets admin flag if email matches ADMIN_EMAIL.
        """
        if g.user:
            return redirect(url_for('browse'))

        if request.method == 'POST':
            username = request.form.get('username', '').strip()
            email = request.form.get('email', '').strip().lower()
            password = request.form.get('password', '')
            agree_terms = request.form.get('agree_terms')

            errors = []
            if not username or len(username) < 3:
                errors.append("Username must be at least 3 characters.")
            if not email or '@' not in email:
                errors.append("A valid email address is required.")
            if not password or len(password) < 8:
                errors.append("Password must be at least 8 characters long.")
            if not agree_terms:
                errors.append("You must agree to the Terms of Service and Copyright policy.")

            # Validate institutional email domain
            domain = email.split('@')[-1] if '@' in email else ''
            allowed_domains = app.config.get('ALLOWED_DOMAINS', Config.ALLOWED_DOMAINS)
            if domain not in allowed_domains:
                errors.append(
                    f"Email domain '@{domain}' is not recognized. "
                    f"Only allowed universities can register: {', '.join(['@' + d for d in allowed_domains.keys()])}."
                )

            if errors:
                for err in errors:
                    flash(err, "danger")
                return render_template('register.html', username=username, email=email)

            db = get_db()
            # Find university record
            uni = db.execute("SELECT id FROM universities WHERE domain = ?", (domain,)).fetchone()
            if not uni:
                # Should have been seeded, but insert if missing
                uni_name = allowed_domains.get(domain, domain.upper())
                cursor = db.execute("INSERT INTO universities (name, domain) VALUES (?, ?)", (uni_name, domain))
                uni_id = cursor.lastrowid
            else:
                uni_id = uni['id']

            # Check uniqueness
            existing = db.execute(
                "SELECT email, username FROM users WHERE email = ? OR username = ?",
                (email, username)
            ).fetchone()
            if existing:
                if existing['email'] == email:
                    flash("An account with that email already exists. Please log in.", "warning")
                else:
                    flash("That username is already taken. Please choose another.", "warning")
                return render_template('register.html', username=username, email=email)

            # Hash password & determine admin status
            pwd_hash = generate_password_hash(password)
            is_admin = 1 if email == app.config.get('ADMIN_EMAIL', Config.ADMIN_EMAIL) else 0
            signup_bonus = app.config.get('SIGNUP_BONUS', Config.SIGNUP_BONUS)

            try:
                # Atomic DB transaction: create user and initial ledger entry
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
                cursor.execute(
                    """
                    INSERT INTO ledger (user_id, amount, reason, file_id)
                    VALUES (?, ?, 'signup', NULL)
                    """,
                    (user_id, signup_bonus)
                )
                db.commit()
            except sqlite3.IntegrityError:
                db.rollback()
                flash("An account with that email or username already exists. Please log in.", "warning")
                return render_template('register.html', username=username, email=email)
            except Exception as e:
                db.rollback()
                app.logger.error("Registration transaction error: %s", e, exc_info=True)
                flash("Registration failed due to a server error. Please try again.", "danger")
                return render_template('register.html', username=username, email=email)

            # Success flow strictly outside the DB transaction try/except block
            session['user_id'] = user_id
            flash(f"Welcome to StudyExchange, {username}! You have received {signup_bonus} bonus credits.", "success")
            return redirect(url_for('consent'))

        return render_template('register.html')

    @app.route('/consent', methods=['GET', 'POST'])
    def consent():
        """Academic research consent page shown before first platform use."""
        if not g.user:
            return redirect(url_for('login'))

        if request.method == 'POST':
            agreed = request.form.get('agree_consent')
            if agreed:
                db = get_db()
                db.execute(
                    "INSERT OR IGNORE INTO consents (user_id) VALUES (?)",
                    (g.user['id'],)
                )
                db.commit()
                flash("Thank you for consenting to anonymised academic evaluation.", "success")
                return redirect(url_for('browse'))
            else:
                flash("Please check the agreement box to proceed.", "warning")

        return render_template('consent.html')

    @app.route('/login', methods=['GET', 'POST'])
    def login():
        """User login route."""
        if g.user:
            return redirect(url_for('browse'))

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
                return redirect(url_for('browse'))
            else:
                flash("Invalid email or password. Please try again.", "danger")

        return render_template('login.html')

    @app.route('/logout', methods=['GET', 'POST'])
    def logout():
        """Log out the current user, expire cookies, and redirect to login."""
        session.clear()
        flash("You have been logged out.", "info")
        resp = redirect(url_for('login'))
        resp.delete_cookie(app.config.get('SESSION_COOKIE_NAME', 'session'))
        resp.delete_cookie('study_session_id')
        return resp

    # ---------------------------------------------------------
    # Core Resource Routes: Browse, Upload, Details, Download
    # ---------------------------------------------------------
    @app.route('/browse')
    @login_required
    def browse():
        """
        Browse and search study material.
        STRICT UNIVERSITY ISOLATION:
        Only materials belonging to the logged-in user's university_id are queried.
        """
        search_query = request.args.get('q', '').strip()
        subject_filter = request.args.get('subject', '').strip()
        semester_filter = request.args.get('semester', '').strip()
        type_filter = request.args.get('type', '').strip()
        sort_by = request.args.get('sort', 'newest')
        page = max(1, request.args.get('page', 1, type=int))
        per_page = 9

        db = get_db()

        # Base query with university isolation and active status
        sql_base = """
            FROM files f
            JOIN users u ON f.uploader_id = u.id
            LEFT JOIN ratings r ON f.id = r.file_id
            LEFT JOIN downloads d ON f.id = d.file_id
            WHERE f.university_id = ? AND f.status = 'active'
        """
        params = [g.user['university_id']]

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

        # Count total matching files for pagination
        count_sql = f"SELECT COUNT(DISTINCT f.id) {sql_base}"
        total_items = db.execute(count_sql, params).fetchone()[0]
        total_pages = max(1, (total_items + per_page - 1) // per_page)
        offset = (page - 1) * per_page

        # Sorting logic
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
        query_params = list(params) + [per_page, offset]
        files = db.execute(select_sql, query_params).fetchall()

        # Retrieve distinct subjects for filter dropdown (isolated to university)
        subjects = db.execute(
            "SELECT DISTINCT subject FROM files WHERE university_id = ? AND status = 'active' ORDER BY subject",
            (g.user['university_id'],)
        ).fetchall()

        return render_template(
            'browse.html',
            files=files,
            total_items=total_items,
            page=page,
            total_pages=total_pages,
            search_query=search_query,
            subject_filter=subject_filter,
            semester_filter=semester_filter,
            type_filter=type_filter,
            sort_by=sort_by,
            subjects=[s['subject'] for s in subjects]
        )

    @app.route('/upload', methods=['GET', 'POST'])
    @login_required
    def upload_file():
        """
        Upload study material:
        - Validates file type, size, extension, required metadata.
        - Requires copyright affirmation checkbox.
        - Assigns random stored filename.
        - Implements daily upload reward cap (MAX_REWARDED_UPLOADS_PER_DAY).
        - Always logs upload in the ledger (with reward or 0 credits).
        """
        if request.method == 'POST':
            title = request.form.get('title', '').strip()
            subject = request.form.get('subject', '').strip()
            semester = request.form.get('semester', type=int)
            file_type = request.form.get('type', '').strip()
            description = request.form.get('description', '').strip()
            confirm_copyright = request.form.get('confirm_copyright')
            uploaded_file = request.files.get('file')

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

            # Validate extension
            original_filename = secure_filename(uploaded_file.filename) if uploaded_file else ""
            ext = original_filename.rsplit('.', 1)[-1].lower() if '.' in original_filename else ""
            allowed_exts = app.config.get('ALLOWED_EXT', Config.ALLOWED_EXT)
            if ext not in allowed_exts:
                errors.append(f"Invalid file extension '.{ext}'. Allowed formats: {', '.join(allowed_exts)}.")

            if errors:
                for err in errors:
                    flash(err, "danger")
                return render_template('upload.html')

            # Check file size (read into memory or check length)
            uploaded_file.seek(0, os.SEEK_END)
            file_size = uploaded_file.tell()
            uploaded_file.seek(0)
            max_bytes = app.config.get('MAX_CONTENT_LENGTH', Config.MAX_CONTENT_LENGTH)
            if file_size > max_bytes:
                flash(f"File exceeds maximum allowed size of {app.config.get('MAX_FILE_MB', Config.MAX_FILE_MB)}MB.", "danger")
                return render_template('upload.html')

            # Generate unique random stored filename
            random_filename = f"{uuid.uuid4().hex}.{ext}"
            upload_dir = app.config.get('UPLOAD_FOLDER', Config.UPLOAD_FOLDER)
            os.makedirs(upload_dir, exist_ok=True)
            stored_path = os.path.join(upload_dir, random_filename)
            uploaded_file.save(stored_path)

            db = get_db()
            cursor = db.cursor()

            try:
                # 1. Insert file record linked to user's university
                cursor.execute(
                    """
                    INSERT INTO files (
                        uploader_id, university_id, title, subject, semester,
                        type, description, stored_name, original_name, size, status
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'active')
                    """,
                    (
                        g.user['id'], g.user['university_id'], title, subject,
                        semester, file_type, description, random_filename,
                        original_filename, file_size
                    )
                )
                file_id = cursor.lastrowid

                # 2. Daily reward calculation
                # Check how many rewarded uploads the user has received today
                max_rewarded = app.config.get('MAX_REWARDED_UPLOADS_PER_DAY', Config.MAX_REWARDED_UPLOADS_PER_DAY)
                reward_amount = app.config.get('UPLOAD_REWARD', Config.UPLOAD_REWARD)

                rewarded_today = cursor.execute(
                    """
                    SELECT COUNT(*) FROM ledger
                    WHERE user_id = ? AND reason = 'upload' AND amount > 0
                    AND date(created_at) = date('now')
                    """,
                    (g.user['id'],)
                ).fetchone()[0]

                if rewarded_today < max_rewarded:
                    earned = reward_amount
                    cursor.execute("UPDATE users SET credits = credits + ? WHERE id = ?", (earned, g.user['id']))
                    msg = f"Material uploaded successfully! You earned {earned} credits."
                else:
                    earned = 0
                    msg = f"Material uploaded successfully! (Daily reward limit of {max_rewarded} reached; 0 credits earned)."

                # Always write ledger row
                cursor.execute(
                    """
                    INSERT INTO ledger (user_id, amount, reason, file_id)
                    VALUES (?, ?, 'upload', ?)
                    """,
                    (g.user['id'], earned, file_id)
                )

                db.commit()
                flash(msg, "success")
                return redirect(url_for('file_detail', file_id=file_id))
            except Exception as e:
                db.rollback()
                if os.path.exists(stored_path):
                    os.remove(stored_path)
                flash("Failed to save material due to a database error.", "danger")
                return render_template('upload.html')

        return render_template('upload.html')

    @app.route('/file/<int:file_id>')
    @login_required
    def file_detail(file_id):
        """
        File details page:
        - Strict isolation: verifies file belongs to logged-in user's university.
        - Shows ratings, reviews, uploader info, and download status.
        """
        db = get_db()
        file = db.execute(
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
            (file_id, g.user['university_id'])
        ).fetchone()

        if not file:
            abort(404, description="Material not found or access restricted to its institution.")

        # Determine download status
        is_uploader = (file['uploader_id'] == g.user['id'])
        already_downloaded = db.execute(
            "SELECT 1 FROM downloads WHERE user_id = ? AND file_id = ?",
            (g.user['id'], file_id)
        ).fetchone() is not None

        # Existing user rating
        user_rating = db.execute(
            "SELECT stars FROM ratings WHERE user_id = ? AND file_id = ?",
            (g.user['id'], file_id)
        ).fetchone()

        return render_template(
            'file_detail.html',
            file=file,
            is_uploader=is_uploader,
            already_downloaded=already_downloaded,
            user_stars=user_rating['stars'] if user_rating else None
        )

    @app.route('/file/<int:file_id>/rate', methods=['POST'])
    @login_required
    def rate_file(file_id):
        """Submit or update a 1-5 star rating for an institution file."""
        db = get_db()
        # Verify file belongs to user's university
        file = db.execute(
            "SELECT id FROM files WHERE id = ? AND university_id = ? AND status = 'active'",
            (file_id, g.user['university_id'])
        ).fetchone()

        if not file:
            abort(404, description="Material not found or access restricted.")

        stars = request.form.get('stars', type=int)
        if not stars or not (1 <= stars <= 5):
            flash("Please choose a rating between 1 and 5 stars.", "warning")
            return redirect(url_for('file_detail', file_id=file_id))

        db.execute(
            """
            INSERT INTO ratings (user_id, file_id, stars)
            VALUES (?, ?, ?)
            ON CONFLICT(user_id, file_id) DO UPDATE SET stars = excluded.stars
            """,
            (g.user['id'], file_id, stars)
        )
        db.commit()
        flash(f"Thank you! You rated this material {stars} star{'s' if stars > 1 else ''}.", "success")
        return redirect(url_for('file_detail', file_id=file_id))

    @app.route('/file/<int:file_id>/report', methods=['POST'])
    @login_required
    def report_file(file_id):
        """Submit a copyright or inappropriate content report for administrator review."""
        db = get_db()
        file = db.execute(
            "SELECT id FROM files WHERE id = ? AND university_id = ? AND status = 'active'",
            (file_id, g.user['university_id'])
        ).fetchone()

        if not file:
            abort(404, description="Material not found or access restricted.")

        reason = request.form.get('reason', '').strip()
        if not reason:
            flash("Please provide a reason for reporting this file.", "warning")
            return redirect(url_for('file_detail', file_id=file_id))

        db.execute(
            """
            INSERT INTO reports (user_id, file_id, reason, status)
            VALUES (?, ?, ?, 'open')
            """,
            (g.user['id'], file_id, reason)
        )
        db.commit()
        flash("Your report has been received and will be reviewed by university administrators.", "info")
        return redirect(url_for('file_detail', file_id=file_id))

    @app.route('/download/<int:file_id>')
    @login_required
    def download_file(file_id):
        """
        Secure file download:
        - CRITICAL: Returns 404 if file does not belong to logged-in user's university.
        - Free for uploader and re-downloads.
        - Deducts DOWNLOAD_COST (5 credits) via DB transaction so credits NEVER go negative.
        - Records download in downloads table.
        """
        db = get_db()

        # Strict university isolation query
        file = db.execute(
            "SELECT * FROM files WHERE id = ? AND university_id = ? AND status = 'active'",
            (file_id, g.user['university_id'])
        ).fetchone()

        if not file:
            # Material from other universities returns 404
            abort(404, description="Material not found or access restricted to students of its institution.")

        is_uploader = (file['uploader_id'] == g.user['id'])
        already_downloaded = db.execute(
            "SELECT 1 FROM downloads WHERE user_id = ? AND file_id = ?",
            (g.user['id'], file_id)
        ).fetchone() is not None

        cost = app.config.get('DOWNLOAD_COST', Config.DOWNLOAD_COST)

        # Atomic credit check & transaction
        cursor = db.cursor()
        try:
            cursor.execute("BEGIN IMMEDIATE")

            if not is_uploader and not already_downloaded:
                # Check credit balance
                user_record = cursor.execute(
                    "SELECT credits FROM users WHERE id = ?",
                    (g.user['id'],)
                ).fetchone()

                if not user_record or user_record['credits'] < cost:
                    db.rollback()
                    flash(
                        f"Insufficient credits! Downloading this document requires {cost} credits. "
                        f"Your current balance is {g.user['credits']}. Upload study materials to earn more.",
                        "danger"
                    )
                    return redirect(url_for('file_detail', file_id=file_id))

                # Deduct credits
                cursor.execute(
                    "UPDATE users SET credits = credits - ? WHERE id = ?",
                    (cost, g.user['id'])
                )
                # Write ledger row
                cursor.execute(
                    """
                    INSERT INTO ledger (user_id, amount, reason, file_id)
                    VALUES (?, ?, 'download', ?)
                    """,
                    (g.user['id'], -cost, file_id)
                )

            # Record download if not already recorded
            if not already_downloaded:
                cursor.execute(
                    "INSERT INTO downloads (user_id, file_id) VALUES (?, ?)",
                    (g.user['id'], file_id)
                )

            db.commit()
        except Exception as e:
            db.rollback()
            flash("An error occurred during download processing. Please try again.", "danger")
            return redirect(url_for('file_detail', file_id=file_id))

        upload_folder = app.config.get('UPLOAD_FOLDER', Config.UPLOAD_FOLDER)
        return send_from_directory(
            upload_folder,
            file['stored_name'],
            as_attachment=True,
            download_name=file['original_name']
        )

    # ---------------------------------------------------------
    # Dashboard & User Management
    # ---------------------------------------------------------
    @app.route('/dashboard')
    @login_required
    def dashboard():
        """User personal dashboard with credit balance, ledger history, uploads, and downloads."""
        db = get_db()
        user_id = g.user['id']

        # Ledger history
        ledger = db.execute(
            """
            SELECT l.*, f.title as file_title
            FROM ledger l
            LEFT JOIN files f ON l.file_id = f.id
            WHERE l.user_id = ?
            ORDER BY l.created_at DESC
            LIMIT 50
            """,
            (user_id,)
        ).fetchall()

        # My uploads
        uploads = db.execute(
            """
            SELECT f.*,
                   COALESCE(AVG(r.stars), 0.0) as avg_rating,
                   COUNT(DISTINCT r.id) as rating_count,
                   COUNT(DISTINCT d.id) as download_count
            FROM files f
            LEFT JOIN ratings r ON f.id = r.file_id
            LEFT JOIN downloads d ON f.id = d.file_id
            WHERE f.uploader_id = ?
            GROUP BY f.id
            ORDER BY f.created_at DESC
            """,
            (user_id,)
        ).fetchall()

        # My downloads
        downloads = db.execute(
            """
            SELECT d.created_at as downloaded_at, f.id as file_id, f.title, f.subject,
                   f.semester, f.type, f.size, f.status, u.username as uploader_username
            FROM downloads d
            JOIN files f ON d.file_id = f.id
            JOIN users u ON f.uploader_id = u.id
            WHERE d.user_id = ? AND f.university_id = ?
            ORDER BY d.created_at DESC
            """,
            (user_id, g.user['university_id'])
        ).fetchall()

        return render_template(
            'dashboard.html',
            ledger=ledger,
            uploads=uploads,
            downloads=downloads
        )

    # ---------------------------------------------------------
    # Administrator Routes
    # ---------------------------------------------------------
    @app.route('/admin')
    @admin_required
    def admin_panel():
        """
        Administrator overview:
        - Reports moderation.
        - System statistics.
        - Direct export triggers.
        """
        db = get_db()

        # System statistics
        stats = {
            'users_count': db.execute("SELECT COUNT(*) FROM users").fetchone()[0],
            'files_count': db.execute("SELECT COUNT(*) FROM files WHERE status = 'active'").fetchone()[0],
            'downloads_count': db.execute("SELECT COUNT(*) FROM downloads").fetchone()[0],
            'reports_count': db.execute("SELECT COUNT(*) FROM reports WHERE status = 'open'").fetchone()[0],
            'tasks_count': db.execute("SELECT COUNT(*) FROM tasks").fetchone()[0],
            'sus_count': db.execute("SELECT COUNT(*) FROM sus_responses").fetchone()[0]
        }

        # Open reports
        reports = db.execute(
            """
            SELECT r.*, f.title as file_title, f.status as file_status,
                   reporter.username as reporter_username,
                   uploader.username as uploader_username, uploader.id as uploader_id,
                   un.name as university_name
            FROM reports r
            JOIN files f ON r.file_id = f.id
            JOIN users reporter ON r.user_id = reporter.id
            JOIN users uploader ON f.uploader_id = uploader.id
            JOIN universities un ON f.university_id = un.id
            WHERE r.status = 'open'
            ORDER BY r.created_at DESC
            """
        ).fetchall()

        return render_template('admin.html', stats=stats, reports=reports)

    @app.route('/admin/report/<int:report_id>/resolve', methods=['POST'])
    @admin_required
    def resolve_report(report_id):
        """Mark an open report as resolved without modifying the file."""
        db = get_db()
        db.execute("UPDATE reports SET status = 'resolved' WHERE id = ?", (report_id,))
        db.commit()
        flash("Report resolved.", "success")
        return redirect(url_for('admin_panel'))

    @app.route('/admin/file/<int:file_id>/remove', methods=['POST'])
    @admin_required
    def remove_file_admin(file_id):
        """
        Takedown file:
        - Changes file status to 'removed'.
        - Reverses uploader reward via ledger 'reversal'.
        - Resolves all open reports for this file.
        """
        db = get_db()
        cursor = db.cursor()
        try:
            cursor.execute("BEGIN IMMEDIATE")
            file = cursor.execute("SELECT * FROM files WHERE id = ?", (file_id,)).fetchone()
            if not file:
                abort(404, description="File not found.")

            # Mark removed
            cursor.execute("UPDATE files SET status = 'removed' WHERE id = ?", (file_id,))

            # Find reward given to uploader for this file
            upload_ledger = cursor.execute(
                "SELECT amount FROM ledger WHERE file_id = ? AND user_id = ? AND reason = 'upload' AND amount > 0",
                (file_id, file['uploader_id'])
            ).fetchone()

            reversal_amount = upload_ledger['amount'] if upload_ledger else app.config.get('UPLOAD_REWARD', Config.UPLOAD_REWARD)

            # Deduct credits from uploader
            cursor.execute(
                "UPDATE users SET credits = MAX(0, credits - ?) WHERE id = ?",
                (reversal_amount, file['uploader_id'])
            )

            # Record reversal in ledger
            cursor.execute(
                """
                INSERT INTO ledger (user_id, amount, reason, file_id)
                VALUES (?, ?, 'reversal', ?)
                """,
                (file['uploader_id'], -reversal_amount, file_id)
            )

            # Mark related reports resolved
            cursor.execute("UPDATE reports SET status = 'resolved' WHERE file_id = ?", (file_id,))

            db.commit()
            flash(f"Material '{file['title']}' removed and {reversal_amount} credits reversed from uploader.", "success")
        except Exception as e:
            db.rollback()
            flash("Failed to remove material due to a database error.", "danger")

        return redirect(url_for('admin_panel'))

    @app.route('/admin/baseline', methods=['GET', 'POST'])
    @admin_required
    def admin_baseline():
        """Facilitator form to record baseline study tasks (e.g. WhatsApp/Google Drive)."""
        if request.method == 'POST':
            task_name = request.form.get('task_name', '').strip()
            duration_sec = request.form.get('duration_sec', type=float)
            clicks = request.form.get('clicks', 0, type=int)
            errors = request.form.get('errors', 0, type=int)
            success = 1 if request.form.get('success') == '1' else 0

            if not task_name or duration_sec is None or duration_sec < 0:
                flash("Please provide a valid task name and duration in seconds.", "danger")
                return render_template('admin_baseline.html')

            db = get_db()
            db.execute(
                """
                INSERT INTO tasks (user_id, task_name, method, duration_sec, clicks, errors, success, started_at, ended_at)
                VALUES (?, ?, 'baseline', ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """,
                (g.user['id'], task_name, duration_sec, clicks, errors, success)
            )
            db.commit()
            flash("Baseline measurement recorded successfully.", "success")
            return redirect(url_for('admin_baseline'))

        db = get_db()
        baselines = db.execute(
            "SELECT * FROM tasks WHERE method = 'baseline' ORDER BY id DESC LIMIT 30"
        ).fetchall()
        return render_template('admin_baseline.html', baselines=baselines)

    @app.route('/admin/export/<string:table_name>')
    @admin_required
    def admin_export_csv(table_name):
        """
        Export research datasets to CSV.
        Users table is strictly anonymized (no email, no password hash).
        """
        import csv
        import io

        allowed_tables = {
            'events': ('SELECT id, session_id, user_id, event_type, page, detail, ts FROM events',
                       ['id', 'session_id', 'user_id', 'event_type', 'page', 'detail', 'ts']),
            'tasks': ('SELECT id, user_id, task_name, method, started_at, ended_at, duration_sec, clicks, errors, success FROM tasks',
                      ['id', 'user_id', 'task_name', 'method', 'started_at', 'ended_at', 'duration_sec', 'clicks', 'errors', 'success']),
            'sus_responses': ('SELECT id, user_id, q1, q2, q3, q4, q5, q6, q7, q8, q9, q10, score, created_at FROM sus_responses',
                              ['id', 'user_id', 'q1', 'q2', 'q3', 'q4', 'q5', 'q6', 'q7', 'q8', 'q9', 'q10', 'score', 'created_at']),
            'feedback': ('SELECT id, user_id, text, usability_issue, created_at FROM feedback',
                         ['id', 'user_id', 'text', 'usability_issue', 'created_at']),
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

        if table_name not in allowed_tables:
            abort(404, description="Dataset not available for export.")

        query, headers = allowed_tables[table_name]
        db = get_db()
        rows = db.execute(query).fetchall()

        si = io.StringIO()
        cw = csv.writer(si)
        cw.writerow(headers)
        for row in rows:
            cw.writerow([row[col] for col in headers])

        output = make_response(si.getvalue())
        output.headers["Content-Disposition"] = f"attachment; filename=studyexchange_{table_name}.csv"
        output.headers["Content-type"] = "text/csv"
        return output

    # ---------------------------------------------------------
    # Usage Measurement & Evaluation Routes (Task, SUS, Feedback, API)
    # ---------------------------------------------------------
    @app.route('/api/me', methods=['GET'])
    def api_me():
        """Lightweight auth status check for clients and bfcache validation."""
        if not g.user:
            return jsonify({'authenticated': False}), 401
        return jsonify({
            'authenticated': True,
            'user': {
                'id': g.user['id'],
                'username': g.user['username'],
                'email': g.user['email'],
                'university_id': g.user['university_id'],
                'university_name': g.user['university_name'],
                'credits': g.user['credits'],
                'is_admin': bool(g.user['is_admin'])
            }
        }), 200

    @app.route('/api/domain-check', methods=['GET'])
    def api_domain_check():
        """
        Validate university institutional domain for registration.
        Returns university name if recognized, else 404 (never lists all domains).
        """
        email = request.args.get('email', '').strip().lower()
        if not email or '@' not in email:
            return jsonify({'valid': False, 'message': 'Invalid email format'}), 400

        domain = email.split('@')[-1]
        allowed_domains = app.config.get('ALLOWED_DOMAINS', {})
        if domain in allowed_domains:
            return jsonify({
                'valid': True,
                'domain': domain,
                'university_name': allowed_domains[domain]
            }), 200
        else:
            return jsonify({
                'valid': False,
                'message': 'This email domain is not supported yet'
            }), 404

    @app.route('/api/credits', methods=['GET'])
    def api_credits():
        """Return fresh credit balance for the authenticated user as JSON."""
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({'credits': 0, 'logged_in': False}), 200
        db = get_db()
        row = db.execute("SELECT credits FROM users WHERE id = ?", (user_id,)).fetchone()
        credits = row['credits'] if row else 0
        return jsonify({'credits': credits, 'logged_in': True}), 200

    @app.route('/api/event', methods=['POST'])
    def api_event():
        """Receive telemetry events from client-side JS (clicks, validation errors)."""
        data = request.get_json(silent=True) or {}
        event_type = data.get('event_type', 'unknown')
        page = data.get('page', request.referrer or '/')
        detail = data.get('detail', '')

        try:
            db = get_db()
            db.execute(
                """
                INSERT INTO events (session_id, user_id, event_type, page, detail)
                VALUES (?, ?, ?, ?, ?)
                """,
                (g.session_id, g.user['id'] if g.user else None, event_type, page, str(detail)[:500])
            )
            db.commit()
            return jsonify({'status': 'ok'}), 200
        except Exception as e:
            return jsonify({'status': 'error', 'message': str(e)}), 500

    @app.route('/task', methods=['GET'])
    @login_required
    def task_page():
        """
        Interactive Test Mode for HCI usability evaluation:
        Select a task, timer starts, clicks & errors are tracked, finish with success/failure.
        """
        db = get_db()
        my_tasks = db.execute(
            "SELECT * FROM tasks WHERE user_id = ? ORDER BY id DESC LIMIT 20",
            (g.user['id'],)
        ).fetchall()

        predefined_tasks = [
            {"id": 1, "name": "Find and download notes for Computer Networks, semester 4"},
            {"id": 2, "name": "Locate the highest rated study guide for Calculus"},
            {"id": 3, "name": "Upload study material for semester 3 and verify credit addition"},
            {"id": 4, "name": "Search for exam past papers and filter by semester"}
        ]

        return render_template('task.html', my_tasks=my_tasks, predefined_tasks=predefined_tasks)

    @app.route('/task/complete', methods=['POST'])
    @login_required
    def task_complete():
        """Record task evaluation metrics (method='prototype')."""
        task_name = request.form.get('task_name', '').strip()
        started_at = request.form.get('started_at')
        ended_at = request.form.get('ended_at')
        duration_sec = request.form.get('duration_sec', type=float) or 0.0
        clicks = request.form.get('clicks', 0, type=int)
        errors = request.form.get('errors', 0, type=int)
        success = 1 if request.form.get('success') in ['1', 'true', 'True'] else 0

        if not task_name:
            flash("Invalid task submission.", "danger")
            return redirect(url_for('task_page'))

        db = get_db()
        db.execute(
            """
            INSERT INTO tasks (user_id, task_name, method, started_at, ended_at, duration_sec, clicks, errors, success)
            VALUES (?, ?, 'prototype', ?, ?, ?, ?, ?, ?)
            """,
            (g.user['id'], task_name, started_at, ended_at, duration_sec, clicks, errors, success)
        )
        db.commit()

        if success:
            flash(f"Task '{task_name}' recorded as SUCCESS! Duration: {duration_sec}s, Clicks: {clicks}, Errors: {errors}.", "success")
        else:
            flash(f"Task '{task_name}' recorded as Abandoned. Telemetry saved for evaluation.", "warning")

        return redirect(url_for('task_page'))

    @app.route('/sus', methods=['GET', 'POST'])
    @login_required
    def sus_survey():
        """
        Standard 10-Item System Usability Scale (SUS):
        - Radios 1-5 for each question.
        - Calculates SUS score:
          Odd items: (item - 1)
          Even items: (5 - item)
          Score = Sum * 2.5
        """
        sus_items = [
            "I think that I would like to use this system frequently.",
            "I found the system unnecessarily complex.",
            "I thought the system was easy to use.",
            "I think that I would need the support of a technical person to be able to use this system.",
            "I found the various functions in this system were well integrated.",
            "I thought there was too much inconsistency in this system.",
            "I would imagine that most people would learn to use this system very quickly.",
            "I found the system very cumbersome to use.",
            "I felt very confident using the system.",
            "I needed to learn a lot of things before I could get going with this system."
        ]

        if request.method == 'POST':
            answers = []
            for i in range(1, 11):
                val = request.form.get(f'q{i}', type=int)
                if val is None or not (1 <= val <= 5):
                    flash(f"Please rate item {i} (value between 1 and 5).", "warning")
                    return render_template('sus.html', items=sus_items), 400
                answers.append(val)

            # Compute SUS score correctly:
            # odd (index 0, 2, 4, 6, 8): x - 1
            # even (index 1, 3, 5, 7, 9): 5 - x
            odd_sum = sum(answers[i] - 1 for i in [0, 2, 4, 6, 8])
            even_sum = sum(5 - answers[i] for i in [1, 3, 5, 7, 9])
            sus_score = (odd_sum + even_sum) * 2.5

            db = get_db()
            db.execute(
                """
                INSERT INTO sus_responses (user_id, q1, q2, q3, q4, q5, q6, q7, q8, q9, q10, score)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (g.user['id'], *answers, sus_score)
            )
            db.commit()

            flash("Thank you! Your System Usability Scale evaluation has been recorded.", "success")
            return redirect(url_for('sus_survey', submitted=1))

        submitted = bool(request.args.get('submitted'))
        return render_template('sus.html', items=sus_items, submitted=submitted)

    @app.route('/feedback', methods=['GET', 'POST'])
    @login_required
    def feedback_page():
        """User feedback form with text input and usability issue reporting."""
        if request.method == 'POST':
            text = request.form.get('text', '').strip()
            usability_issue = request.form.get('usability_issue', '').strip()

            if not text:
                flash("Please enter your feedback comments.", "warning")
                return render_template('feedback.html')

            db = get_db()
            db.execute(
                """
                INSERT INTO feedback (user_id, text, usability_issue)
                VALUES (?, ?, ?)
                """,
                (g.user['id'], text, usability_issue if usability_issue else None)
            )
            db.commit()
            flash("Thank you for your valuable feedback! It will help improve StudyExchange.", "success")
            return redirect(url_for('browse'))

        return render_template('feedback.html')

    @app.route('/terms')
    def terms_page():
        """Terms of Service, Copyright Ownership Policy, and Takedown Procedures."""
        return render_template('terms.html')

    # ---------------------------------------------------------
    # Error Handlers
    # ---------------------------------------------------------
    @app.errorhandler(400)
    def bad_request(error):
        return render_template('404.html', error_title="400 - Bad Request", error_message=getattr(error, 'description', "Bad request.")), 400

    @app.errorhandler(403)
    def forbidden(error):
        return render_template('404.html', error_title="403 - Forbidden", error_message=getattr(error, 'description', "Access forbidden.")), 403

    @app.errorhandler(404)
    def page_not_found(error):
        return render_template('404.html', error_title="404 - Not Found", error_message=getattr(error, 'description', "The requested page or material could not be found.")), 404

    @app.errorhandler(500)
    def server_error(error):
        return render_template('500.html'), 500

    return app

# Application entry point for single-command run: python app.py
if __name__ == '__main__':
    application = create_app()
    # Runs locally on port 5000
    print("==================================================")
    print(" StudyExchange Prototype Server Starting")
    print(" Access: http://127.0.0.1:5000")
    print(" Database automatically initialized.")
    print("==================================================")
    application.run(host='127.0.0.1', port=5000, debug=True)
