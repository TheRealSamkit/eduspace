"""
Credit economy service functions for EduSpace.

Encapsulates ledger writes, daily upload reward caps, download charges
with atomic credit checks, and moderation reward reversals.
Depends on sqlite3 (for transaction errors).
"""


def record_ledger_entry(cursor_or_db, user_id, amount, reason, file_id=None):
    """
    Append an immutable transaction record to the credit ledger.

    Args:
        cursor_or_db: Active SQLite connection or cursor within an ongoing transaction.
        user_id (int): Primary key of the affected user.
        amount (int): Net credit change (positive for rewards/signup, negative for downloads/reversals).
        reason (str): Reason identifier ('signup', 'upload', 'download', 'reversal').
        file_id (int, optional): Related file ID if applicable.
    """
    cursor_or_db.execute(
        """
        INSERT INTO ledger (user_id, amount, reason, file_id)
        VALUES (?, ?, ?, ?)
        """,
        (user_id, amount, reason, file_id)
    )


def process_upload_reward(db, user_id, file_id, max_daily_rewards, reward_amount):
    """
    Calculate and apply upload credits subject to the daily reward ceiling.

    Args:
        db: SQLite database connection.
        user_id (int): Uploader user ID.
        file_id (int): Primary key of the newly uploaded file.
        max_daily_rewards (int): Maximum rewarded uploads allowed per UTC calendar day.
        reward_amount (int): Number of credits awarded per eligible upload.

    Returns:
        tuple: (earned_credits: int, notification_message: str)
    Side effects:
        Updates users.credits if eligible and appends an entry to ledger.
    """
    cursor = db.cursor()

    # Count how many upload rewards this user has received today
    rewarded_today = cursor.execute(
        """
        SELECT COUNT(*) FROM ledger
        WHERE user_id = ? AND reason = 'upload' AND amount > 0
        AND date(created_at) = date('now')
        """,
        (user_id,)
    ).fetchone()[0]

    if rewarded_today < max_daily_rewards:
        earned = reward_amount
        cursor.execute("UPDATE users SET credits = credits + ? WHERE id = ?", (earned, user_id))
        msg = f"Material uploaded successfully! You earned {earned} credits."
    else:
        earned = 0
        msg = f"Material uploaded successfully! (Daily reward limit of {max_daily_rewards} reached; 0 credits earned)."

    record_ledger_entry(cursor, user_id, earned, 'upload', file_id)
    return earned, msg


def process_download_transaction(db, user_id, file_id, cost, is_uploader, already_downloaded):
    """
    Atomically verify credit balance, deduct download fee, and register download.

    Uses BEGIN IMMEDIATE to prevent race conditions and overdrafts.

    Args:
        db: SQLite database connection.
        user_id (int): Downloader user ID.
        file_id (int): Target file ID.
        cost (int): Cost in credits for downloading.
        is_uploader (bool): True if the requesting user uploaded the document.
        already_downloaded (bool): True if user previously paid for/downloaded this material.

    Returns:
        tuple: (success: bool, error_message: str or None)
    Side effects:
        Decrements users.credits, writes negative ledger entry, inserts downloads row.
    """
    cursor = db.cursor()
    try:
        cursor.execute("BEGIN IMMEDIATE")

        if not is_uploader and not already_downloaded:
            user_record = cursor.execute(
                "SELECT credits FROM users WHERE id = ?",
                (user_id,)
            ).fetchone()

            if not user_record or user_record['credits'] < cost:
                db.rollback()
                curr_balance = user_record['credits'] if user_record else 0
                return False, (
                    f"Insufficient credits! Downloading this document requires {cost} credits. "
                    f"Your current balance is {curr_balance}. Upload study materials to earn more."
                )

            # Deduct credits and record in ledger
            cursor.execute("UPDATE users SET credits = credits - ? WHERE id = ?", (cost, user_id))
            record_ledger_entry(cursor, user_id, -cost, 'download', file_id)

        if not already_downloaded:
            cursor.execute(
                "INSERT INTO downloads (user_id, file_id) VALUES (?, ?)",
                (user_id, file_id)
            )

        db.commit()
        return True, None
    except Exception as e:
        db.rollback()
        return False, "An error occurred during download processing. Please try again."


def reverse_upload_credits(cursor, file_id, uploader_id, default_reward):
    """
    Reverse the reward credits earned by an uploader when their material is removed.

    Args:
        cursor: Active SQLite database cursor within a transaction.
        file_id (int): Primary key of the violating file.
        uploader_id (int): Primary key of the uploader.
        default_reward (int): Default reward fallback if ledger entry is missing.

    Returns:
        int: Amount of credits reversed.
    Side effects:
        Decrements uploader credits (bounded at 0) and records reversal in ledger.
    """
    upload_ledger = cursor.execute(
        "SELECT COALESCE(SUM(amount), 0) as total FROM ledger WHERE file_id = ? AND user_id = ? AND reason IN ('upload', 'request_reward') AND amount > 0",
        (file_id, uploader_id)
    ).fetchone()

    reversal_amount = upload_ledger['total'] if (upload_ledger and upload_ledger['total'] > 0) else default_reward

    # Ensure credits never become negative from administrative reversal
    cursor.execute(
        "UPDATE users SET credits = MAX(0, credits - ?) WHERE id = ?",
        (reversal_amount, uploader_id)
    )

    record_ledger_entry(cursor, uploader_id, -reversal_amount, 'reversal', file_id)
    return reversal_amount
