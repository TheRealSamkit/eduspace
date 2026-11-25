"""
EduSpace Database Seeder
Populates demo universities, users, dummy PDF files, ledger entries,
ratings, reports, events, and SUS responses to test and demonstrate the platform.
"""

import os
import uuid
import sqlite3
from datetime import datetime
from werkzeug.security import generate_password_hash
from config import Config
from db import init_db

def generate_minimal_pdf():
    """Generate minimal valid PDF-1.4 file bytes without external libraries."""
    return (
        b"%PDF-1.4\n"
        b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
        b"2 0 obj<</Type/Pages/Count 1/Kids[3 0 R]>>endobj\n"
        b"3 0 obj<</Type/Page/MediaBox[0 0 612 792]/Parent 2 0 R/Resources<<>>>>endobj\n"
        b"xref\n0 4\n0000000000 65535 f \n"
        b"0000000010 00000 n \n0000000060 00000 n \n0000000117 00000 n \n"
        b"trailer<</Size 4/Root 1 0 R>>\nstartxref\n200\n%%EOF"
    )

def seed():
    # Ensure database tables exist
    init_db()

    conn = sqlite3.connect(Config.DATABASE)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    cursor = conn.cursor()

    print("Seeding EduSpace database...")

    # Clear old data for a clean demonstration state
    cursor.execute("DELETE FROM request_submissions;")
    cursor.execute("DELETE FROM request_interest;")
    cursor.execute("DELETE FROM resource_requests;")
    cursor.execute("DELETE FROM bookmarks;")
    cursor.execute("DELETE FROM reports;")
    cursor.execute("DELETE FROM ratings;")
    cursor.execute("DELETE FROM downloads;")
    cursor.execute("DELETE FROM ledger;")
    cursor.execute("DELETE FROM files;")
    cursor.execute("DELETE FROM consents;")
    cursor.execute("DELETE FROM tasks;")
    cursor.execute("DELETE FROM sus_responses;")
    cursor.execute("DELETE FROM feedback;")
    cursor.execute("DELETE FROM events;")
    cursor.execute("DELETE FROM users;")
    cursor.execute("DELETE FROM universities;")

    # 1. Universities
    unis = [
        ("XYZ University", "xyz.edu", "partner"),
        ("ABC College", "abc.edu", "partner"),
        (Config.PUBLIC_UNI_NAME, Config.PUBLIC_EMAIL_DOMAIN, "public"),
    ]
    uni_ids = {}
    for name, domain, kind in unis:
        cursor.execute(
            "INSERT INTO universities (name, domain, kind) VALUES (?, ?, ?)",
            (name, domain, kind)
        )
        uni_ids[domain] = cursor.lastrowid

    # 2. Users (6 demo users: 4 in XYZ University, 2 in ABC College)
    # Admin: admin@xyz.edu / admin123
    # Others: demo1234
    users_data = [
        # XYZ University
        ("admin@xyz.edu", "admin_xyz", "admin123", uni_ids["xyz.edu"], 50, 1),
        ("alice@xyz.edu", "alice_w", "demo1234", uni_ids["xyz.edu"], 35, 0),
        ("bob@xyz.edu", "bob_m", "demo1234", uni_ids["xyz.edu"], 20, 0),
        ("carol@xyz.edu", "carol_k", "demo1234", uni_ids["xyz.edu"], 15, 0),
        # ABC College
        ("david@abc.edu", "david_r", "demo1234", uni_ids["abc.edu"], 40, 0),
        ("emma@abc.edu", "emma_t", "demo1234", uni_ids["abc.edu"], 25, 0),
    ]

    user_ids = {}
    for email, username, pwd, uni_id, creds, is_admin in users_data:
        pwd_hash = generate_password_hash(pwd)
        cursor.execute(
            """
            INSERT INTO users (email, username, password_hash, university_id, credits, is_admin)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (email, username, pwd_hash, uni_id, creds, is_admin)
        )
        uid = cursor.lastrowid
        user_ids[email] = uid

        # Add initial signup bonus ledger
        cursor.execute(
            "INSERT INTO ledger (user_id, amount, reason, file_id) VALUES (?, ?, 'signup', NULL)",
            (uid, Config.SIGNUP_BONUS)
        )

        # Pre-consent for demo accounts
        cursor.execute("INSERT INTO consents (user_id) VALUES (?)", (uid,))

    # 3. Dummy PDF Files (12 files: 8 in XYZ, 4 in ABC)
    upload_folder = Config.UPLOAD_FOLDER
    os.makedirs(upload_folder, exist_ok=True)
    pdf_bytes = generate_minimal_pdf()

    files_data = [
        # XYZ University Files (8 files)
        (
            user_ids["alice@xyz.edu"], uni_ids["xyz.edu"],
            "CS101: Introduction to Python Programming Summary",
            "Computer Science", 1, "Summaries",
            "Comprehensive review of variables, loops, recursion, and object-oriented concepts.",
            "cs101_python_summary.pdf"
        ),
        (
            user_ids["alice@xyz.edu"], uni_ids["xyz.edu"],
            "MATH201: Multivariable Calculus Formulas & Cheatsheet",
            "Mathematics", 2, "Summaries",
            "Vectors, partial derivatives, double integrals, and Green's Theorem formula sheet.",
            "math201_calculus_cheat.pdf"
        ),
        (
            user_ids["bob@xyz.edu"], uni_ids["xyz.edu"],
            "CS202: Data Structures & Algorithms Midterm Exam 2025",
            "Computer Science", 3, "Past Exams",
            "Official spring midterm exam questions covering trees, heaps, graphs, and sorting complexity.",
            "cs202_midterm_2025.pdf"
        ),
        (
            user_ids["bob@xyz.edu"], uni_ids["xyz.edu"],
            "CS304: Database Management Systems Lecture Notes",
            "Computer Science", 4, "Lecture Notes",
            "Relational algebra, normal forms 1NF to BCNF, SQL query execution, and transactions.",
            "cs304_dbms_notes.pdf"
        ),
        (
            user_ids["carol@xyz.edu"], uni_ids["xyz.edu"],
            "PHY101: Engineering Physics Mechanics Worked Solutions",
            "Physics", 1, "Solutions",
            "Step-by-step problem set solutions for kinematics, rotational dynamics, and work-energy.",
            "phy101_solutions.pdf"
        ),
        (
            user_ids["carol@xyz.edu"], uni_ids["xyz.edu"],
            "CS305: Computer Networks Architecture Guide",
            "Computer Science", 4, "Lecture Notes",
            "OSI model, TCP/IP flow control, congestion avoidance, and socket programming review.",
            "cs305_networks_guide.pdf"
        ),
        (
            user_ids["admin@xyz.edu"], uni_ids["xyz.edu"],
            "CHEM102: Organic Chemistry Reaction Mechanisms",
            "Chemistry", 2, "Textbook Guides",
            "SN1/SN2 substitution, E1/E2 elimination reactions, and carbonyl addition mechanisms.",
            "chem102_reactions.pdf"
        ),
        (
            user_ids["admin@xyz.edu"], uni_ids["xyz.edu"],
            "MATH303: Probability & Statistics Final Prep Notes",
            "Mathematics", 3, "Lecture Notes",
            "Bayes theorem, joint distributions, Central Limit Theorem, and hypothesis testing.",
            "math303_probability_final.pdf"
        ),

        # ABC College Files (4 files)
        (
            user_ids["david@abc.edu"], uni_ids["abc.edu"],
            "BIO101: General Cellular Biology Core Notes",
            "Biology", 1, "Lecture Notes",
            "Organelle structures, cellular respiration, photosynthesis, and mitosis mechanisms.",
            "bio101_cellular_bio.pdf"
        ),
        (
            user_ids["david@abc.edu"], uni_ids["abc.edu"],
            "ENG102: Academic Research & Technical Writing Guide",
            "English", 2, "Textbook Guides",
            "Structuring literature reviews, citations styles (APA/IEEE), and thesis development.",
            "eng102_academic_writing.pdf"
        ),
        (
            user_ids["emma@abc.edu"], uni_ids["abc.edu"],
            "BIO202: Molecular Genetics Past Paper Solutions",
            "Biology", 3, "Solutions",
            "Worked explanations for Mendelian crosses, gene mapping, PCR, and gel electrophoresis.",
            "bio202_genetics_solutions.pdf"
        ),
        (
            user_ids["emma@abc.edu"], uni_ids["abc.edu"],
            "CHEM201: Analytical Chemistry Lab Report Template",
            "Chemistry", 3, "Summaries",
            "Standard lab report structure, titration error propagation, and spectrophotometry data.",
            "chem201_lab_template.pdf"
        )
    ]

    file_ids = []
    for uploader_id, uni_id, title, subj, sem, ftype, desc, orig_name in files_data:
        stored_name = f"{uuid.uuid4().hex}.pdf"
        stored_path = os.path.join(upload_folder, stored_name)
        with open(stored_path, 'wb') as f:
            f.write(pdf_bytes)

        file_size = len(pdf_bytes)
        cursor.execute(
            """
            INSERT INTO files (uploader_id, university_id, title, subject, semester, type, description, stored_name, original_name, size, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'active')
            """,
            (uploader_id, uni_id, title, subj, sem, ftype, desc, stored_name, orig_name, file_size)
        )
        fid = cursor.lastrowid
        file_ids.append((fid, uploader_id, uni_id))

        # Ledger row for upload
        cursor.execute(
            "INSERT INTO ledger (user_id, amount, reason, file_id) VALUES (?, ?, 'upload', ?)",
            (uploader_id, Config.UPLOAD_REWARD, fid)
        )

    # 4. Downloads & Ratings (within same university!)
    # Bob downloads Alice's CS101 notes
    cs101_id = file_ids[0][0]
    cursor.execute("INSERT INTO downloads (user_id, file_id) VALUES (?, ?)", (user_ids["bob@xyz.edu"], cs101_id))
    cursor.execute("INSERT INTO ledger (user_id, amount, reason, file_id) VALUES (?, ?, 'download', ?)", (user_ids["bob@xyz.edu"], -Config.DOWNLOAD_COST, cs101_id))
    cursor.execute("INSERT INTO ratings (user_id, file_id, stars) VALUES (?, ?, 5)", (user_ids["bob@xyz.edu"], cs101_id))

    # Carol downloads Alice's MATH201 cheat sheet
    math201_id = file_ids[1][0]
    cursor.execute("INSERT INTO downloads (user_id, file_id) VALUES (?, ?)", (user_ids["carol@xyz.edu"], math201_id))
    cursor.execute("INSERT INTO ledger (user_id, amount, reason, file_id) VALUES (?, ?, 'download', ?)", (user_ids["carol@xyz.edu"], -Config.DOWNLOAD_COST, math201_id))
    cursor.execute("INSERT INTO ratings (user_id, file_id, stars) VALUES (?, ?, 5)", (user_ids["carol@xyz.edu"], math201_id))

    # Alice downloads Bob's CS202 midterm
    cs202_id = file_ids[2][0]
    cursor.execute("INSERT INTO downloads (user_id, file_id) VALUES (?, ?)", (user_ids["alice@xyz.edu"], cs202_id))
    cursor.execute("INSERT INTO ledger (user_id, amount, reason, file_id) VALUES (?, ?, 'download', ?)", (user_ids["alice@xyz.edu"], -Config.DOWNLOAD_COST, cs202_id))
    cursor.execute("INSERT INTO ratings (user_id, file_id, stars) VALUES (?, ?, 4)", (user_ids["alice@xyz.edu"], cs202_id))

    # Emma downloads David's BIO101 notes in ABC College
    bio101_id = file_ids[8][0]
    cursor.execute("INSERT INTO downloads (user_id, file_id) VALUES (?, ?)", (user_ids["emma@abc.edu"], bio101_id))
    cursor.execute("INSERT INTO ledger (user_id, amount, reason, file_id) VALUES (?, ?, 'download', ?)", (user_ids["emma@abc.edu"], -Config.DOWNLOAD_COST, bio101_id))
    cursor.execute("INSERT INTO ratings (user_id, file_id, stars) VALUES (?, ?, 5)", (user_ids["emma@abc.edu"], bio101_id))

    # 5. Open Report for Admin Demonstration
    # Carol reports Bob's PHY101 file
    phy_id = file_ids[4][0]
    cursor.execute(
        """
        INSERT INTO reports (user_id, file_id, reason, status)
        VALUES (?, ?, 'Check formula derivation notation in problem 3', 'open')
        """,
        (user_ids["carol@xyz.edu"], phy_id)
    )

    # 6. Evaluation Tasks (prototype & baseline sample entries)
    cursor.execute(
        """
        INSERT INTO tasks (user_id, task_name, method, duration_sec, clicks, errors, success, started_at, ended_at)
        VALUES (?, 'Find and download notes for Computer Networks, semester 4', 'prototype', 18.4, 5, 0, 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        """,
        (user_ids["alice@xyz.edu"],)
    )
    cursor.execute(
        """
        INSERT INTO tasks (user_id, task_name, method, duration_sec, clicks, errors, success, started_at, ended_at)
        VALUES (?, 'Locate Calculus notes via WhatsApp Group Drive Links', 'baseline', 124.6, 21, 3, 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        """,
        (user_ids["admin@xyz.edu"],)
    )

    # 7. Sample SUS Usability Survey Response (SUS score: 85.0)
    cursor.execute(
        """
        INSERT INTO sus_responses (user_id, q1, q2, q3, q4, q5, q6, q7, q8, q9, q10, score)
        VALUES (?, 5, 1, 5, 1, 4, 1, 5, 1, 4, 1, 85.0)
        """,
        (user_ids["alice@xyz.edu"],)
    )

    # 8. Sample Feedback
    cursor.execute(
        """
        INSERT INTO feedback (user_id, text, usability_issue)
        VALUES (?, 'The credit incentive really encourages students to share notes instead of freeloading. Fast download speeds!', 'Filter reset could remember my semester')
        """,
        (user_ids["alice@xyz.edu"],)
    )

    conn.commit()
    conn.close()

    print("\n========================================================")
    print(" EduSpace Demo Seed Complete!")
    print("========================================================")
    print(" Universities Created:")
    print("  1. XYZ University (Domain: xyz.edu)")
    print("  2. ABC College    (Domain: abc.edu)")
    print("\n Demo User Credentials:")
    print("  --------------------------------------------------------")
    print("  Role       Email             Password   University   Credits")
    print("  --------------------------------------------------------")
    print("  Admin:     admin@xyz.edu     admin123   XYZ Univ     50")
    print("  Student:   alice@xyz.edu     demo1234   XYZ Univ     35")
    print("  Student:   bob@xyz.edu       demo1234   XYZ Univ     20")
    print("  Student:   carol@xyz.edu     demo1234   XYZ Univ     15")
    print("  Student:   david@abc.edu     demo1234   ABC College  40")
    print("  Student:   emma@abc.edu      demo1234   ABC College  25")
    print("  --------------------------------------------------------")
    print(" Files Seeded: 12 total (8 in XYZ University, 4 in ABC College)")
    print(" Single run command: python app.py")
    print("========================================================\n")

if __name__ == '__main__':
    seed()
