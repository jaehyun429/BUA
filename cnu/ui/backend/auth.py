# backend/auth.py
import bcrypt
from cryptography.fernet import Fernet
import os
import sqlite3
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

DB_PATH = "./data/users.db"
FERNET = Fernet(os.getenv("APP_SECRET_KEY").encode())


def init_db():
    Path("./data").mkdir(exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            user_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS credentials (
            user_id TEXT NOT NULL,
            system TEXT NOT NULL,
            cnu_id TEXT NOT NULL,
            cnu_pw_enc TEXT NOT NULL,
            PRIMARY KEY (user_id, system),
            FOREIGN KEY (user_id) REFERENCES users(user_id)
        );
    """)
    conn.commit()
    conn.close()


# ── 우리 시스템 비밀번호 ──
def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode(), hashed.encode())


# ── 학내 시스템 비밀번호 (복호화 필요) ──
def encrypt_credential(plaintext: str) -> str:
    return FERNET.encrypt(plaintext.encode()).decode()

def decrypt_credential(ciphertext: str) -> str:
    return FERNET.decrypt(ciphertext.encode()).decode()


# ── DB 액세스 ──
def create_user(user_id: str, name: str, password: str) -> bool:
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.execute(
            "INSERT INTO users (user_id, name, password_hash) VALUES (?, ?, ?)",
            (user_id, name, hash_password(password))
        )
        conn.commit()
        conn.close()
        return True
    except sqlite3.IntegrityError:
        return False  # 이미 존재


def authenticate(user_id: str, password: str) -> dict | None:
    conn = sqlite3.connect(DB_PATH)
    row = conn.execute(
        "SELECT name, password_hash FROM users WHERE user_id = ?",
        (user_id,)
    ).fetchone()
    conn.close()
    
    if row and verify_password(password, row[1]):
        return {"user_id": user_id, "name": row[0]}
    return None


def save_credential(user_id: str, system: str, cnu_id: str, cnu_pw: str):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        INSERT INTO credentials (user_id, system, cnu_id, cnu_pw_enc)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(user_id, system) DO UPDATE SET
            cnu_id = excluded.cnu_id,
            cnu_pw_enc = excluded.cnu_pw_enc
    """, (user_id, system, cnu_id, encrypt_credential(cnu_pw)))
    conn.commit()
    conn.close()


def get_credential(user_id: str, system: str) -> dict | None:
    conn = sqlite3.connect(DB_PATH)
    row = conn.execute(
        "SELECT cnu_id, cnu_pw_enc FROM credentials WHERE user_id = ? AND system = ?",
        (user_id, system)
    ).fetchone()
    conn.close()
    
    if row:
        return {
            "cnu_id": row[0],
            "cnu_pw": decrypt_credential(row[1])
        }
    return None