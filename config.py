import os

class Config:
    # Allowed university email domains mapped to University Name
    ALLOWED_DOMAINS = {
        "xyz.edu": "XYZ University",
        "abc.edu": "ABC College",
        "jg.edu.in": "JG University",
        "lj.edu.in": "LJ University",
        "gtu.ac.in": "GTU",
    }

    # Credit Economy Settings
    SIGNUP_BONUS = 20
    UPLOAD_REWARD = 10
    DOWNLOAD_COST = 5
    MAX_REWARDED_UPLOADS_PER_DAY = 3

    # Public Library & Open Sign-up Settings
    PUBLIC_EMAIL_DOMAIN = "eduspace.public"
    PUBLIC_UNI_NAME = "EduSpace Public"
    PUBLIC_SIGNUP_BONUS = 10
    PUBLIC_SIGNUPS_PER_HOUR_PER_IP = 5

    # Preview & Moderation Settings
    PREVIEW_LOCKED_PAGES = 3
    PREVIEW_IMAGE_MAX_PX = 900
    REPORTS_TO_AUTOHIDE = 3

    # Resource Requests Settings
    REQUEST_BASE_REWARD = 15
    REQUEST_INTEREST_BONUS = 1
    REQUEST_BONUS_CAP = 10
    MAX_OPEN_REQUESTS_PER_USER = 3
    MAX_REQUEST_REWARDS_PER_DAY = 2

    # Licensing Choices for Public Uploads
    LICENSE_CHOICES = [
        ("own_work", "Own original work"),
        ("cc_by", "Open licence: CC BY 4.0"),
        ("cc_by_sa", "Open licence: CC BY-SA 4.0"),
        ("cc0", "Open licence: CC0 (No Rights Reserved)"),
        ("public_domain", "Public Domain"),
    ]

    # File Upload Limits
    MAX_FILE_MB = 10
    MAX_CONTENT_LENGTH = 10 * 1024 * 1024  # 10 MB in bytes
    ALLOWED_EXT = {"pdf", "pptx", "docx", "png", "jpg"}

    # Base Paths
    BASE_DIR = os.path.abspath(os.path.dirname(__file__))
    DATABASE = os.environ.get("DATABASE_PATH", os.path.join(BASE_DIR, "eduspace.db"))
    UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads")

    # Security & Admin
    SECRET_KEY = os.environ.get("SECRET_KEY", "eduspace-secret-key-2026-secure")
    ADMIN_EMAIL = "admin@xyz.edu"
