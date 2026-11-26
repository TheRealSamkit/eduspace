# EduSpace - Peer-to-Peer Academic Resource Sharing Platform

> **AI Tools Disclosure**: Built with the help of an AI coding agent.

EduSpace is a university-confined web platform where students within the **same university** create accounts, upload verified study material, and earn platform credits to spend on downloading other students' material.

A fundamental design invariant of EduSpace is **strict institutional isolation**: students can only discover, search, view, rate, and download materials uploaded within their own university domain. Cross-institutional resource access is strictly blocked at the database and routing layer.

---

## Tech Stack

The technology stack was chosen strictly to prioritize rapid prototyping, zero-build simplicity, robust transaction safety, and native accessibility:

- **Backend**: **Python 3.10+ & Flask**
  - *Why Flask?* Minimalist, lightweight WSGI framework with zero boilerplate, allowing fine-grained control over request lifecycles, session cookies, database connections, and custom decorator guards.
- **Database**: **SQLite (`sqlite3` standard library module, no ORM)**
  - *Why SQLite without ORM?* Built directly into Python with zero external server dependencies. Direct parameterized SQL gives complete transparency over query isolation, index optimization, and atomic transactions (`BEGIN IMMEDIATE`) ensuring platform credit balances never go negative.
- **Templates**: **Jinja2**
  - *Why Jinja2?* Native integration with Flask for secure server-side HTML rendering, template inheritance (`base.html`), automatic escaping against XSS, and seamless context processor injection (e.g., CSRF tokens, current user).
- **Frontend CSS**: **Bootstrap 5.3.3 (via custom build and jsDelivr CDN)**
  - *Why Bootstrap?* Industry-standard responsive grid, accessible form components, was-validated validation styling, modals, badges, and dismissible alerts without requiring build tools or bundlers.
- **Icons**: **Tabler Icons (v3.19.0 webfont via jsDelivr CDN)**
  - *Why Tabler Icons?* Clean, modern SVG-based icon font rendered with semantic `<i class="ti ti-*"></i>` tags, providing icons for coins, files, ratings, dashboards, and shields.
- **Frontend Behavior**: **Vanilla JavaScript (ES6)** & **pdf.js (v3.11.174, Apache-2.0, vendored)**
  - *Why Vanilla JS + vendored pdf.js?* Zero npm dependencies and no build step. Handles client-side Bootstrap form validation, optimistic bookmark/interest toggles, document/image file viewer modals, live evaluation timers, debounced user click/error tracking to `/api/event`, and submit button spinners.

---

## Team File Ownership

To maintain strict architectural boundaries across the team, the codebase is partitioned into distinct ownership domains:

- **Frontend Team**:
  - `templates/` (All Jinja templates extending `templates/base.html`)
  - `static/` (CSS styling at `static/css/`, vanilla JS at `static/js/`)
- **Backend Team**:
  - `app.py` (Thin server runner script)
  - `EduSpace/` (Modular application package, blueprints, services, hooks, security)
  - `db.py` (SQLite connection lifecycle, automatic initialization)
  - `schema.sql` (Relational schema, foreign keys, table indexes)
  - `config.py` (Configuration constants, domain mappings, credit rewards)
- **Analysis & Quality Assurance Team**:
  - `analysis/` (CSV dataset export scripts and export folder)
  - `tests/` (Automated pytest test suite, route snapshot, route integrity tests)

### Ownership Rules
1. **Schema Guard**: Nobody modifies `schema.sql` without consulting and getting sign-off from the Backend owner.
2. **Layout Consistency**: All templates must extend `templates/base.html`.
3. **CDN Link Invariant**: CDN links for Bootstrap CSS, JS bundle, and Tabler Icons webfont live **ONLY** in `templates/base.html`. No template or partial may re-import CDN assets.

---

## File Structure

```text
studyVerse/
├── app.py                             # Thin runner entry point (create_app, runs local server)
├── db.py                              # Database connection manager and initialization
├── schema.sql                         # SQLite schema definition and indexes
├── seed.py                            # Seed script populating demo unis, users, and dummy files
├── config.py                          # Platform parameters (rewards, limits, domains)
├── requirements.txt                   # Python dependencies (flask, werkzeug, pytest)
├── README.md                          # Project documentation and architecture guide
├── EduSpace/                     # Core application package
│   ├── __init__.py                    # create_app factory: config, init_app, hooks, blueprints
│   ├── hooks.py                       # Context processors, before_request, after_request headers
│   ├── security.py                    # CSRF helpers, login_required, admin_required decorators
│   ├── blueprints/                    # Modular route handlers
│   │   ├── pages.py                   # /, /terms, /favicon.ico
│   │   ├── auth.py                    # /register, /login, /logout, /consent
│   │   ├── library.py                 # /browse, /file/<id>, rate, report, /download/<id>
│   │   ├── upload.py                  # /upload
│   │   ├── dashboard.py               # /dashboard
│   │   ├── admin.py                   # /admin, report resolve, takedown, baseline, CSV export
│   │   ├── research.py                # /task, /task/complete, /sus, /feedback
│   │   ├── api.py                     # /api/me, /api/domain-check, /api/credits, /api/event
│   │   └── errors.py                  # HTTP 400, 403, 404, 500 error handlers
│   └── services/                      # Decoupled business logic (no Flask request/response)
│       ├── credits.py                 # Ledger writes, upload rewards, atomic download charges, reversals
│       ├── files.py                   # Upload validation, saving, browse querying with isolation, takedowns
│       ├── telemetry.py               # Event logging, task evaluation metrics, user feedback
│       ├── sus.py                     # 10-item System Usability Scale calculations and validation
│       └── exports.py                 # CSV dataset schemas and anonymized data querying
├── static/
│   ├── css/
│   │   ├── bootstrap.css              # Custom compiled Bootstrap 5.3 build
│   │   └── custom.css                 # Brand styling, toast layout, elevations
│   └── js/
│       ├── main.js                    # Telemetry logging, test mode tracker, form validation
│       ├── toast.js                   # Client-side toast notification manager
│       └── shortcuts.js               # Keyboard shortcuts handler and help modal
├── templates/
│   ├── base.html                      # Master layout with left sidebar, slim topbar, toasts container
│   ├── _components.html               # Reusable UI macros (page_header, stat_card, empty_state, file_card)
│   ├── index.html                     # Landing page for prospective students
│   ├── register.html                  # Institutional registration form
│   ├── login.html                     # Sign in form
│   ├── consent.html                   # Academic research ethics consent page
│   ├── browse.html                    # Resource repository with search, filters, and pagination
│   ├── upload.html                    # Single-card two-column file upload form
│   ├── file_detail.html               # Resource detail, star rating widget, and report modal
│   ├── dashboard.html                 # Credit balance, ledger history, my uploads & downloads
│   ├── admin.html                     # Moderation panel, stats cards, and CSV export buttons
│   ├── admin_baseline.html            # Facilitator entry form for baseline control data
│   ├── task.html                      # HCI Test Mode evaluation interface (timed tasks)
│   ├── sus.html                       # Stepped 10-item System Usability Scale (SUS) survey
│   ├── feedback.html                  # Qualitative user feedback and usability issue reporting
│   ├── terms.html                     # Terms of service, copyright policy, and takedown policy
│   ├── 404.html                       # Friendly 404 / 403 error page
│   └── 500.html                       # Friendly 500 server error page
├── uploads/                           # Local storage for uploaded files (randomized filenames)
├── screenshots/                       # Visual validation captures at 1440px and 390px (light/dark)
├── analysis/
│   ├── export_data.py                 # Standalone CSV export script
│   └── exports/                       # Output folder for exported CSV research datasets
└── tests/
    ├── test_app.py                    # Core tests (isolation, auth, credits, moderation)
    ├── test_routes.py                 # Route smoke tests iterating app.url_map under 4 contexts
    ├── test_flows.py                  # End-to-end integration flows and input validation
    ├── test_phase1_improvements.py    # Phase 1 UI and architecture test suite
    ├── test_route_integrity.py        # Route snapshot comparison and url_for endpoint scanner
    └── route_snapshot.json            # Baseline route table snapshot
```

---

## What Each Module Does

### Blueprints (`EduSpace/blueprints/`)
- **`pages.py`**: Public landing page (`/`), legal and copyright terms (`/terms`), and silent favicon handler (`/favicon.ico`).
- **`auth.py`**: User authentication lifecycles including institutional domain-checked registration (`/register`), login (`/login`), logout (`/logout`), and research ethics consent (`/consent`).
- **`library.py`**: Core student study material workflows: browsing with search/filters (`/browse`), material details (`/file/<id>`), 1–5 star ratings (`/file/<id>/rate`), content infringement reporting (`/file/<id>/report`), and credit-deducted file downloads (`/download/<id>`).
- **`upload.py`**: Material submission (`/upload`), input validation, and daily upload credit rewarding.
- **`dashboard.py`**: Personal account overview (`/dashboard`) showing real-time credits, transaction history, active uploads, and previous downloads.
- **`admin.py`**: Administrator moderation console (`/admin`), open report dismissal (`/admin/report/<id>/resolve`), material removal with credit reversal (`/admin/file/<id>/remove`), facilitator baseline data recording (`/admin/baseline`), and CSV exports (`/admin/export/<table>`).
- **`research.py`**: Usability evaluation tools: interactive test mode runner (`/task`), task completion telemetry (`/task/complete`), 10-item System Usability Scale survey (`/sus`), and qualitative feedback submission (`/feedback`).
- **`api.py`**: JSON endpoints supporting dynamic client UI: auth status check (`/api/me`), real-time domain verification (`/api/domain-check`), live credit sync (`/api/credits`), and telemetry event logging (`/api/event`).
- **`errors.py`**: Custom HTTP error handling rendering styled 400, 403, 404, and 500 error templates.

### Services (`EduSpace/services/`)
- **`credits.py`**: Manages all credit transactions and ledger writes. Enforces the daily upload reward cap (`MAX_REWARDED_UPLOADS_PER_DAY`), performs atomic credit checks and deductions in a `BEGIN IMMEDIATE` transaction during downloads, and handles reward reversals upon moderation removal.
- **`files.py`**: Handles upload metadata validation, disk persistence with randomized filenames, browse queries with strict `university_id` isolation, rating/report persistence, and content takedown.
- **`telemetry.py`**: Persistence helpers for client-side events, prototype task metrics, and qualitative usability feedback.
- **`sus.py`**: System Usability Scale utilities: item definition, 1–5 range validation, Brooke (1996) formula score calculation, and database persistence.
- **`exports.py`**: CSV export table definitions and data retrieval with strict anonymization rules (excluding student emails and password hashes).

---

## How to Add a New Route

To add a new route while preserving modular separation and testing invariants:

1. **Implement Business Logic (Service)**:
   Add any non-trivial database operations or domain logic to the relevant service module in `EduSpace/services/` (e.g. `files.py`, `credits.py`, or `telemetry.py`). Keep service functions decoupled from Flask request and response objects.

2. **Add View Function to Blueprint**:
   Locate or create the appropriate blueprint in `EduSpace/blueprints/`:
   ```python
   from flask import Blueprint, render_template, request, redirect, url_for, flash
   from EduSpace.security import login_required

   @bp.route('/my-route', methods=['GET', 'POST'])
   @login_required
   def my_view():
       # Handle request, call service function, return response
       return render_template('my_template.html')
   ```

3. **Register Blueprint (if new)**:
   If you created a new blueprint, register it inside `EduSpace/__init__.py`:
   ```python
   from EduSpace.blueprints.my_module import bp as my_bp
   app.register_blueprint(my_bp)
   ```

4. **Reference via Namespaced `url_for`**:
   In templates, redirects, and tests, always reference the route with its blueprint prefix:
   ```jinja2
   <a href="{{ url_for('my_bp.my_view') }}">Go to My View</a>
   ```

5. **Verify with Tests**:
   Run `pytest` to automatically verify that the route appears in the url map and that all `url_for` references in templates match registered endpoints:
   ```bash
   pytest tests/test_route_integrity.py
   ```

---

## Database Diagram (Text-based ERD)

```text
+-----------------------+         +-------------------------------------+
|     universities      |         |                users                |
+-----------------------+         +-------------------------------------+
| id (PK)               |<---+    | id (PK)                             |<---------+
| name                  |    +----| university_id (FK -> universities)   |          |
| domain (UNIQUE)       |         | email (UNIQUE)                      |          |
+-----------------------+         | username (UNIQUE)                   |          |
                                  | password_hash                       |          |
                                  | credits                             |          |
                                  | is_admin                            |          |
                                  | created_at                          |          |
                                  +-------------------------------------+          |
                                             |                 |                   |
               +-----------------------------+                 |                   |
               |                             |                 |                   |
               v                             v                 v                   v
+-------------------------------+  +-------------------+  +-------------------+  +---------------------+
|             files             |  |      ledger       |  |     downloads     |  |       ratings       |
+-------------------------------+  +-------------------+  +-------------------+  +---------------------+
| id (PK)                       |  | id (PK)           |  | id (PK)           |  | id (PK)             |
| uploader_id (FK -> users)     |  | user_id (FK)      |  | user_id (FK)      |  | user_id (FK)        |
| university_id (FK -> unis)    |  | amount            |  | file_id (FK)      |  | file_id (FK)        |
| title, subject, semester      |  | reason            |  | created_at        |  | stars (1-5)         |
| type, description             |  |   ('signup',      |  +-------------------+  | UNIQUE(user, file)  |
| stored_name, original_name    |  |    'upload',      |                         +---------------------+
| size, status ('active',       |  |    'download',    |
|               'removed')      |  |    'reversal')    |
| created_at                    |  | file_id (FK)      |
+-------------------------------+  | created_at        |
               |                   +-------------------+
               v
+-------------------------------+  +-------------------------------------------------------------------+
|            reports            |  |                         Research Tables                           |
+-------------------------------+  +-------------------------------------------------------------------+
| id (PK)                       |  | consents     (id, user_id, agreed_at)                             |
| user_id (FK -> users)         |  | events       (id, session_id, user_id, event_type, page, detail)  |
| file_id (FK -> files)         |  | tasks        (id, user_id, task_name, method, duration, clicks)  |
| reason                        |  | sus_responses(id, user_id, q1..q10, score, created_at)            |
| status ('open', 'resolved')   |  | feedback     (id, user_id, text, usability_issue, created_at)     |
| created_at                    |  +-------------------------------------------------------------------+
+-------------------------------+
```

---

## Keyboard Shortcuts & Accessibility

EduSpace provides full keyboard navigation via a single source of truth defined in `static/js/shortcuts.js`:

| Key Sequence | Action | Group | Notes |
|:---|:---|:---|:---|
| <kbd>G</kbd> then <kbd>B</kbd> | Navigate to Browse | Navigation | 1.5s sequence window with hint pill (partner students) |
| <kbd>G</kbd> then <kbd>P</kbd> | Navigate to Public Library | Navigation | |
| <kbd>G</kbd> then <kbd>V</kbd> | Navigate to Saved | Navigation | |
| <kbd>G</kbd> then <kbd>R</kbd> | Navigate to Resource Requests | Navigation | |
| <kbd>G</kbd> then <kbd>U</kbd> | Navigate to Upload | Navigation | |
| <kbd>G</kbd> then <kbd>D</kbd> | Navigate to Dashboard | Navigation | |
| <kbd>G</kbd> then <kbd>T</kbd> | Navigate to Test Mode | Navigation | |
| <kbd>G</kbd> then <kbd>S</kbd> | Navigate to SUS Survey | Navigation | |
| <kbd>G</kbd> then <kbd>F</kbd> | Navigate to Usability Feedback | Navigation | |
| <kbd>G</kbd> then <kbd>A</kbd> | Navigate to Admin Panel | Navigation | Visible & active for admins only |
| <kbd>G</kbd> then <kbd>L</kbd> | Navigate to Baseline Data | Navigation | Visible & active for admins only |
| <kbd>T</kbd> | Toggle light / dark theme | Interface | Instant client-side toggle |
| <kbd>/</kbd> | Focus Search field | Interface | Available on Browse page |
| <kbd>?</kbd> | Keyboard shortcuts modal | Interface | Accessible dialog with Esc dismissal |
| <kbd>Esc</kbd> | Close dialog / dismiss toast | Interface | Restores focus to previous active element |

### Research Safety Rules
- **Test Mode Gating**: To preserve research validity, all navigation shortcuts and `/` are automatically disabled while an evaluation task is running. Pressing a navigation shortcut during a task displays a non-blocking warning toast (`"Keyboard shortcuts are disabled during test tasks."`) and does not inflate task click counts.
- **Form Input Safety**: Shortcuts never fire when focus is inside text inputs, textareas, selects, or `contenteditable` elements.
- **Modifier Isolation**: Key events with `Ctrl`, `Alt`, or `Meta` modifiers are ignored to avoid interfering with browser defaults.
- **Accessible Tooltips**: Navigation items and icon-only buttons display Bootstrap tooltips on hover and keyboard focus. Tooltips are initialized only on hover-capable devices (`@media (hover: hover)`) to prevent sticky tooltips on mobile touchscreens.

---

## Setup & Running the Application

### 1. Requirements & Dependencies
Ensure Python 3.10 or later is installed. Install dependencies:
```bash
pip install -r requirements.txt
```
*(Dependencies: `flask`, `werkzeug`, `pytest`)*

### 2. Single Command to Run
```bash
python app.py
```
- The application automatically initializes `eduspace.db` with the schema on its first run if the database file is not present.
- The server starts at: **`http://127.0.0.1:5000`**

### 3. Seed Demo Data (Recommended)
To populate demo universities, 6 demo students, 12 dummy PDF files, ratings, and usage telemetry:
```bash
python seed.py
```

---

## Demo Accounts

All demo accounts come pre-configured with completed research consent:

| Role | University | Institutional Email | Password | Username | Starting Credits |
|---|---|---|---|---|---|
| **Administrator** | XYZ University | `admin@xyz.edu` | `admin123` | `admin_xyz` | 50 |
| **Student** | XYZ University | `alice@xyz.edu` | `demo1234` | `alice_w` | 35 |
| **Student** | XYZ University | `bob@xyz.edu` | `demo1234` | `bob_m` | 20 |
| **Student** | XYZ University | `carol@xyz.edu` | `demo1234` | `carol_k` | 15 |
| **Student** | ABC College | `david@abc.edu` | `demo1234` | `david_r` | 40 |
| **Student** | ABC College | `emma@abc.edu` | `demo1234` | `emma_t` | 25 |

> **Privacy Invariant**: Public file listings, reviews, and details display **usernames only**. Student emails are never shown.

---

## Key Feature Implementation

### 1. University Isolation (Strict Segregation)
- Every query on `/browse`, `/file/<id>`, `/download/<id>`, `/file/<id>/rate`, and `/file/<id>/report` enforces `university_id = g.user['university_id']`.
- Direct URL requests to `/download/<id>` or `/file/<id>` belonging to another university immediately return an HTTP **404 Not Found** response to prevent cross-institution enumeration.
- Proven with automated isolation tests in `tests/test_app.py`.

### 2. Credit Economy & Atomic Transactions
- **Signup Bonus**: New registered users receive **+20 credits** recorded in the ledger (`reason='signup'`).
- **Upload Reward**: Users receive **+10 credits** for quality uploads (`reason='upload'`). To avoid spamming, a daily cap of **3 rewarded uploads per day** (`MAX_REWARDED_UPLOADS_PER_DAY`) is enforced; uploads beyond the cap still succeed and are logged in the ledger with `amount=0`.
- **Download Cost**: Downloading another student's file deducts **5 credits** (`DOWNLOAD_COST`, `reason='download'`).
- **Atomic Balance Safety**: Uses SQLite transactions (`BEGIN IMMEDIATE`) verifying credits prior to deduction. Credits **never go negative**; users with insufficient credits are blocked with an informative alert directing them to upload material.
- **Fair Use**: Downloading your own uploaded material is free; re-downloading previously purchased material is free.

### 3. Content Moderation & Takedown
- Users can flag material for copyright infringement or inappropriate content using the modal report dialog.
- Administrators reviewing reports on `/admin` can resolve reports or click **Remove & Reverse**. Removing a file sets `status='removed'`, automatically resolves associated reports, and writes a ledger entry (`reason='reversal'`) deducting the upload reward from the uploader.

### 4. HCI Usage Measurement & Telemetry
- **Session Tracking**: A `study_session_id` cookie tracks sessions; server-side page views are logged to the `events` table.
- **Client-Side Telemetry**: JavaScript tracks button clicks and form validation errors (`invalid` event) and posts them to `/api/event`.
- **Interactive Test Mode (`/task`)**: Users select an evaluation task and click **Start Task**. A live timer runs with click and error counters that persist across site navigation via a sticky banner. Upon clicking **I Found It** or **Give Up**, the telemetry is recorded in `tasks` with `method='prototype'`.
- **Baseline Entry (`/admin/baseline`)**: Facilitators manually record control condition trial results (e.g. finding notes via WhatsApp or Google Drive) with `method='baseline'`.
- **System Usability Scale (`/sus`)**: The standard 10-item SUS instrument using 1–5 Likert scales. Scores are computed using the verified SUS formula:
  $$\text{Odd contributions} = \sum (x_i - 1), \quad \text{Even contributions} = \sum (5 - x_i)$$
  $$\text{SUS Score} = (\text{Odd} + \text{Even}) \times 2.5 \quad [0 \dots 100]$$

---

## How to Export Research Data

### Method 1: Web Interface (Administrators Only)
Log in as `admin@xyz.edu` (`admin123`) and navigate to `/admin`. Under **Research Data Export Center**, click any button to trigger instant CSV downloads:
- Events Telemetry CSV
- Tasks Performance CSV
- SUS Responses CSV
- Feedback CSV
- Anonymized Users CSV
- Files Metadata CSV
- Downloads CSV
- Credit Ledger CSV

### Method 2: Command Line Script
Run the standalone analysis export tool:
```bash
python analysis/export_data.py [optional_output_directory]
```
By default, this writes all 8 datasets to `analysis/exports/`.

> **Academic Ethics Guarantee**: Exported user records contain only `id`, `university_id`, `university_name`, `credits`, `is_admin`, and `created_at`. Student email addresses and password hashes are **strictly excluded**.

---

## Automated Test Suite

The test suite covers unit tests, security route smoke tests, and full end-to-end integration flows across five test modules:

```bash
pytest
```

1. **`tests/test_app.py`**:
   - `test_domain_restriction`: Permitted vs disallowed email domains.
   - `test_university_isolation_browse_and_download`: Cross-university browse filtering, search isolation, and 404 on direct download attempts.
   - `test_credit_economy_rules`: Signup bonus, daily upload reward caps, download deductions, no negative balances, and free re-downloads.
   - `test_admin_removal_and_reversal`: Content takedown and ledger reward reversal.
   - `test_sus_scoring`: 10-item SUS calculation accuracy across standard profiles.
   - `test_task_logging_and_csv_anonymization`: Prototype and baseline task logging and CSV anonymization verification.
   - `test_registration_atomic_success`: Atomic user + ledger signup bonus transaction with redirect to consent.
   - `test_credit_ui_fresh_rendered_html`: Verification of fresh credit balances rendered on credit actions.

2. **`tests/test_routes.py`**:
   - Iterates `app.url_map` across four security contexts (Anonymous, Student, Cross-University Student, Admin).
   - Guarantees zero 500 server errors across all routes.
   - Confirms proper authentication redirects (302), role-based forbidden blocks (403), and custom 404 error page responses.

3. **`tests/test_flows.py`**:
   - End-to-end user lifecycle: Registration -> Consent -> Upload (+10) -> Browse/Search/Filter/Sort -> Second user download (-5) -> Free re-download -> Rate -> Report -> Admin moderation takedown & reversal (-10) -> Test Mode task tracking -> SUS survey scoring -> Qualitative feedback -> Facilitator baseline metric entry -> Anonymized CSV dataset downloads.
   - Input validation & security: Oversized file rejection (>10MB), disallowed extensions (.exe, .sh), missing fields, duplicate email/username, password length requirements, SQL injection resilience in search/filters, XSS HTML escaping, and CSRF token enforcement.

4. **`tests/test_route_integrity.py`**:
   - Compares registered rules and methods against `tests/route_snapshot.json` to guarantee identical route URLs.
   - Scans all template HTML and static JavaScript files to ensure every `url_for` call references a valid registered endpoint.

5. **`tests/test_toasts.py`**:
   - Verifies Flask flash messages render as semantic Bootstrap toasts instead of inline alert banners.
   - Asserts correct semantic categories (`text-bg-success`, `text-bg-danger`, etc.) and eliminates legacy `.alert` markup.

6. **`tests/test_shortcuts.py`**:
   - Verifies `SHORTCUTS_DEF` data integrity, key uniqueness, and avoidance of numerical/Enter shortcuts.
   - Asserts role-aware presence of `data-shortcut` and `aria-keyshortcuts` attributes for students vs admins.

---

## Known Limitations

- **Email Verification**: In this prototype, email verification is performed via domain suffix checking (`@xyz.edu`, `@abc.edu`) rather than sending live SMTP verification emails.
- **Local File Storage**: Files are stored in the local `uploads/` directory with randomized UUID filenames. In a high-availability cloud deployment, this would be backed by an S3-compatible object store.
- **Single-Host SQLite**: SQLite is utilized for simplicity and zero-configuration prototyping; production scaling across concurrent multi-server nodes would utilize PostgreSQL with row-level security.

---

## Extended Features & Architecture (Phases 0–6)

### New Modules
- **`eduspace/services/visibility.py`**: Centralised access control (`can_view_file`, `file_visibility_where`, `can_view_request`, `request_visibility_where`, `is_public_member`).
- **`eduspace/services/preview.py`**: Unlock-gated file viewability helpers (`is_file_unlocked`, `get_unlocked_file_ids`, `get_view_kind`).
- **`eduspace/services/requests.py`**: Resource requests lifecycle (`create_request`, `query_requests`, `toggle_request_interest`, `submit_file_to_request`, `accept_submission`).
- **`eduspace/blueprints/public.py`**: Guest-accessible `/library` and `/library/<id>` routes.
- **`eduspace/blueprints/requests.py`**: `/requests`, `/requests/<id>`, `/api/requests/<id>/interest`, `/requests/<id>/submit`, `/requests/<id>/accept/<sub_id>`, `/requests/<id>/close`.
- **`static/js/preview.js`**: Accessible PDF (vendored `pdf.js`) and image viewer modal with fullscreen, zoom, and keyboard navigation.

### New Configuration Constants (`config.py`)
- `PUBLIC_EMAIL_DOMAIN = "eduspace.public"`, `PUBLIC_UNI_NAME = "EduSpace Public"`
- `PUBLIC_SIGNUP_BONUS = 10`, `PUBLIC_SIGNUPS_PER_HOUR_PER_IP = 5`
- `REPORTS_TO_AUTOHIDE = 3`
- `REQUEST_BASE_REWARD = 15`, `REQUEST_INTEREST_BONUS = 1`, `REQUEST_BONUS_CAP = 10`
- `MAX_OPEN_REQUESTS_PER_USER = 3`, `MAX_REQUEST_REWARDS_PER_DAY = 2`
- `LICENSE_CHOICES`: Own original work, CC BY 4.0, CC BY-SA 4.0, CC0, Public Domain.

### Visibility Model & Public Members
- **Private (`visibility='university'`)**: Visible only to logged-in partner-university students of the same `university_id`. Public-member accounts (`kind='public'`) can never see private files or private requests.
- **Public (`visibility='public'`)**: Listing and detail (`/library`, `/library/<id>`) are visible to guests and all users; viewing (`/view/<id>`), download, rating, reporting, and bookmarking require login.
- **Moderation (`status='hidden'`)**: Public files auto-hide after `REPORTS_TO_AUTOHIDE` distinct reporters; admins can restore or remove them.
- **Public Members & Anti-Abuse**: Students whose university isn't listed register via `/register/public` (username + password only, internal `username@eduspace.public` email never shown). Protected by a hidden honeypot field, per-IP hourly rate limit (`PUBLIC_SIGNUPS_PER_HOUR_PER_IP`), lower `PUBLIC_SIGNUP_BONUS` (10 vs 20), and licence requirement on public uploads.

### Duplicate Detection & Unlock-Gated Viewing
- **Deduplication**: Upload streams compute SHA-256 and check within the same `BEGIN IMMEDIATE` transaction (private uploads check same-university + public; public uploads check public only so cross-university private files never leak). Removed/hidden file hashes remain blocklisted. *Limitation*: only byte-identical files are detected; re-exported PDFs with different metadata/bytes are not matched.
- **Unlock-Gated Viewing**: Inline viewing (`/view/<id>`) is available only to the uploader, admins, or users who have unlocked/downloaded the file.

### Resource Request Economics & Inflation Risk
- **Reward Formula**: `REQUEST_BASE_REWARD + min(REQUEST_BONUS_CAP, interested_count * REQUEST_INTEREST_BONUS)`.
- **Minting & Inflation Risk**: Request rewards are platform-minted (no escrow is deducted from the requester), and requesters download submitted files free of charge. While `MAX_OPEN_REQUESTS_PER_USER` and `MAX_REQUEST_REWARDS_PER_DAY` bound abuse, minted rewards can increase total credit supply over time if many requests are fulfilled.

### Third-Party Credits & AI Disclosure
- **pdf.js (`pdfjs-dist` v3.11.174)**: Vendored under `static/vendor/pdfjs/`, licensed under **Apache-2.0**.
- **AI Tools Disclosure**: Initial prototype and Phases 0–7 extensions (visibility model, dedupe, bookmarks, file viewer modal, public library/members, resource requests, tests, and UI polish) were built with the assistance of an AI coding agent.
