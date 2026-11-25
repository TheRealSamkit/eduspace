"""
Server-side preview generation and access helpers for EduSpace.

Generates cached, server-enforced limited previews for locked PDFs (first N pages)
and locked images (downscaled to max dimension). Never exposes full locked files.
"""

import os
from PIL import Image
from pypdf import PdfReader, PdfWriter


def is_file_unlocked(db, user, file):
    """
    Return True if the user is entitled to view the full unredacted file.

    Unlocked for: the uploader, administrators, or users who already downloaded it.
    """
    if not user or not file:
        return False
    if user['id'] == file['uploader_id'] or bool(user['is_admin']):
        return True
    row = db.execute(
        "SELECT 1 FROM downloads WHERE user_id = ? AND file_id = ?",
        (user['id'], file['id'])
    ).fetchone()
    return row is not None


def get_preview_kind(filename):
    """Classify filename into 'pdf', 'image', or 'unsupported'."""
    ext = filename.rsplit('.', 1)[-1].lower() if '.' in (filename or '') else ''
    if ext == 'pdf':
        return 'pdf'
    if ext in ('png', 'jpg', 'jpeg'):
        return 'image'
    return 'unsupported'


def get_or_create_locked_pdf(source_path, content_hash, cache_dir, max_pages):
    """
    Create or return cached PDF containing only the first max_pages pages.

    Raises ValueError for encrypted, empty, or corrupt PDFs.
    """
    os.makedirs(cache_dir, exist_ok=True)
    cache_path = os.path.join(cache_dir, f"{content_hash}_p{max_pages}.pdf")
    if os.path.isfile(cache_path) and os.path.getsize(cache_path) > 0:
        return cache_path

    try:
        reader = PdfReader(source_path)
        if reader.is_encrypted:
            raise ValueError("Encrypted PDFs cannot be previewed.")
        total_pages = len(reader.pages)
        if total_pages == 0:
            raise ValueError("PDF contains no pages.")

        writer = PdfWriter()
        for idx in range(min(max_pages, total_pages)):
            writer.add_page(reader.pages[idx])

        tmp_path = f"{cache_path}.{os.getpid()}.tmp"
        with open(tmp_path, 'wb') as f:
            writer.write(f)
        os.replace(tmp_path, cache_path)
        return cache_path
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError("Corrupt or unreadable PDF file.") from exc


def get_or_create_locked_image(source_path, content_hash, ext, cache_dir, max_px):
    """
    Create or return cached downscaled image bounded by max_px on its longest side.

    Raises ValueError if the image cannot be decoded.
    """
    os.makedirs(cache_dir, exist_ok=True)
    norm_ext = 'jpg' if ext == 'jpeg' else ext
    cache_path = os.path.join(cache_dir, f"{content_hash}_max{max_px}.{norm_ext}")
    if os.path.isfile(cache_path) and os.path.getsize(cache_path) > 0:
        return cache_path

    try:
        with Image.open(source_path) as img:
            img.load()
            img.thumbnail((max_px, max_px), Image.Resampling.LANCZOS)
            save_img = img
            if norm_ext == 'jpg' and img.mode not in ('RGB', 'L'):
                save_img = img.convert('RGB')
            tmp_path = f"{cache_path}.{os.getpid()}.tmp"
            fmt = 'JPEG' if norm_ext == 'jpg' else 'PNG'
            save_img.save(tmp_path, format=fmt)
        os.replace(tmp_path, cache_path)
        return cache_path
    except Exception as exc:
        raise ValueError("Corrupt or unreadable image file.") from exc
