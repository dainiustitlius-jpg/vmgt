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

# Teisės – ką galima daryti. Rolė duoda rinkinį, vartotojui galima atskirai
# pridėti ar atimti (`users.perm_add` / `perm_remove`).
PERMS = {
    "view": "Matyti projektus, cechą, analitiką",
    "projects": "Kurti ir keisti projektus, mazgus, etapus",
    "tasks": "Kurti ir keisti užduotis, maršrutus, importuoti",
    "release": "Išleisti mazgo maršrutą į gamybą ir grąžinti jį keisti",
    "plan": "Rikiuoti ir tvirtinti darbo centrų eiles",
    "execute": "Dirbti terminale: Start, Pauzė, Stop",
    "ack_rev": "Patvirtinti darbą po brėžinio revizijos ar technologo failo pasikeitimo, leisti patikros išimtį",
    "docs": "Įkelti brėžinius",
    "ncr_report": "Registruoti neatitiktis",
    "ncr_manage": "Priskirti ir uždaryti neatitiktis",
    "quality": "Kokybė: kontrolės patikros, išimtys, sertifikatai, kvalifikacijos, WPS, dosjė",
    "purchase": "Komponentų pirkimai: eilutės, importas",
    "receive": "Registruoti komponentų gavimą",
    "actions": "Kurti projekto užduotis ir keisti visų užduotis",
    "meetings": "Vesti ir tvirtinti susitikimų protokolus",
    "calendar": "Darbo kalendorius: pamainos, nedarbo dienos, remontai, papildomas darbas",
    "admin": "Vartotojai, rolės ir teisės, darbo centrai",
}

# Moduliai – kaip teisės sugrupuotos lange (matrica, vartotojo kortelė) ir
# trumpi pavadinimai stulpeliams.
MODULES = [
    ("projektai", "Projektai", [("view", "Matyti"), ("projects", "Projektai ir etapai"),
                                ("actions", "Komandos užduotys"), ("meetings", "Protokolai")]),
    ("planavimas", "Planavimas", [("plan", "Centrų eilės"), ("calendar", "Darbo kalendorius")]),
    ("gamyba", "Gamyba", [("execute", "Terminalas"), ("ack_rev", "Meistro patvirtinimai"),
                          ("tasks", "Maršrutai ir užduotys"), ("release", "Išleisti į gamybą"),
                          ("docs", "Brėžiniai")]),
    ("kokybe", "Kokybė", [("ncr_report", "Registruoti neatitiktis"), ("ncr_manage", "Valdyti neatitiktis"),
                          ("quality", "Kokybės kontrolė")]),
    ("tiekimas", "Tiekimas", [("purchase", "Pirkimai"), ("receive", "Gavimas")]),
    ("admin", "Administravimas", [("admin", "Administravimas")]),
]
PERM_LABEL = {k: l for _, _, ps in MODULES for k, l in ps}

# Bare ribojami veiksmai: rolei su `scope='own'` (pvz. meistrui) jie galioja
# tik priskirtų barų / centrų darbams, kitur – tik matyti. Terminalas
# (`execute`) ribojamas visada – operatorius dirba tik savo centruose.
SCOPED = {"execute", "ack_rev", "plan", "calendar"}

ROLES = {
    "admin": ("Administratorius", set(PERMS)),
    "vadovas": ("Projektų vadovas", {"view", "projects", "tasks", "plan", "docs", "ncr_report", "purchase",
                                     "actions", "meetings", "calendar"}),
    "pirkimai": ("Pirkimų specialistas", {"view", "purchase", "receive", "actions"}),
    "sandelis": ("Sandėlininkas", {"view", "receive"}),
    "planuotojas": ("Planuotojas", {"view", "plan", "ncr_report", "actions", "calendar"}),
    "technologas": ("Technologas", {"view", "tasks", "release", "docs", "ncr_report", "actions"}),
    "meistras": ("Meistras", {"view", "plan", "execute", "ack_rev", "ncr_report", "receive", "actions",
                              "calendar"}),
    "operatorius": ("Operatorius", {"execute", "ncr_report"}),
    "kokybe": ("Kokybės inžinierius", {"view", "ncr_report", "ncr_manage", "quality", "actions"}),
    "perziura": ("Peržiūra", {"view"}),
}
# meistras eilę, kalendorių ir patvirtinimus tvarko savo baruose (vartotojo sprendimas 2026-10-26)
ROLE_SCOPE = {"meistras": "own"}
ROLE_INFO = {
    "admin": "Viskas, ir vartotojų bei teisių valdymas",
    "vadovas": "Projektai, planas, pirkimai, susitikimai",
    "pirkimai": "Komponentų užsakymai ir gavimai",
    "sandelis": "Gavimai, medžiagų lydiniai",
    "planuotojas": "Departamentų planas, centrų eilės, kalendorius",
    "technologas": "Maršrutai, failai, išleidimas į gamybą",
    "meistras": "Savo barų eilės, kalendorius, patvirtinimai, terminalas",
    "operatorius": "Tik terminalas priskirtuose centruose",
    "kokybe": "Kokybės kontrolė, neatitiktys, dosjė",
    "perziura": "Tik matyti",
}


def _split(v) -> set[str]:
    if isinstance(v, (list, set, tuple)):
        return {x for x in v if x}
    return {x for x in (v or "").split(",") if x}


def ensure_roles(con) -> None:
    """Įprastos rolės bazėje – kad jas būtų galima keisti lange. Esamos
    neperrašomos: administratoriaus pakeitimai lieka."""
    for i, (code, (name, perms)) in enumerate(ROLES.items()):
        con.execute("INSERT OR IGNORE INTO roles (code, name, perms, scope, description, system, sort) "
                    "VALUES (?,?,?,?,?,1,?)", (code, name, ",".join(sorted(perms)), ROLE_SCOPE.get(code, "all"),
                                                ROLE_INFO.get(code, ""), i))


def _roles(con) -> dict:
    out = {r["code"]: r for r in db.rows(con.execute("SELECT * FROM roles ORDER BY sort, name"))}
    if not out:                    # bazė be įrašytų rolių (testai) – kodo numatytosios
        out = {k: {"code": k, "name": n, "perms": ",".join(sorted(p)), "scope": ROLE_SCOPE.get(k, "all"),
                   "description": ROLE_INFO.get(k, ""), "system": 1, "sort": i}
               for i, (k, (n, p)) in enumerate(ROLES.items())}
    return out


def _effective(role_code, role_perms, add, remove) -> set[str]:
    # administratorius visada turi viską – kitaip galima užsirakinti
    if role_code == "admin":
        return set(PERMS)
    return ((set(role_perms) | set(add)) - set(remove)) & set(PERMS)


def load_perms(con, user: dict) -> dict:
    """Prideda vartotojui galiojančias teises iš bazės (rolė + išimtys)."""
    r = _roles(con).get(user["role"])
    user["_perms"] = _effective(user["role"], _split(r["perms"]) if r else set(),
                                _split(user.get("perm_add")), _split(user.get("perm_remove")))
    user["_scope"] = r["scope"] if r else "all"
    user["_role_name"] = r["name"] if r else user["role"]
    return user


def perms_of(user: dict) -> set[str]:
    if "_perms" in user:
        return set(user["_perms"])
    # be bazės (vidiniai kvietimai, testai) – kodo numatytosios rolės
    return _effective(user["role"], ROLES.get(user["role"], ("", set()))[1],
                      _split(user.get("perm_add")), _split(user.get("perm_remove")))


def scope_of(user: dict) -> str:
    return user.get("_scope") or ROLE_SCOPE.get(user["role"], "all")


def can_at(user: dict, perm: str, centre_code: str | None, area_code: str | None = None) -> bool:
    """Ar teisė galioja šio centro darbui: bare ribojama teisė rolei „savo
    baruose“ – tik priskirtuose baruose / centruose (tušti – visi)."""
    if perm not in perms_of(user):
        return False
    if perm not in SCOPED or (perm != "execute" and scope_of(user) == "all"):
        return True
    return can_centre(user, centre_code or "", area_code)


def require_at(user: dict, perm: str, centre_code: str | None, area_code: str | None = None) -> None:
    if not can_at(user, perm, centre_code, area_code):
        if perm in perms_of(user):
            raise RuleError(f"{centre_code or area_code} – ne jūsų baras: čia galite tik matyti")
        raise RuleError("Neturite teisės šiam veiksmui")


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


def pin_key(con, pin: str) -> str:
    """PIN raktas: HMAC-SHA256 su šios diegties paslaptimi.

    Kodėl ne PBKDF2, kaip slaptažodžiams: PIN tikrinamas neturint
    prisijungimo vardo, tad su lėta maiša tektų tikrinti VISUS vartotojus iš
    eilės – 6 PIN užtrukdavo iki 0,9 s, 50 operatorių būtų ~7 s prie
    terminalo. 4–8 skaitmenų PIN lėta maiša nuo perrinkimo vis tiek neapsaugo
    (10^4 variantų); jį saugo bandymų riba web sluoksnyje (`web.app`).
    """
    r = con.execute("SELECT value FROM settings WHERE key='pin_secret'").fetchone()
    if r:
        secret = r[0]
    else:
        secret = secrets.token_hex(32)
        con.execute("INSERT INTO settings (key, value) VALUES ('pin_secret', ?)", (secret,))
    return "pin$" + hmac.new(bytes.fromhex(secret), pin.encode(), hashlib.sha256).hexdigest()


def public_user(u: dict) -> dict:
    return {
        "id": u["id"],
        "login": u["login"],
        "name": u["name"],
        "role": u["role"],
        "role_label": u.get("_role_name") or ROLES.get(u["role"], (u["role"],))[0],
        "centres": json.loads(u.get("centres") or "[]"),
        "active": bool(u["active"]),
        "has_pin": bool(u.get("pin_hash")),
        "perms": sorted(perms_of(u)),
        "scope": scope_of(u),
        "perm_add": sorted(_split(u.get("perm_add"))),
        "perm_remove": sorted(_split(u.get("perm_remove"))),
    }


def create_user(con, login, name, role, password, pin=None, centres=None, by=None) -> int:
    if role not in _roles(con):
        raise RuleError(f"Nežinoma rolė: {role}")
    if not login or not password:
        raise RuleError("Reikia prisijungimo vardo ir slaptažodžio")
    if pin and _pin_taken(con, pin):
        raise RuleError("Toks PIN jau naudojamas")
    try:
        cur = con.execute(
            "INSERT INTO users (login, name, role, pw_hash, pin_hash, centres, created) VALUES (?,?,?,?,?,?,?)",
            (login, name, role, hash_secret(password), pin_key(con, pin) if pin else None,
             json.dumps(centres or []), db.now()),
        )
    except Exception as e:  # sqlite3.IntegrityError – užimtas vardas
        raise RuleError(f"Vartotojas „{login}“ jau yra") from e
    db.log_event(con, by, "user", cur.lastrowid, "create", {"login": login, "role": role})
    if by is not None:
        _access(con, by, "user", cur.lastrowid, f"{name} ({login}): sukurtas, rolė {_role_name(con, role)}"
                + (f", barai / centrai {', '.join(centres)}" if centres else ""))
    return cur.lastrowid


def update_user(con, user_id, by, **fields) -> None:
    u = db.row(con.execute("SELECT * FROM users WHERE id=?", (user_id,)))
    if not u:
        raise NotFound("Vartotojo nėra")
    sets, vals, said = [], [], []
    if "name" in fields and fields["name"] and fields["name"] != u["name"]:
        sets.append("name=?"); vals.append(fields["name"])
        said.append(f"vardas → {fields['name']}")
    if "role" in fields and fields["role"] and fields["role"] != u["role"]:
        if fields["role"] not in _roles(con):
            raise RuleError("Nežinoma rolė")
        sets.append("role=?"); vals.append(fields["role"])
        said.append(f"rolė {_role_name(con, u['role'])} → {_role_name(con, fields['role'])}")
    if "centres" in fields and fields["centres"] is not None:
        new = [c for c in fields["centres"] if c]
        if new != json.loads(u["centres"] or "[]"):
            sets.append("centres=?"); vals.append(json.dumps(new))
            said.append(f"barai / centrai → {', '.join(new) or 'visi'}")
    for col, word in (("perm_add", "papildomai suteikta"), ("perm_remove", "atimta")):
        if col in fields and fields[col] is not None:
            new = _split(fields[col])
            bad = new - set(PERMS)
            if bad:
                raise RuleError(f"Nežinoma teisė: {', '.join(sorted(bad))}")
            old = _split(u[col])
            if new != old:
                sets.append(f"{col}=?"); vals.append(",".join(sorted(new)))
                said.append(f"{word}: " + (", ".join(PERM_LABEL[p] for p in sorted(new)) or "nieko"))
    if fields.get("password"):
        sets.append("pw_hash=?"); vals.append(hash_secret(fields["password"]))
        said.append("pakeistas slaptažodis")
    if "pin" in fields and fields["pin"] is not None:
        if fields["pin"] == "":
            sets.append("pin_hash=NULL")
            said.append("PIN pašalintas")
        else:
            if _pin_taken(con, fields["pin"], exclude=user_id):
                raise RuleError("Toks PIN jau naudojamas")
            sets.append("pin_hash=?"); vals.append(pin_key(con, fields["pin"]))
            said.append("nustatytas naujas PIN")
    if "active" in fields and fields["active"] is not None and bool(fields["active"]) != bool(u["active"]):
        sets.append("active=?"); vals.append(1 if fields["active"] else 0)
        said.append("įjungtas" if fields["active"] else "išjungtas")
    if not sets:
        return
    con.execute(f"UPDATE users SET {', '.join(sets)} WHERE id=?", (*vals, user_id))
    _keep_admin(con)
    # pasikeitus slaptažodžiui ar išjungus – senos sesijos nebegalioja
    if fields.get("password") or fields.get("active") is False:
        con.execute("DELETE FROM sessions WHERE user_id=?", (user_id,))
    db.log_event(con, by, "user", user_id, "update", {k: v for k, v in fields.items() if k not in ("password", "pin")})
    _access(con, by, "user", user_id, f"{u['name']} ({u['login']}): " + "; ".join(said),
            {k: v for k, v in fields.items() if k not in ("password", "pin") and v is not None})


def _keep_admin(con) -> None:
    """Bent vienas aktyvus vartotojas turi likti su administravimo teise –
    kitaip niekas nebegalėtų valdyti teisių. Tikrinama jau pakeitus."""
    for u in db.rows(con.execute("SELECT * FROM users WHERE active=1")):
        if "admin" in perms_of(load_perms(con, u)):
            return
    raise RuleError("Negalima atimti administravimo teisės paskutiniam administratoriui")


def _role_name(con, code) -> str:
    r = _roles(con).get(code)
    return r["name"] if r else code


def _access(con, by, target, target_id, summary, data=None) -> None:
    con.execute("INSERT INTO access_log (at, by_id, target, target_id, summary, data) VALUES (?,?,?,?,?,?)",
                (db.now(), by, target, str(target_id), summary, json.dumps(data or {}, ensure_ascii=False)))


# ---------- rolės ----------

def list_roles(con) -> list[dict]:
    counts = dict(con.execute("SELECT role, COUNT(*) FROM users WHERE active=1 GROUP BY role").fetchall())
    out = []
    for r in _roles(con).values():
        perms = set(PERMS) if r["code"] == "admin" else _split(r["perms"])
        out.append({"code": r["code"], "name": r["name"], "perms": sorted(perms), "scope": r["scope"],
                    "description": r["description"], "system": bool(r["system"]), "users": counts.get(r["code"], 0),
                    "locked": r["code"] == "admin"})
    return out


def save_role(con, by, code: str, data: dict, new=False) -> str:
    """Nauja rolė arba esamos pakeitimas: pavadinimas, teisės, ar bare
    ribojami veiksmai tik savo baruose. Administratoriaus teisių keisti negalima."""
    import re
    roles = _roles(con)
    if new:
        code = (code or data.get("code") or "").strip().lower()
        if not re.fullmatch(r"[a-z][a-z0-9_]{1,23}", code):
            raise RuleError("Rolės kodas – lotyniškos raidės ir skaičiai, pvz. „meistras_dazymo“")
        if code in roles:
            raise RuleError(f"Rolė „{code}“ jau yra")
        name = (data.get("name") or "").strip()
        if not name:
            raise RuleError("Nurodykite rolės pavadinimą")
        base = roles.get(data.get("copy_from") or "")
        perms = _split(data.get("perms")) if "perms" in data else (_split(base["perms"]) if base else {"view"})
        scope = data.get("scope") or (base["scope"] if base else "all")
        if perms - set(PERMS):
            raise RuleError("Nežinoma teisė")
        con.execute("INSERT INTO roles (code, name, perms, scope, description, system, sort) VALUES (?,?,?,?,?,0,?)",
                    (code, name, ",".join(sorted(perms)), scope, (data.get("description") or "").strip(),
                     max([r["sort"] for r in roles.values()] or [0]) + 1))
        _access(con, by, "role", code, f"Nauja rolė {name}" + (f" (nukopijuota iš {base['name']})" if base else "")
                + ": " + (", ".join(PERM_LABEL[p] for p in sorted(perms, key=_order)) or "be teisių"))
        return code
    r = roles.get(code)
    if not r:
        raise NotFound("Rolės nėra")
    if not con.execute("SELECT 1 FROM roles WHERE code=?", (code,)).fetchone():
        ensure_roles(con)
    sets, vals, said = [], [], []
    if data.get("name") and data["name"].strip() != r["name"]:
        sets.append("name=?"); vals.append(data["name"].strip()); said.append(f"pavadinimas → {data['name'].strip()}")
    if "description" in data and (data["description"] or "") != r["description"]:
        sets.append("description=?"); vals.append(data["description"] or "")
    if "perms" in data:
        if code == "admin":
            raise RuleError("Administratoriaus rolė visada turi visas teises")
        new_p, old_p = _split(data["perms"]), _split(r["perms"])
        if new_p - set(PERMS):
            raise RuleError("Nežinoma teisė")
        if new_p != old_p:
            sets.append("perms=?"); vals.append(",".join(sorted(new_p)))
            plus = sorted(new_p - old_p, key=_order)
            minus = sorted(old_p - new_p, key=_order)
            said += ([f"+ {', '.join(PERM_LABEL[p] for p in plus)}"] if plus else []) + \
                    ([f"− {', '.join(PERM_LABEL[p] for p in minus)}"] if minus else [])
    if "scope" in data and data["scope"] != r["scope"]:
        if data["scope"] not in ("all", "own"):
            raise RuleError("Nežinoma apimtis")
        sets.append("scope=?"); vals.append(data["scope"])
        said.append("veiksmai tik savo baruose" if data["scope"] == "own" else "veiksmai visuose baruose")
    if not sets:
        return code
    con.execute(f"UPDATE roles SET {', '.join(sets)} WHERE code=?", (*vals, code))
    _keep_admin(con)
    if said:
        _access(con, by, "role", code, f"Rolė {r['name']}: " + "; ".join(said),
                {k: v for k, v in data.items() if k in ("perms", "scope", "name")})
    return code


def delete_role(con, by, code) -> None:
    r = _roles(con).get(code)
    if not r:
        raise NotFound("Rolės nėra")
    if r["system"]:
        raise RuleError("Įprastos rolės pašalinti negalima – galima pakeisti jos teises")
    n = con.execute("SELECT COUNT(*) FROM users WHERE role=?", (code,)).fetchone()[0]
    if n:
        raise RuleError(f"Rolę turi {n} vartotojai – pirma priskirkite jiems kitą")
    con.execute("DELETE FROM roles WHERE code=?", (code,))
    _access(con, by, "role", code, f"Rolė {r['name']} pašalinta")


def _order(p):
    keys = [k for _, _, ps in MODULES for k, _ in ps]
    return keys.index(p) if p in keys else 99


def access_log(con, target=None, target_id=None, limit=200) -> list[dict]:
    q = ("SELECT a.*, u.name AS by_name FROM access_log a LEFT JOIN users u ON u.id=a.by_id")
    args = []
    if target:
        q += " WHERE a.target=?" + (" AND a.target_id=?" if target_id is not None else "")
        args = [target] + ([str(target_id)] if target_id is not None else [])
    return db.rows(con.execute(q + " ORDER BY a.at DESC, a.id DESC LIMIT ?", (*args, limit)))


def describe(con, user: dict) -> list[dict]:
    """Ką vartotojas mato ir gali – pagal modulius, žmonių kalba; iš kur
    kiekviena teisė (rolė / papildomai) ir kur ji galioja."""
    load_perms(con, user)
    role = _roles(con).get(user["role"])
    from_role = set(PERMS) if user["role"] == "admin" else _split(role["perms"] if role else "")
    eff, add, rem = perms_of(user), _split(user.get("perm_add")), _split(user.get("perm_remove"))
    where = json.loads(user.get("centres") or "[]")
    out = []
    for key, label, ps in MODULES:
        items = []
        for p, pl in ps:
            if p not in eff and p not in rem:
                continue
            scoped = p in SCOPED and (p == "execute" or scope_of(user) == "own") and where
            items.append({"perm": p, "label": pl, "description": PERMS[p], "on": p in eff,
                          "source": "atimta" if p in rem else "papildomai" if p in add and p not in from_role else "rolė",
                          "where": ", ".join(where) if scoped else ("visi barai" if p in SCOPED else "")})
        out.append({"module": key, "label": label, "items": items})
    return out


def _pin_user(con, pin) -> dict | None:
    u = db.row(con.execute("SELECT * FROM users WHERE pin_hash=? AND active=1", (pin_key(con, pin),)))
    if u:
        return u
    # seni PBKDF2 PIN (iki 2026-10-25): tikrinami po vieną ir, radus,
    # perrašomi nauju raktu – taip seni įrašai išnyksta patys
    for r in db.rows(con.execute("SELECT * FROM users WHERE pin_hash LIKE 'pbkdf2$%' AND active=1")):
        if check_secret(pin, r["pin_hash"]):
            con.execute("UPDATE users SET pin_hash=? WHERE id=?", (pin_key(con, pin), r["id"]))
            return r
    return None


def _pin_taken(con, pin, exclude=None) -> bool:
    u = _pin_user(con, pin)
    return bool(u and u["id"] != exclude)


def login(con, hours: int, login_name=None, password=None, pin=None) -> tuple[str, dict]:
    """Grąžina (žetoną, vartotoją). Klaida visada ta pati – neišduodame, ar
    vartotojas egzistuoja."""
    user = None
    if pin:
        user = _pin_user(con, str(pin))
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
    return load_perms(con, r)


def can_centre(user: dict, centre_code: str, area_code: str | None = None) -> bool:
    """Vartotojui priskirti kodai gali būti centrų (SV-01) arba barų (SVB):
    baro meistrui ar suvirintojui užtenka priskirti barą, ir nauji to baro
    centrai jam atsiranda patys."""
    allowed = json.loads(user.get("centres") or "[]")
    return not allowed or centre_code in allowed or bool(area_code and area_code in allowed)


def _th(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()
