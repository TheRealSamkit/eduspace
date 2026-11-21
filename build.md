You are building a complete, working web prototype for a university project. Build it fully, run it, test it, and fix bugs before finishing. Prioritise working features over polish. Do not ask me questions; make sensible choices and document them in the README.

# PROJECT
"StudyExchange": a platform where students of the SAME university create accounts, upload study material, and earn platform credits which they spend to download other students' material. Students must never see material from other universities.

# STACK (strict, do not add anything else)
- Backend: Python 3.10+, Flask, SQLite (sqlite3 module, no ORM), Jinja2 templates
- Frontend: Bootstrap 5.3.3 (CSS + JS bundle via jsDelivr CDN), Tabler Icons webfont via CDN, vanilla JavaScript for custom behaviour. No React/Vue/Tailwind, no npm, no build step.
- CDN links (put them ONLY in templates/base.html):
  - <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet">
  - <link href="https://cdn.jsdelivr.net/npm/@tabler/icons-webfont@3.19.0/dist/tabler-icons.min.css" rel="stylesheet">
  - <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/js/bootstrap.bundle.min.js"></script>
- Icons are used as <i class="ti ti-download"></i> (e.g. ti-upload, ti-download, ti-star, ti-star-filled, ti-search, ti-flag, ti-coin, ti-user, ti-logout, ti-dashboard, ti-shield-check, ti-file-text).
- Python dependencies only: flask, werkzeug, pytest. Provide requirements.txt.
- Single command to run: `python app.py` (auto-create DB on first run).

# FILE STRUCTURE
app.py, db.py, schema.sql, seed.py, config.py, requirements.txt, README.md
templates/ (base.html + one template per page; ALL pages extend base.html)
static/css/custom.css (small overrides only; Bootstrap does the heavy lifting), static/js/main.js
uploads/ (stored files, random filenames)
analysis/export_data.py (exports tables to CSV)
tests/test_app.py

# CONFIG (config.py)
- ALLOWED_DOMAINS = {"xyz.edu": "XYZ University", "abc.edu": "ABC College"} (editable; two demo unis to prove isolation)
- SIGNUP_BONUS=20, UPLOAD_REWARD=10, DOWNLOAD_COST=5, MAX_REWARDED_UPLOADS_PER_DAY=3
- MAX_FILE_MB=10, ALLOWED_EXT = pdf, pptx, docx, png, jpg
- SECRET_KEY, ADMIN_EMAIL

# DATABASE (schema.sql)
- universities(id, name, domain)
- users(id, email, username, password_hash, university_id, credits, is_admin, created_at). Public display uses username only, never email.
- files(id, uploader_id, university_id, title, subject, semester, type, description, stored_name, original_name, size, status('active'/'removed'), created_at)
- ledger(id, user_id, amount, reason('signup','upload','download','reversal'), file_id, created_at)
- downloads(id, user_id, file_id, created_at)
- ratings(id, user_id, file_id, stars, UNIQUE(user_id,file_id))
- reports(id, user_id, file_id, reason, status('open'/'resolved'), created_at)
- events(id, session_id, user_id, event_type, page, detail, ts)  -- usage logging
- tasks(id, user_id, task_name, method('prototype'/'baseline'), started_at, ended_at, duration_sec, clicks, errors, success)
- sus_responses(id, user_id, q1..q10 (1-5), score, created_at)
- feedback(id, user_id, text, usability_issue, created_at)
- consents(id, user_id, agreed_at)

# FEATURES AND ROUTES
1. Auth: /register, /login, /logout. Register only if the email domain is in ALLOWED_DOMAINS; derive university from domain; require username, password (min 8), terms checkbox. Hash with werkzeug. Give SIGNUP_BONUS and write a ledger row. Show a consent page (data used for academic research, anonymised) before first use; store in consents.
2. UNIVERSITY ISOLATION (critical): every query on files/search/download/rating/report MUST filter by the logged-in user's university_id. Direct access to /download/<id> of another university's file returns 404. Add a test proving this.
3. /upload: form with validation (type, size, extension, required fields, copyright checkbox: "I confirm I own this material or have the right to share it"). Save with random filename. Reward UPLOAD_REWARD credits only for the first MAX_REWARDED_UPLOADS_PER_DAY uploads per day; always write ledger.
4. / and /browse: list files of own university with search (title/subject), filters (subject, semester, type), sort (newest, top rated, most downloaded), pagination (Bootstrap pagination component). Show avg rating, uploader username, cost.
5. /file/<id>: details, rate 1-5, report button (Bootstrap modal), Download button showing cost. Download deducts DOWNLOAD_COST, blocked with a clear message if credits are insufficient; own uploads are free; re-downloading an already downloaded file is free. Use a DB transaction so credits never go negative.
6. /dashboard: credit balance, ledger history, my uploads, my downloads.
7. /admin (admin only): open reports, remove a file (status='removed', reverse the uploader's reward via ledger 'reversal'), stats cards (users, files, downloads), and buttons to download CSV of events, tasks, sus_responses, feedback, users (anonymised: no email or password, only user id and university).
8. USAGE MEASUREMENT (critical for statistics later):
   - A session_id cookie; log page views server-side in events.
   - JS logs click counts and form validation errors to POST /api/event.
   - /task page ("Test Mode"): user picks a task (e.g. "Find and download notes for <subject>, semester <n>"), clicks Start (timer begins, clicks/errors counted), clicks "I found it" or "Give up" -> store duration_sec, clicks, errors, success in tasks with method='prototype'. Also add /admin/baseline form where a facilitator manually enters baseline results (method='baseline', e.g. time taken via WhatsApp/Drive).
   - /sus: the standard 10-item System Usability Scale with 1-5 radio buttons; compute score correctly (odd items: x-1, even items: 5-x, sum*2.5) and store it.
   - /feedback: free text plus "usability issue" field.
9. /terms page: users must only upload material they have rights to; report button; admin takedown.

# UI REQUIREMENTS (Bootstrap 5 + Tabler Icons)
- Use Bootstrap components, do not hand-write what Bootstrap provides: navbar (collapsible, shows credit balance with ti-coin icon), container/grid (row/col-md-*), cards for files, forms with form-control/form-select/form-check and was-validated styling, alerts for flash messages (map Flask categories to alert-success/danger/warning/info), modal for report, badges for file type/semester, table for ledger and admin lists, pagination, buttons with icons, spinner on submit.
- Mobile first and responsive; consistent layout via base.html (navbar, flash messages block, footer with Terms link).
- Accessibility: labelled form fields (label for=), aria-labels on icon-only buttons, visible focus, good contrast, semantic HTML, alt text, aria-live on flash messages.
- Client-side (Bootstrap validation) plus server-side validation.
- Friendly empty states with an icon ("No files yet - upload the first one and earn 10 credits").
- custom.css only for small tweaks (brand colour via CSS variable, card hover). No other CSS framework.

# SECURITY / ROBUSTNESS
- CSRF-safe enough for a prototype (a simple token in forms), parameterised SQL only, secure_filename plus random names, file type/size checks, login_required and admin_required decorators, try/except with friendly 404/500 pages, never expose emails publicly.

# SEED (seed.py)
Create both universities, 6 demo users (4 in xyz.edu, 2 in abc.edu, one admin admin@xyz.edu / admin123, others password demo1234), 12 small dummy files (generate tiny valid PDFs), some ratings and ledger rows, so the app looks alive. Print the demo credentials.

# TESTING (do this before finishing)
- tests/test_app.py (pytest) covering: domain restriction, university isolation (user A cannot see/download a file from another university), credit rules (signup, reward cap, download cost, insufficient credits, no negative balance), SUS scoring, task logging.
- Run the app, run seed, run tests, fix failures.

# DELIVERABLES
- Working app, clear comments on every route and function.
- README.md with: setup, run, demo accounts, feature list, DB diagram (text), how to export data, known limitations, and these sections:
  * "Tech stack": Flask, SQLite, Bootstrap 5.3.3, Tabler Icons, vanilla JS, and why each was chosen.
  * "Team file ownership": Frontend = templates/*.html, static/css, static/js. Backend = app.py, db.py, schema.sql, config.py. Analysis = analysis/ and tests/. Rule: nobody edits schema.sql without telling the backend owner; all pages extend base.html; CDN links live only in base.html.
  * "AI tools disclosure: built with the help of an AI coding agent."
- At the end, give me a summary of what was built, what to run, and anything incomplete.

Work in phases: (1) schema + auth + isolation, (2) upload/browse/download/credits, (3) rating/report/admin, (4) measurement (events, task timer, SUS, feedback, CSV export), (5) UI polish, seed, tests, README. Verify each phase works before moving on.