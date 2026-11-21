# StudyExchange - Peer-to-Peer Academic Resource Sharing Platform

> **AI Tools Disclosure**: Built with the help of an AI coding agent.

StudyExchange is a university-confined web platform where students within the **same university** create accounts, upload verified study material, and earn platform credits to spend on downloading other students' material.

A fundamental design invariant of StudyExchange is **strict institutional isolation**: students can only discover, search, view, rate, and download materials uploaded within their own university domain. Cross-institutional resource access is strictly blocked at the database and routing layer.

---

## Tech Stack

The technology stack was chosen strictly to prioritize rapid prototyping, zero-build simplicity, robust transaction safety, and native accessibility:

- **Backend**: **Python 3.10+ & Flask**
  - *Why Flask?* Minimalist, lightweight WSGI framework with zero boilerplate, allowing fine-grained control over request lifecycles, session cookies, database connections, and custom decorator guards.
- **Database**: **SQLite (`sqlite3` standard library module, no ORM)**
  - *Why SQLite without ORM?* Built directly into Python with zero external server dependencies. Direct parameterized SQL gives complete transparency over query isolation, index optimization, and atomic transactions (`BEGIN IMMEDIATE`) ensuring platform credit balances never go negative.
- **Templates**: **Jinja2**
  - *Why Jinja2?* Native integration with Flask for secure server-side HTML rendering, template inheritance (`base.html`), automatic escaping against XSS, and seamless context processor injection (e.g., CSRF tokens, current user).
- **Frontend CSS**: **Bootstrap 5.3.3 (via jsDelivr CDN)**
  - *Why Bootstrap?* Industry-standard responsive grid, accessible form components, was-validated validation styling, modals, badges, and dismissible alerts without requiring build tools or bundlers.
- **Icons**: **Tabler Icons (v3.19.0 webfont via jsDelivr CDN)**
  - *Why Tabler Icons?* Clean, modern SVG-based icon font rendered with semantic `<i class="ti ti-*"></i>` tags, providing icons for coins, files, ratings, dashboards, and shields.
- **Frontend Behavior**: **Vanilla JavaScript (ES6)**
  - *Why Vanilla JS?* Zero npm dependencies and no build step. Handles client-side Bootstrap form validation, live evaluation timers, debounced user click/error tracking to `/api/event`, and submit button spinners.

---

## Team File Ownership

To maintain strict architectural boundaries across the team, the codebase is partitioned into distinct ownership domains:

- **Frontend Team**:
  - `templates/*.html` (All pages extending `templates/base.html`)
  - `static/css/custom.css` (Brand variables, elevation styles, star ratings)
  - `static/js/main.js` (Telemetry event logger, task timer tracker, validation)
- **Backend Team**:
  - `app.py` (Flask factory, application routes, authentication, transactions)
  - `db.py` (SQLite connection lifecycle, automatic initialization)
  - `schema.sql` (Relational schema, foreign keys, table indexes)
  - `config.py` (Configuration constants, domain mappings, credit rewards)
- **Analysis & Quality Assurance Team**:
  - `analysis/export_data.py` (CSV dataset export tool for research analytics)
  - `tests/test_app.py` (Automated pytest test suite)

### Ownership Rules
1. **Schema Guard**: Nobody modifies `schema.sql` without consulting and getting sign-off from the Backend owner.
2. **Layout Consistency**: All templates must extend `templates/base.html`.
3. **CDN Link Invariant**: CDN links for Bootstrap CSS, JS bundle, and Tabler Icons webfont live **ONLY** in `templates/base.html`. No template or partial may re-import CDN assets.

---

## File Structure

```text
studyVerse/
├── app.py                   # Flask application factory, routes, and error handlers
├── db.py                    # Database connection manager and initialization
├── schema.sql               # SQLite schema definition and indexes
├── seed.py                  # Seed script populating demo unis, users, and dummy files
├── config.py                # Platform parameters (rewards, limits, domains)
├── requirements.txt         # Python dependencies (flask, werkzeug, pytest)
├── README.md                # Project documentation and evaluation guide
├── static/
│   ├── css/
│   │   └── custom.css       # Brand styling and hover elevations
│   └── js/
│       └── main.js          # Telemetry logging, test mode tracker, validation
├── templates/
│   ├── base.html            # Master layout with left sidebar, slim topbar, and CDN links
│   ├── _components.html     # Reusable UI macros (page_header, stat_card, empty_state, file_card)
│   ├── index.html           # Landing page for prospective students
│   ├── register.html        # Institutional registration form
│   ├── login.html           # Sign in form
│   ├── consent.html         # Academic research ethics consent page
│   ├── browse.html          # Resource repository with search, filters, and pagination
│   ├── upload.html          # File upload form with copyright ownership checkbox
│   ├── file_detail.html     # Resource detail, star rating widget, and report modal
│   ├── dashboard.html       # Credit balance, ledger history, my uploads & downloads
│   ├── admin.html           # Moderation panel, stats cards, and CSV export buttons
│   ├── admin_baseline.html  # Facilitator entry form for baseline control data
│   ├── task.html            # HCI Test Mode evaluation interface (timed tasks)
│   ├── sus.html             # Stepped 10-item System Usability Scale (SUS) survey
│   ├── feedback.html        # Qualitative user feedback and usability issue reporting
│   ├── terms.html           # Terms of service, copyright policy, and takedown policy
│   ├── 404.html             # Friendly 404 / 403 error page
│   └── 500.html             # Friendly 500 server error page
├── uploads/                 # Local storage for uploaded files (randomized filenames)
├── screenshots/             # Visual validation captures at 1440px and 390px (light/dark)
├── analysis/
│   ├── export_data.py       # Standalone CSV export script
│   └── exports/             # Output folder for exported CSV research datasets
└── tests/
    ├── test_app.py          # Core tests (isolation, auth, credits, moderation)
    ├── test_routes.py       # Route smoke tests iterating app.url_map under 4 contexts
    └── test_flows.py        # End-to-end integration flows and input validation
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
- The application automatically initializes `study_exchange.db` with the schema on its first run if the database file is not present.
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

The test suite covers unit tests, security route smoke tests, and full end-to-end integration flows across three test modules:

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
   - End-to-end user lifecycle: Registration -> Consent -> Upload (+10) -> Browse/Search/Filter/Sort -> Second user download (-5) -> Free re-download -> Rate -> Report -> Admin moderation takedown & reversal (-10) -> Test Mode task tracking -> SUS survey scoring (Odd=5/Even=1 -> 100, All 3s -> 50) -> Qualitative feedback -> Facilitator baseline metric entry -> Anonymized CSV dataset downloads.
   - Input validation & security: Oversized file rejection (>10MB), disallowed extensions (.exe, .sh), missing fields, duplicate email/username, password length requirements, SQL injection resilience in search/filters, XSS HTML escaping, and CSRF token enforcement.

---

## Known Limitations

- **Email Verification**: In this prototype, email verification is performed via domain suffix checking (`@xyz.edu`, `@abc.edu`) rather than sending live SMTP verification emails.
- **Local File Storage**: Files are stored in the local `uploads/` directory with randomized UUID filenames. In a high-availability cloud deployment, this would be backed by an S3-compatible object store.
- **Single-Host SQLite**: SQLite is utilized for simplicity and zero-configuration prototyping; production scaling across concurrent multi-server nodes would utilize PostgreSQL with row-level security.
