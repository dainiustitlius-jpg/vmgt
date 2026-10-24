"""Vartotojai, rolės, teisės ir sesijos.

Slaptažodžiai – PBKDF2-SHA256; slapuke – atsitiktinis žetonas, bazėje – tik
jo SHA-256, tad bazės kopija sesijos nepavagia. PIN skirtas greitam
operatoriaus prisijungimui prie terminalo, kai per pamainą keičiasi žmonės.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets
from datetime import timedelta

from .. import db
from . import NotFound, RuleError

ITERATIONS = 240_000

# Teisės – ką galima daryti. Rolė duoda rinkinį.
PERMS = {
    "view": "Matyti projektus, cechą, analitiką",
    "projects": "Kurti ir keisti projektus, mazgus, etapus",
    "tasks": "Kurti ir keisti užduotis, maršrutus, importuoti",
    "plan": "Rikiuoti ir tvirtinti darbo centrų eiles",
    "execute": "Dirbti terminale: Start, Pauzė, Stop",
    "ack_rev": "Patvirtinti darbą po brėžinio revizijos pasikeitimo",
    "docs": "Įkelti brėžinius",
    "ncr_report": "Registruoti neatitiktis",
    "ncr_manage": "Priskirti ir uždaryti neatitiktis",
    "admin": "Vartotojai ir darbo centrai",
}

ROLES = {
    "admin": ("Administratorius", set(PERMS)),
    "vadovas": ("Projektų vadovas", {"view", "projects", "tasks", "plan", "docs", "ncr_report"}),
    "planuotojas": ("Planuotojas", {"view", "plan", "ncr_report"}),
    "technologas": ("Technologas", {"view", "tasks", "docs", "ncr_report"}),
    "meistras": ("Meistras", {"view", "plan", "execute", "ack_rev", "ncr_report"}),
    "operatorius": ("Operatorius", {"execute", "ncr_report"}),
    "kokybe": ("Kokybės inžinierius", {"view", "ncr_report", "ncr_manage"}),
    "perziura": ("Peržiūra", {"view"}),
}


def hash_secret(secret: str, salt: bytes | None = None) -> str:
    salt = salt or secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", secret.encode(), salt, ITERATIONS)
    return f"pbkdf2${ITERATIONS}${salt.hex()}${dk.hex()}"


def check_secret(secret: str, stored: str | None) -> bool:
    if not stored:
        return False
    try:
        _, it, salt, dk = stored.split("$")
    except ValueError:
        return False
    test = hashlib.pbkdf2_hmac("sha256", secret.encode(), bytes.fromhex(salt), int(it))
    return hmac.compare_digest(test.hex(), dk)


def perms_of(user: dict) -> set[str]:
    return set(ROLES.get(user["role"], ("", set()))[1])


def public_user(u: dict) -> dict:
    return {
        "id": u["id"],
        "login": u["login"],
        "name": u["name"],
        "role": u["role"],
        "role_label": ROLES.get(u["role"], (u["role"],))[0],
        "centres": json.loads(u.get("centres") or "[]"),
        "active": bool(u["active"]),
        "has_pin": bool(u.get("pin_hash")),
        "perms": sorted(perms_of(u)),
    }


def create_user(con, login, name, role, password, pin=None, centres=None, by=None) -> int:
    if role not in ROLES:
        raise RuleError(f"Nežinoma rolė: {role}")
    if not login or not password:
        raise RuleError("Reikia prisijungimo vardo ir slaptažodžio")
    if pin and _pin_taken(con, pin):
        raise RuleError("Toks PIN jau naudojamas")
    try:
        cur = con.execute(
            "INSERT INTO users (login, name, role, pw_hash, pin_hash, centres, created) VALUES (?,?,?,?,?,?,?)",
            (login, name, role, hash_secret(password), hash_secret(pin) if pin else None,
             json.dumps(centres or []), db.now()),
        )
    except Exception as e:  # sqlite3.IntegrityError – užimtas vardas
        raise RuleError(f"Vartotojas „{login}“ jau yra") from e
    db.log_event(con, by, "user", cur.lastrowid, "create", {"login": login, "role": role})
    return cur.lastrowid


def update_user(con, user_id, by, **fields) -> None:
    u = db.row(con.execute("SELECT * FROM users WHERE id=?", (user_id,)))
    if not u:
        raise NotFound("Vartotojo nėra")
    sets, vals = [], []
    if "name" in fields and fields["name"]:
        sets.append("name=?"); vals.append(fields["name"])
    if "role" in fields and fields["role"]:
        if fields["role"] not in ROLES:
            raise RuleError("Nežinoma rolė")
        if u["role"] == "admin" and fields["role"] != "admin" and _active_admins(con) <= 1:
            raise RuleError("Negalima atimti paskutinio administratoriaus")
        sets.append("role=?"); vals.append(fields["role"])
    if "centres" in fields and fields["centres"] is not None:
        sets.append("centres=?"); vals.append(json.dumps(fields["centres"]))
    if fields.get("password"):
        sets.append("pw_hash=?"); vals.append(hash_secret(fields["password"]))
    if "pin" in fields and fields["pin"] is not None:
        if fields["pin"] == "":
            sets.append("pin_hash=NULL")
        else:
            if _pin_taken(con, fields["pin"], exclude=user_id):
                raise RuleError("Toks PIN jau naudojamas")
            sets.append("pin_hash=?"); vals.append(hash_secret(fields["pin"]))
    if "active" in fields and fields["active"] is not None:
        if not fields["active"] and u["role"] == "admin" and _active_admins(con) <= 1:
            raise RuleError("Negalima išjungti paskutinio administratoriaus")
        sets.append("active=?"); vals.append(1 if fields["active"] else 0)
    if not sets:
        return
    con.execute(f"UPDATE users SET {', '.join(sets)} WHERE id=?", (*vals, user_id))
    # pasikeitus slaptažodžiui ar išjungus – senos sesijos nebegalioja
    if fields.get("password") or fields.get("active") is False:
        con.execute("DELETE FROM sessions WHERE user_id=?", (user_id,))
    db.log_event(con, by, "user", user_id, "update", {k: v for k, v in fields.items() if k not in ("password", "pin")})


def _active_admins(con) -> int:
    return con.execute("SELECT COUNT(*) FROM users WHERE role='admin' AND active=1").fetchone()[0]


def _pin_taken(con, pin, exclude=None) -> bool:
    for r in con.execute("SELECT id, pin_hash FROM users WHERE pin_hash IS NOT NULL AND active=1"):
        if r["id"] != exclude and check_secret(pin, r["pin_hash"]):
            return True
    return False


def login(con, hours: int, login_name=None, password=None, pin=None) -> tuple[str, dict]:
    """Grąžina (žetoną, vartotoją). Klaida visada ta pati – neišduodame, ar
    vartotojas egzistuoja."""
    user = None
    if pin:
        for r in db.rows(con.execute("SELECT * FROM users WHERE pin_hash IS NOT NULL AND active=1")):
            if check_secret(pin, r["pin_hash"]):
                user = r
                break
    elif login_name and password:
        r = db.row(con.execute("SELECT * FROM users WHERE login=? AND active=1", (login_name,)))
        if r and check_secret(password, r["pw_hash"]):
            user = r
    if not user:
        raise RuleError("Neteisingi prisijungimo duomenys")
    token = secrets.token_urlsafe(32)
    start = db.parse_ts(db.now())
    con.execute(
        "INSERT INTO sessions (token_hash, user_id, created, expires) VALUES (?,?,?,?)",
        (_th(token), user["id"], start.isoformat(timespec="seconds"),
         (start + timedelta(hours=hours)).isoformat(timespec="seconds")),
    )
    db.log_event(con, user["id"], "user", user["id"], "login", {"pin": bool(pin)})
    return token, user


def logout(con, token: str) -> None:
    con.execute("DELETE FROM sessions WHERE token_hash=?", (_th(token),))


def user_by_token(con, token: str | None) -> dict | None:
    if not token:
        return None
    r = db.row(con.execute(
        "SELECT u.* , s.expires FROM sessions s JOIN users u ON u.id=s.user_id "
        "WHERE s.token_hash=? AND u.active=1", (_th(token),)))
    if not r or r["expires"] < db.now():
        return None
    return r


def can_centre(user: dict, centre_code: str) -> bool:
    allowed = json.loads(user.get("centres") or "[]")
    return not allowed or centre_code in allowed


def _th(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()
