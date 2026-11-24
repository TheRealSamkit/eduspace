# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users
- Primary: College and university students looking to discover, share, and access study materials (lecture notes, exam papers, lab reports, assignments, presentation slides) specifically within their own college or university.
- Secondary: Student group project evaluators and academic moderators managing file verification, student reports, content takedowns, and usability assessment.

## Product Purpose
EduSpace is a student-focused academic hub that enables college students to share and access verified study resources exclusively within their own institution. It solves study material fragmentation and academic isolation by fostering a campus-specific peer economy where students earn credits by contributing materials to download resources shared by classmates.

## Positioning
- Strict institutional domain isolation: resource discovery, search, viewing, rating, and downloading are strictly constrained to the student's authenticated university domain (cross-institutional access is blocked at the routing and database layer).
- Contribution-driven credit economy: balances peer contribution and consumption via an atomic transaction ledger (`BEGIN IMMEDIATE`), ensuring balances never drop below zero and rewarding active campus contributors.
- Embedded HCI research & usability evaluation: integrated System Usability Scale (SUS) survey, timed evaluation tasks, and client-side telemetry tracking.

## Operating Context
- Context: Student group academic project and campus sharing hub.
- Environment: Web application accessed across modern desktop and mobile browsers.
- Workflows: Institutional registration with university email domain verification, file upload with daily reward limits, faceted library search/browse, star ratings, content infringement reporting, credit ledger tracking, and administrative moderation.

## Capabilities and Constraints
- Tech Stack: Python 3.10+ with Flask (server-rendered Jinja2 templates extending `templates/base.html`), SQLite via standard library (`sqlite3`, direct SQL, no ORM), custom Bootstrap 5.3.3 and Tabler Icons v3.19 via CDN, Vanilla JavaScript (zero npm build dependencies).
- Institutional Email Domains: Pre-configured mappings (`xyz.edu`, `abc.edu`, `jg.edu.in`, `lj.edu.in`, `gtu.ac.in`).
- Credit Economy Rules: 20-credit signup bonus, 10 credits awarded per valid upload (capped at 3 rewarded uploads per day), 5 credits deducted per download; rewards reversed on administrative takedown.
- File Constraints: 10 MB maximum file size; allowed formats: `.pdf`, `.pptx`, `.docx`, `.png`, `.jpg`.
- Architectural Guardrails: Strict ownership boundaries—schema changes require backend sign-off; all templates inherit `base.html`; CDN asset imports stay exclusively in `base.html`.

## Brand Commitments
- Name: EduSpace
- Voice: Clear, encouraging, academic, trustworthy, and student-centric.
- Visual Constraints: Modern, uncluttered campus productivity interface; responsive down to mobile viewports (390px).

## Evidence on Hand
- Working Flask application with end-to-end route handlers in `eduspace/blueprints/` and decoupled business logic in `eduspace/services/`.
- Full relational SQLite schema (`schema.sql`) and sample institutional seed data (`seed.py`).
- Automated pytest test suite (`tests/`) covering isolation, authentication, credits, moderation, and route integrity.
- Visual regression snapshots in `screenshots/` (1440px desktop and 390px mobile).
- Note: No external commercial endorsements or third-party marketing testimonials exist; future work must not fabricate them.

## Product Principles
1. Strict Institutional Isolation: A student must only ever see, search, and download academic materials created within their verified university domain.
2. Contribution-Driven Fairness: Credit rewards and deduction costs balance sharing and downloading, discouraging passive free-riding.
3. Zero-Build Simplicity & Robustness: Prioritize server-rendered templates, native browser standards, and atomic database transactions over client-side complexity.
4. Academic Accountability: Foster trust through transparent peer ratings, responsive abuse reporting, and straightforward moderation takedowns.

## Accessibility & Inclusion
- Semantic HTML structure with keyboard-navigable forms, modals, and tables.
- WCAG AA contrast compliance across light and dark themes.
- Clear error states, accessible form validation cues, and screen-reader friendly icon representations.
