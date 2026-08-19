#!/usr/bin/env python3
"""Create reserved admin accounts (admin / owner / root) with random passwords.

Usage: venv/bin/python scripts/create_admins.py
"""
import secrets
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.auth import hash_password  # noqa: E402
from app.database import SessionLocal  # noqa: E402
from app.models import User  # noqa: E402

NAMES = ["admin", "owner", "root"]
EMAIL_DOMAIN = "meow.bahari.tr"

db = SessionLocal()
try:
    for name in NAMES:
        existing = db.query(User).filter(User.username == name).first()
        if existing:
            existing.is_admin = True
            db.commit()
            print(f"[{name}] already existed (id={existing.id}) → promoted to admin (password kept)")
        else:
            password = secrets.token_urlsafe(12)
            user = User(
                username=name,
                email=f"{name}@{EMAIL_DOMAIN}",
                password_hash=hash_password(password),
                is_admin=True,
            )
            db.add(user)
            db.commit()
            print(f"[{name}] created → admin ✅ | password: {password}")
finally:
    db.close()
