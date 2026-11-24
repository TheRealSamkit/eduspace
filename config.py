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
