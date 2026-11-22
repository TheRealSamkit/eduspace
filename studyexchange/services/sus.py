"""
System Usability Scale (SUS) calculation and validation services.

Provides standard 10-item Brooke (1996) SUS score computation and database persistence.
"""

SUS_ITEMS = [
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


def validate_and_extract_sus_answers(form_dict):
    """
    Validate that all 10 standard items are rated between 1 and 5.

    Args:
        form_dict (dict): Dictionary mapping 'q1' through 'q10' to integer ratings.

    Returns:
        tuple: (answers: list of int or None, invalid_item_number: int or None)
    """
    answers = []
    for i in range(1, 11):
        raw_val = form_dict.get(f'q{i}')
        try:
            val = int(raw_val) if raw_val is not None else None
        except (ValueError, TypeError):
            val = None

        if val is None or not (1 <= val <= 5):
            return None, i
        answers.append(val)
    return answers, None


def calculate_sus_score(answers):
    """
    Compute standard SUS usability score on a 0-100 scale.

    Odd items (1, 3, 5, 7, 9) contribute score = response - 1.
    Even items (2, 4, 6, 8, 10) contribute score = 5 - response.
    Overall SUS Score = Sum of contributions * 2.5.

    Args:
        answers (list of int): List of 10 integer ratings (1 to 5).

    Returns:
        float: SUS score between 0.0 and 100.0.
    """
    # odd indices: 0, 2, 4, 6, 8 -> val - 1
    odd_sum = sum(answers[i] - 1 for i in [0, 2, 4, 6, 8])
    # even indices: 1, 3, 5, 7, 9 -> 5 - val
    even_sum = sum(5 - answers[i] for i in [1, 3, 5, 7, 9])
    return (odd_sum + even_sum) * 2.5


def record_sus_evaluation(db, user_id, answers, score):
    """
    Persist completed SUS survey evaluation to the database.

    Args:
        db: SQLite database connection.
        user_id (int): Student user ID.
        answers (list of int): List of 10 question scores.
        score (float): Calculated overall score.

    Side effects:
        Inserts row into sus_responses.
    """
    db.execute(
        """
        INSERT INTO sus_responses (user_id, q1, q2, q3, q4, q5, q6, q7, q8, q9, q10, score)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (user_id, *answers, score)
    )
    db.commit()
