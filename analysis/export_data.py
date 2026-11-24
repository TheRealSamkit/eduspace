"""
EduSpace Data Export Tool
Exports system usage, task evaluation, SUS responses, feedback,
and platform activity into CSV format for statistical analysis.

Note: In accordance with academic ethics and platform privacy rules,
user records are strictly anonymized (email and password hashes omitted).
"""

import os
import sys
import csv
import sqlite3

# Add parent directory to path to import Config
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from config import Config

def export_all(db_path=None, output_dir=None):
    if not db_path:
        db_path = Config.DATABASE
    if not output_dir:
        output_dir = os.path.join(os.path.dirname(__file__), 'exports')

    os.makedirs(output_dir, exist_ok=True)

    if not os.path.exists(db_path):
        print(f"Error: Database not found at '{db_path}'. Please run the app or seed.py first.")
        return

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    datasets = {
        'events.csv': (
            'SELECT id, session_id, user_id, event_type, page, detail, ts FROM events',
            ['id', 'session_id', 'user_id', 'event_type', 'page', 'detail', 'ts']
        ),
        'tasks.csv': (
            'SELECT id, user_id, task_name, method, started_at, ended_at, duration_sec, clicks, errors, success FROM tasks',
            ['id', 'user_id', 'task_name', 'method', 'started_at', 'ended_at', 'duration_sec', 'clicks', 'errors', 'success']
        ),
        'sus_responses.csv': (
            'SELECT id, user_id, q1, q2, q3, q4, q5, q6, q7, q8, q9, q10, score, created_at FROM sus_responses',
            ['id', 'user_id', 'q1', 'q2', 'q3', 'q4', 'q5', 'q6', 'q7', 'q8', 'q9', 'q10', 'score', 'created_at']
        ),
        'feedback.csv': (
            'SELECT id, user_id, text, usability_issue, created_at FROM feedback',
            ['id', 'user_id', 'text', 'usability_issue', 'created_at']
        ),
        'users_anonymized.csv': (
            '''
            SELECT u.id, u.university_id, un.name as university_name, u.credits, u.is_admin, u.created_at
            FROM users u
            JOIN universities un ON u.university_id = un.id
            ''',
            ['id', 'university_id', 'university_name', 'credits', 'is_admin', 'created_at']
        ),
        'files.csv': (
            '''
            SELECT f.id, f.university_id, f.subject, f.semester, f.type, f.size, f.status, f.created_at
            FROM files f
            ''',
            ['id', 'university_id', 'subject', 'semester', 'type', 'size', 'status', 'created_at']
        ),
        'downloads.csv': (
            'SELECT id, user_id, file_id, created_at FROM downloads',
            ['id', 'user_id', 'file_id', 'created_at']
        ),
        'ledger.csv': (
            'SELECT id, user_id, amount, reason, file_id, created_at FROM ledger',
            ['id', 'user_id', 'amount', 'reason', 'file_id', 'created_at']
        )
    }

    print(f"Exporting EduSpace data from '{db_path}' to '{output_dir}'...")

    for filename, (query, headers) in datasets.items():
        filepath = os.path.join(output_dir, filename)
        cursor = conn.cursor()
        rows = cursor.execute(query).fetchall()

        with open(filepath, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(headers)
            for row in rows:
                writer.writerow([row[col] for col in headers])

        print(f" -> Exported {len(rows):4d} records to {filename}")

    conn.close()
    print("Export complete!")

if __name__ == '__main__':
    custom_output = sys.argv[1] if len(sys.argv) > 1 else None
    export_all(output_dir=custom_output)
