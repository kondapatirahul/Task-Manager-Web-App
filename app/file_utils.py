"""
File security, validation, and storage utilities for TaskNest task collaboration.
"""

import os
import re
import uuid
from typing import Optional, Tuple, List, Dict, Any
from werkzeug.utils import secure_filename
from werkzeug.datastructures import FileStorage

ALLOWED_EXTENSIONS = {'pdf', 'png', 'jpg', 'jpeg', 'docx', 'xlsx', 'txt'}

DEFAULT_MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB per file
DEFAULT_MAX_FILES_PER_MESSAGE = 5

MIME_TYPE_MAPPING = {
    'pdf': 'application/pdf',
    'png': 'image/png',
    'jpg': 'image/jpeg',
    'jpeg': 'image/jpeg',
    'docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    'xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    'txt': 'text/plain',
}

# Signatures for magic bytes validation
MAGIC_SIGNATURES = {
    'pdf': [b'%PDF-'],
    'png': [b'\x89PNG\r\n\x1a\n'],
    'jpg': [b'\xff\xd8\xff'],
    'jpeg': [b'\xff\xd8\xff'],
    'docx': [b'PK\x03\x04'],  # ZIP container
    'xlsx': [b'PK\x03\x04'],  # ZIP container
}


def get_file_extension(filename: str) -> str:
    """Extract and normalize lowercase file extension without dot."""
    if not filename or '.' not in filename:
        return ''
    return filename.rsplit('.', 1)[1].lower().strip()


def format_file_size(num_bytes: int) -> str:
    """Format byte count into human-readable string."""
    if num_bytes is None or num_bytes < 0:
        return '0 B'
    if num_bytes < 1024:
        return f"{num_bytes} B"
    elif num_bytes < 1024 * 1024:
        return f"{num_bytes / 1024:.1f} KB"
    elif num_bytes < 1024 * 1024 * 1024:
        return f"{num_bytes / (1024 * 1024):.1f} MB"
    else:
        return f"{num_bytes / (1024 * 1024 * 1024):.1f} GB"


def validate_file_content(file_obj: FileStorage, ext: str) -> Tuple[bool, Optional[str]]:
    """
    Validate that the file content matches expected signatures / format.
    Does not consume stream permanently (seeks back to 0).
    """
    ext = ext.lower()
    file_obj.seek(0)
    header = file_obj.read(16)
    file_obj.seek(0)

    if ext in MAGIC_SIGNATURES:
        signatures = MAGIC_SIGNATURES[ext]
        matched = any(header.startswith(sig) for sig in signatures)
        if not matched:
            return False, f"File content does not match expected format for .{ext}"
        return True, None

    if ext == 'txt':
        # Verify text is decodable as utf-8 or ascii without null bytes
        file_obj.seek(0)
        sample = file_obj.read(4096)
        file_obj.seek(0)
        if b'\x00' in sample:
            return False, "Text files must not contain binary null bytes"
        try:
            sample.decode('utf-8')
        except UnicodeDecodeError:
            try:
                sample.decode('latin-1')
            except Exception:
                return False, "Text file is not valid readable text"
        return True, None

    return False, f"Unsupported file extension: .{ext}"


def validate_uploaded_file(file_storage: FileStorage, max_size: int = DEFAULT_MAX_FILE_SIZE) -> Tuple[bool, Optional[str], Optional[Dict[str, Any]]]:
    """
    Validate an uploaded file for presence, name, extension, size, and content.
    Returns: (is_valid, error_message, metadata_dict)
    """
    if not file_storage or not file_storage.filename or not file_storage.filename.strip():
        return False, "No file uploaded or filename is empty", None

    raw_filename = file_storage.filename.strip()
    safe_name = secure_filename(os.path.basename(raw_filename))
    if not safe_name:
        safe_name = f"attachment_{uuid.uuid4().hex[:8]}"

    ext = get_file_extension(raw_filename)
    if not ext or ext not in ALLOWED_EXTENSIONS:
        allowed_list = ', '.join(f".{e}" for e in sorted(ALLOWED_EXTENSIONS))
        return False, f"File type not supported. Allowed formats: {allowed_list}", None

    # Check file size by seeking
    file_storage.seek(0, os.SEEK_END)
    file_size = file_storage.tell()
    file_storage.seek(0)

    if file_size == 0:
        return False, "Uploaded file is empty (0 bytes)", None

    if file_size > max_size:
        return False, f"File exceeds maximum size limit of {format_file_size(max_size)}", None

    # Content signature inspection
    is_content_valid, content_err = validate_file_content(file_storage, ext)
    if not is_content_valid:
        return False, content_err, None

    mime_type = MIME_TYPE_MAPPING.get(ext, file_storage.content_type or 'application/octet-stream')

    metadata = {
        'original_filename': raw_filename,
        'safe_filename': safe_name,
        'extension': ext,
        'file_size': file_size,
        'mime_type': mime_type,
    }
    return True, None, metadata


def save_attachment_file(file_storage: FileStorage, task_id: int, upload_root: str, ext: str) -> Tuple[str, str]:
    """
    Save an uploaded file using a cryptographically unique storage name outside the static folder.
    Prevents path traversal by ensuring the destination is strictly inside the task storage folder.
    Returns (storage_name, absolute_filepath).
    """
    unique_storage_name = f"{uuid.uuid4().hex}.{ext.lower()}"
    task_dir = os.path.join(upload_root, f"task_{task_id}")
    os.makedirs(task_dir, exist_ok=True)

    dest_path = os.path.abspath(os.path.join(task_dir, unique_storage_name))
    resolved_root = os.path.abspath(upload_root)

    # Path traversal assertion
    common = os.path.commonpath([dest_path, resolved_root])
    if common != resolved_root:
        raise ValueError("Invalid storage path: path traversal detected")

    file_storage.seek(0)
    file_storage.save(dest_path)
    return unique_storage_name, dest_path


def get_attachment_filepath(task_id: int, storage_name: str, upload_root: str) -> Optional[str]:
    """
    Get and verify the absolute filepath of an attachment, strictly preventing path traversal.
    """
    if not storage_name or '/' in storage_name or '\\' in storage_name or '..' in storage_name:
        return None

    task_dir = os.path.join(upload_root, f"task_{task_id}")
    dest_path = os.path.abspath(os.path.join(task_dir, storage_name))
    resolved_root = os.path.abspath(upload_root)

    try:
        common = os.path.commonpath([dest_path, resolved_root])
        if common != resolved_root:
            return None
    except ValueError:
        return None

    if not os.path.isfile(dest_path):
        return None

    return dest_path


def delete_attachment_file(task_id: int, storage_name: str, upload_root: str) -> bool:
    """Safely delete an attachment file from disk."""
    filepath = get_attachment_filepath(task_id, storage_name, upload_root)
    if filepath and os.path.isfile(filepath):
        try:
            os.remove(filepath)
            return True
        except OSError:
            pass
    return False


def extract_mentions(text: str) -> List[str]:
    """
    Extract unique usernames mentioned in text via @username syntax.
    Usernames can contain alphanumeric, underscore, dot, hyphen.
    """
    if not text:
        return []
    # Match @username when preceded by start of string, whitespace, or punctuation
    matches = re.findall(r'(?:^|[\s(])@([a-zA-Z0-9_.-]+)', text)
    unique_mentions = []
    seen = set()
    for m in matches:
        clean = m.strip().rstrip('.,!?:;')
        if clean and clean.lower() not in seen:
            seen.add(clean.lower())
            unique_mentions.append(clean)
    return unique_mentions
