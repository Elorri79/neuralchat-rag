import sqlite3
import os
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(__file__), "neuralchat.db")

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn

def init_db():
    conn = get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            is_admin INTEGER DEFAULT 0,
            max_chunks INTEGER DEFAULT 5000,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_login TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            title TEXT DEFAULT 'Nueva conversación',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id INTEGER NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            tokens INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
        );
    """)
    conn.commit()
    conn.close()

def count_users():
    conn = get_db()
    count = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    conn.close()
    return count

def create_user(username, password_hash, is_admin=False):
    conn = get_db()
    try:
        if is_admin:
            cur = conn.execute("INSERT INTO users (username, password_hash, is_admin) VALUES (?, ?, 1)", (username, password_hash))
        else:
            cur = conn.execute("INSERT INTO users (username, password_hash) VALUES (?, ?)", (username, password_hash))
        conn.commit()
        return cur.lastrowid
    except sqlite3.IntegrityError:
        return None
    finally:
        conn.close()

def list_users():
    conn = get_db()
    rows = conn.execute("SELECT id, username, is_admin, max_chunks, created_at, last_login FROM users ORDER BY id").fetchall()
    conn.close()
    return [dict(r) for r in rows]

def delete_user_by_id(user_id):
    conn = get_db()
    conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
    conn.commit()
    conn.close()

def get_user(username):
    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
    conn.close()
    return dict(user) if user else None

def get_user_by_id(user_id):
    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    conn.close()
    return dict(user) if user else None

def update_last_login(user_id):
    conn = get_db()
    conn.execute("UPDATE users SET last_login = ? WHERE id = ?", (datetime.utcnow().isoformat(), user_id))
    conn.commit()
    conn.close()

def create_session(user_id, title="Nueva conversación"):
    conn = get_db()
    cur = conn.execute("INSERT INTO sessions (user_id, title) VALUES (?, ?)", (user_id, title))
    conn.commit()
    session_id = cur.lastrowid
    conn.close()
    return session_id

def get_sessions(user_id):
    conn = get_db()
    rows = conn.execute(
        "SELECT id, title, created_at, updated_at FROM sessions WHERE user_id = ? ORDER BY updated_at DESC",
        (user_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def update_session_title(session_id, title):
    conn = get_db()
    conn.execute("UPDATE sessions SET title = ?, updated_at = ? WHERE id = ?",
                 (title, datetime.utcnow().isoformat(), session_id))
    conn.commit()
    conn.close()

def touch_session(session_id):
    conn = get_db()
    conn.execute("UPDATE sessions SET updated_at = ? WHERE id = ?",
                 (datetime.utcnow().isoformat(), session_id))
    conn.commit()
    conn.close()

def delete_session(session_id):
    conn = get_db()
    conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
    conn.commit()
    conn.close()

def add_message(session_id, role, content, tokens=0):
    conn = get_db()
    cur = conn.execute(
        "INSERT INTO messages (session_id, role, content, tokens) VALUES (?, ?, ?, ?)",
        (session_id, role, content, tokens)
    )
    conn.commit()
    msg_id = cur.lastrowid
    conn.close()
    return msg_id

def get_messages(session_id):
    conn = get_db()
    rows = conn.execute(
        "SELECT id, role, content, tokens, created_at FROM messages WHERE session_id = ? ORDER BY id",
        (session_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_user_chunk_count(user_id):
    import rag
    return rag.get_user_chunks(user_id)

def get_user_storage_info(user_id):
    conn = get_db()
    user = conn.execute("SELECT max_chunks FROM users WHERE id = ?", (user_id,)).fetchone()
    conn.close()
    if not user:
        return None
    used = get_user_chunk_count(user_id)
    return {"used": used, "max": user["max_chunks"], "available": max(0, user["max_chunks"] - used)}
