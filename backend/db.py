import sqlite3
import json
from typing import Optional, List, Dict, Any
from datetime import datetime
import hashlib
import os

DB_PATH = "chats.sqlite3"


def _conn():
    return sqlite3.connect(DB_PATH)


def _hash_password(password: str, salt: Optional[str] = None) -> str:
    salt = salt or os.urandom(16).hex()
    digest = hashlib.sha256((salt + password).encode("utf-8")).hexdigest()
    return f"{salt}${digest}"


def _verify_password(password: str, salted_hash: str) -> bool:
    try:
        salt, stored = salted_hash.split("$", 1)
        candidate = hashlib.sha256((salt + password).encode("utf-8")).hexdigest()
        return candidate == stored
    except Exception:
        return False


def init_db():
    conn = _conn()
    cur = conn.cursor()
    # chats table
    cur.execute("""
    CREATE TABLE IF NOT EXISTS chats (
        session_id TEXT PRIMARY KEY,
        title TEXT,
        user_id TEXT,
        messages_json TEXT NOT NULL,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """)
    # chunks table
    cur.execute("""
    CREATE TABLE IF NOT EXISTS chunks (
        chunk_id TEXT PRIMARY KEY,
        doc_id TEXT,
        session_id TEXT,
        url TEXT,
        position INTEGER,
        created_at TEXT
    )
    """)
    # users table
    cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        email TEXT UNIQUE,
        password_hash TEXT NOT NULL,
        role TEXT NOT NULL CHECK(role IN ('user','admin')),
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """)
    # otps table
    cur.execute("""
    CREATE TABLE IF NOT EXISTS otps (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        otp TEXT NOT NULL,
        expires_at TEXT NOT NULL,
        created_at TEXT NOT NULL,
        FOREIGN KEY (user_id) REFERENCES users (id)
    )
    """)
    conn.commit()
    conn.close()


def upsert_chat(session_id: str, user_id: Optional[str], title: str, messages: List[Dict[str, Any]]):
    conn = _conn()
    cur = conn.cursor()
    now = datetime.utcnow().isoformat()
    cur.execute("""
      INSERT INTO chats (session_id, title, user_id, messages_json, created_at, updated_at)
      VALUES (?, ?, ?, ?, ?, ?)
      ON CONFLICT(session_id) DO UPDATE SET
        title=excluded.title,
        user_id=excluded.user_id,
        messages_json=excluded.messages_json,
        updated_at=excluded.updated_at
    """, (session_id, title, user_id, json.dumps(messages, ensure_ascii=False), now, now))
    conn.commit()
    conn.close()


def load_chat(session_id: str) -> Optional[Dict[str, Any]]:
    conn = _conn()
    cur = conn.cursor()
    cur.execute("SELECT session_id, title, user_id, messages_json, created_at, updated_at FROM chats WHERE session_id=?", (session_id,))
    row = cur.fetchone()
    conn.close()
    if not row:
        return None
    return {
        "session_id": row[0],
        "title": row[1],
        "user_id": row[2],
        "messages": json.loads(row[3]),
        "created_at": row[4],
        "updated_at": row[5],
    }


def list_chats(user_id: Optional[str] = None, limit: int = 50, offset: int = 0) -> List[Dict[str, Any]]:
    conn = _conn()
    cur = conn.cursor()
    if user_id:
        cur.execute("""
          SELECT session_id, title, user_id, created_at, updated_at
          FROM chats
          WHERE user_id=?
          ORDER BY updated_at DESC
          LIMIT ? OFFSET ?
        """, (user_id, limit, offset))
    else:
        cur.execute("""
          SELECT session_id, title, user_id, created_at, updated_at
          FROM chats
          ORDER BY updated_at DESC
          LIMIT ? OFFSET ?
        """, (limit, offset))
    rows = cur.fetchall()
    conn.close()
    return [
        {"session_id": r[0], "title": r[1], "user_id": r[2], "created_at": r[3], "updated_at": r[4]}
        for r in rows
    ]

# ---------------- chunk helpers ----------------

def insert_chunk_record(chunk_id: str, doc_id: str, session_id: str, url: str, position: int):
    conn = _conn()
    cur = conn.cursor()
    now = datetime.utcnow().isoformat()
    try:
        cur.execute("""
            INSERT INTO chunks (chunk_id, doc_id, session_id, url, position, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (chunk_id, doc_id, session_id, url, position, now))
        conn.commit()
    except sqlite3.IntegrityError:
        # already exists
        pass
    finally:
        conn.close()


def chunk_exists_for_session(chunk_id: str, session_id: str) -> bool:
    conn = _conn()
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM chunks WHERE chunk_id=? AND session_id=? LIMIT 1", (chunk_id, session_id))
    row = cur.fetchone()
    conn.close()
    return row is not None


def get_chunks_for_session(session_id: str, limit: int = 100) -> List[Dict[str, Any]]:
    conn = _conn()
    cur = conn.cursor()
    cur.execute("SELECT chunk_id, doc_id, url, position, created_at FROM chunks WHERE session_id=? ORDER BY created_at DESC LIMIT ?", (session_id, limit))
    rows = cur.fetchall()
    conn.close()
    return [
        {"chunk_id": r[0], "doc_id": r[1], "url": r[2], "position": r[3], "created_at": r[4]}
        for r in rows
    ]

# ---------------- users helpers ----------------

def create_user(username: str, password: str, role: str = 'user', email: Optional[str] = None) -> Dict[str, Any]:
    conn = _conn()
    cur = conn.cursor()
    now = datetime.utcnow().isoformat()
    pwd = _hash_password(password)
    cur.execute("""
      INSERT INTO users (username, email, password_hash, role, created_at, updated_at)
      VALUES (?, ?, ?, ?, ?, ?)
    """, (username, email, pwd, role, now, now))
    conn.commit()
    user_id = cur.lastrowid
    conn.close()
    return {"id": user_id, "username": username, "email": email, "role": role}


def get_user_by_username(username: str) -> Optional[Dict[str, Any]]:
    conn = _conn()
    cur = conn.cursor()
    cur.execute("SELECT id, username, email, password_hash, role, created_at, updated_at FROM users WHERE username=?", (username,))
    row = cur.fetchone()
    conn.close()
    if not row:
        return None
    return {"id": row[0], "username": row[1], "email": row[2], "password_hash": row[3], "role": row[4], "created_at": row[5], "updated_at": row[6]}

def get_user_by_email(email: str) -> Optional[Dict[str, Any]]:
    conn = _conn()
    cur = conn.cursor()
    cur.execute("SELECT id, username, email, password_hash, role, created_at, updated_at FROM users WHERE email=?", (email,))
    row = cur.fetchone()
    conn.close()
    if not row:
        return None
    return {"id": row[0], "username": row[1], "email": row[2], "password_hash": row[3], "role": row[4], "created_at": row[5], "updated_at": row[6]}


def check_username_available(username: str) -> bool:
    return get_user_by_username(username) is None


def list_users(limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
    conn = _conn()
    cur = conn.cursor()
    cur.execute("SELECT id, username, email, role, created_at, updated_at FROM users ORDER BY created_at DESC LIMIT ? OFFSET ?", (limit, offset))
    rows = cur.fetchall()
    conn.close()
    return [{"id": r[0], "username": r[1], "email": r[2], "role": r[3], "created_at": r[4], "updated_at": r[5]} for r in rows]


def set_user_role(user_id: int, role: str):
    conn = _conn()
    cur = conn.cursor()
    now = datetime.utcnow().isoformat()
    cur.execute("UPDATE users SET role=?, updated_at=? WHERE id=?", (role, now, user_id))
    conn.commit()
    conn.close()

def verify_user_password(username_or_email: str, password: str) -> Optional[Dict[str, Any]]:
    # Try to find user by username first
    user = get_user_by_username(username_or_email)
    # If not found, try to find by email
    if not user:
        user = get_user_by_email(username_or_email)
    if not user:
        return None
    if _verify_password(password, user["password_hash"]):
        return {"id": user["id"], "username": user["username"], "email": user["email"], "role": user["role"]}
    return None


# ---------------- OTP helpers ----------------

def create_otp(user_id: int, otp: str, expires_at: str) -> None:
    """
    Create a new OTP for a user.
    """
    conn = _conn()
    cur = conn.cursor()
    now = datetime.utcnow().isoformat()
    # Delete any existing OTPs for this user
    cur.execute("DELETE FROM otps WHERE user_id = ?", (user_id,))
    # Insert the new OTP
    cur.execute("""
        INSERT INTO otps (user_id, otp, expires_at, created_at)
        VALUES (?, ?, ?, ?)
    """, (user_id, otp, expires_at, now))
    conn.commit()
    conn.close()


def verify_otp(user_id: int, otp: str) -> bool:
    """
    Verify if an OTP is valid for a user and hasn't expired.
    """
    conn = _conn()
    cur = conn.cursor()
    now = datetime.utcnow().isoformat()
    cur.execute("""
        SELECT 1 FROM otps
        WHERE user_id = ? AND otp = ? AND expires_at > ?
        LIMIT 1
    """, (user_id, otp, now))
    row = cur.fetchone()
    conn.close()
    return row is not None


def delete_otp(user_id: int) -> None:
    """
    Delete OTP for a user (after successful verification or expiration).
    """
    conn = _conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM otps WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()


def get_otp_expiration(user_id: int) -> Optional[str]:
    """
    Get the expiration time of the OTP for a user.
    """
    conn = _conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT expires_at FROM otps
        WHERE user_id = ?
        ORDER BY created_at DESC
        LIMIT 1
    """, (user_id,))
    row = cur.fetchone()
    conn.close()
    return row[0] if row else None

def update_password(user_id: int, new_password: str) -> None:
    """
    Update the password for a user.
    """
    conn = _conn()
    cur = conn.cursor()
    now = datetime.utcnow().isoformat()
    pwd = _hash_password(new_password)
    cur.execute("""
        UPDATE users
        SET password_hash = ?, updated_at = ?
        WHERE id = ?
    """, (pwd, now, user_id))
    conn.commit()
    conn.close()

    # Delete the OTP after successful password reset
    delete_otp(user_id)