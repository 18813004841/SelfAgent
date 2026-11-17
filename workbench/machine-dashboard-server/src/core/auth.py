from __future__ import annotations
import hashlib, hmac, os, secrets
from datetime import datetime, timedelta, timezone
from .storage import connect
from .permissions import ALL_MODULES, modules_for_role

SESSION_DAYS = 7
def _hash_password(password, salt=None):
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 240000)
    return f"pbkdf2_sha256$240000${salt.hex()}${digest.hex()}"
def _check_password(password, encoded):
    try:
        _, rounds, salt, digest = encoded.split("$")
        actual = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), int(rounds)).hex()
        return hmac.compare_digest(actual, digest)
    except (ValueError, TypeError): return False
def ensure_admin():
    db = connect(); row = db.execute("SELECT id FROM users LIMIT 1").fetchone()
    if not row:
        username = os.environ.get("WORKBENCH_ADMIN_USERNAME", "admin").strip() or "admin"
        password = os.environ.get("WORKBENCH_ADMIN_PASSWORD", "admin")
        cur = db.execute("INSERT INTO users(username,password_hash,display_name,is_admin,role) VALUES(?,?,?,1,'admin')", (username, _hash_password(password), "管理员"))
        db.executemany("INSERT INTO user_permissions(user_id,module_key) VALUES(?,?)", [(cur.lastrowid, m) for m in ALL_MODULES]); db.commit()
    db.close()
def user_summary(db, user):
    permissions = [r[0] for r in db.execute("SELECT module_key FROM user_permissions WHERE user_id=?", (user["id"],))]
    role = user["role"] if "role" in user.keys() else ("admin" if user["is_admin"] else "user")
    if user["is_admin"]: role = "admin"
    permissions = modules_for_role(role)
    return {"id": user["id"], "username": user["username"], "display_name": user["display_name"], "role": role, "is_admin": role == "admin", "enabled": bool(user["enabled"]), "modules": permissions}
def login(username, password):
    db = connect(); user = db.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
    if not user or not user["enabled"] or not _check_password(password, user["password_hash"]): db.close(); return None
    token = secrets.token_urlsafe(32); expires = datetime.now(timezone.utc) + timedelta(days=SESSION_DAYS)
    db.execute("INSERT INTO sessions(token_hash,user_id,expires_at) VALUES(?,?,?)", (hashlib.sha256(token.encode()).hexdigest(), user["id"], expires.isoformat())); db.commit(); result = user_summary(db, user); db.close(); return token, result
def current(token):
    if not token: return None
    db = connect(); row = db.execute("SELECT u.* FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.token_hash=? AND s.expires_at>? AND u.enabled=1", (hashlib.sha256(token.encode()).hexdigest(), datetime.now(timezone.utc).isoformat())).fetchone()
    result = user_summary(db, row) if row else None; db.close(); return result
def logout(token):
    if token:
        db = connect(); db.execute("DELETE FROM sessions WHERE token_hash=?", (hashlib.sha256(token.encode()).hexdigest(),)); db.commit(); db.close()
def has_module(user, module): return bool(user and (user["is_admin"] or module in user["modules"]))
