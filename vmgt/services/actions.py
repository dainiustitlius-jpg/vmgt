"""Projekto komandos užduotys: biuro darbai su atsakingu, terminu ir statusais.

Tai ne cecho operacijos (`tasks`), o projektuotojų, technologų, pirkimų,
programuotojų ir vadovo darbai: „Išleisti mazgo 200 brėžinius“, „Gauti
užsakovo patvirtinimą“. Dalis jų gimsta susitikimuose (`meeting_id`).

Statusai keičiami tik leistinais perėjimais (`TRANSITIONS`), o kiekvienas
pakeitimas įrašomas į `action_log` – iš jo matoma visa užduoties istorija ir
skaičiuojama, kiek laiko užduotis laukė. Laukimui ir atšaukimui priežastis
būtina: be jos po savaitės niekas neprisimena, kodėl darbas stovi.
"""

from __future__ import annotations

from .. import db
from . import NotFound, RuleError

STATUSES = [
    ("nauja", "Nauja"),
    ("vykdoma", "Vykdoma"),
    ("laukia", "Laukia"),
    ("perziura", "Peržiūra"),
    ("atlikta", "Atlikta"),
    ("atsaukta", "Atšaukta"),
]
STATUS_LABEL = dict(STATUSES)
OPEN = ("nauja", "vykdoma", "laukia", "perziura")

TRANSITIONS = {
    "nauja": ("vykdoma", "laukia", "atsaukta"),
    "vykdoma": ("laukia", "perziura", "atlikta", "atsaukta"),
    "laukia": ("vykdoma", "atsaukta"),
    "perziura": ("vykdoma", "atlikta"),        # grąžinti taisyti arba priimti
    "atlikta": ("vykdoma",),                   # atidaryti iš naujo
    "atsaukta": ("nauja",),                    # atkurti
}
NEED_REASON = ("laukia", "atsaukta")
PRIORITIES = [(1, "Aukštas"), (2, "Vidutinis"), (3, "Žemas")]

_SELECT = ("SELECT x.*, p.code AS project_code, p.name AS project_name, u.name AS owner_name, "
           "a.code AS assembly_code, m.title AS meeting_title, m.held_at AS meeting_at "
           "FROM actions x JOIN projects p ON p.id=x.project_id LEFT JOIN users u ON u.id=x.owner_id "
           "LEFT JOIN assemblies a ON a.id=x.assembly_id LEFT JOIN meetings m ON m.id=x.meeting_id")


def decorate(x: dict, today: str) -> dict:
    x["status_label"] = STATUS_LABEL.get(x["status"], x["status"])
    x["overdue"] = bool(x["status"] in OPEN and x["due_date"] and x["due_date"] < today)
    x["next"] = [{"key": s, "label": STATUS_LABEL[s], "reason": s in NEED_REASON}
                 for s in TRANSITIONS.get(x["status"], ())]
    return x


def _today():
    return db.now()[:10]


def get(con, action_id) -> dict:
    x = db.row(con.execute(_SELECT + " WHERE x.id=?", (action_id,)))
    if not x:
        raise NotFound("Užduoties nėra")
    return decorate(x, _today())


def list_actions(con, project_id=None, owner_id=None, status=None, meeting_id=None) -> list[dict]:
    q, args = _SELECT + " WHERE 1=1", []
    if project_id:
        q += " AND x.project_id=?"; args.append(project_id)
    if owner_id:
        q += " AND x.owner_id=?"; args.append(owner_id)
    if meeting_id:
        q += " AND x.meeting_id=?"; args.append(meeting_id)
    if status == "open":
        q += f" AND x.status IN ({','.join('?' * len(OPEN))})"; args += list(OPEN)
    elif status:
        q += " AND x.status=?"; args.append(status)
    q += " ORDER BY x.status IN ('atlikta','atsaukta'), x.due_date IS NULL, x.due_date, x.priority, x.id"
    today = _today()
    return [decorate(x, today) for x in db.rows(con.execute(q, args))]


def can_edit(user: dict, x: dict) -> bool:
    """Visas užduotis keičia turintys teisę `actions`; savo užduoties statusą
    ir komentarus – pats atsakingasis, kad ir kokia jo rolė."""
    from .auth import perms_of
    return "actions" in perms_of(user) or x.get("owner_id") == user["id"]


def create(con, user_id, data: dict, meeting_id=None) -> int:
    if not data.get("project_id") or not (data.get("title") or "").strip():
        raise RuleError("Reikia projekto ir užduoties pavadinimo")
    now = db.now()
    cur = con.execute(
        "INSERT INTO actions (project_id, assembly_id, phase_id, meeting_id, title, description, owner_id, priority, "
        "due_date, created_by, created, updated) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        (data["project_id"], data.get("assembly_id") or None, data.get("phase_id") or None, meeting_id,
         data["title"].strip(), data.get("description", ""), data.get("owner_id") or None,
         int(data.get("priority") or 2), data.get("due_date") or None, user_id, now, now))
    aid = cur.lastrowid
    con.execute("INSERT INTO action_log (action_id, user_id, at, kind, to_status, text) VALUES (?,?,?,?,?,?)",
                (aid, user_id, now, "status", "nauja", "sukurta" + (" susitikime" if meeting_id else "")))
    db.log_event(con, user_id, "action", aid, "create", {k: data.get(k) for k in ("title", "owner_id", "due_date")})
    return aid


def update(con, user, action_id, data: dict) -> None:
    x = get(con, action_id)
    if not can_edit(user, x):
        raise RuleError("Šią užduotį keisti gali jos atsakingasis arba projekto vadovas")
    fields = ("title", "description", "owner_id", "priority", "due_date", "assembly_id", "phase_id")
    vals = {k: (data[k] if data[k] != "" else None) for k in fields if k in data}
    if "title" in vals and not (vals["title"] or "").strip():
        raise RuleError("Pavadinimas negali būti tuščias")
    if not vals:
        return
    changes = [f"{k}: {x.get(k) or '—'} → {v or '—'}" for k, v in vals.items() if str(x.get(k) or "") != str(v or "")]
    con.execute(f"UPDATE actions SET {', '.join(k + '=?' for k in vals)}, updated=? WHERE id=?",
                (*vals.values(), db.now(), action_id))
    if changes:
        con.execute("INSERT INTO action_log (action_id, user_id, at, kind, text) VALUES (?,?,?,?,?)",
                    (action_id, user["id"], db.now(), "edit", "; ".join(changes)))


def set_status(con, user, action_id, status: str, reason: str = "") -> dict:
    x = get(con, action_id)
    if not can_edit(user, x):
        raise RuleError("Statusą keisti gali užduoties atsakingasis arba projekto vadovas")
    if status not in TRANSITIONS.get(x["status"], ()):
        raise RuleError(f"Iš „{x['status_label']}“ į „{STATUS_LABEL.get(status, status)}“ pereiti negalima")
    reason = (reason or "").strip()
    if status in NEED_REASON and not reason:
        raise RuleError(f"Nurodykite priežastį: kodėl užduotis {'laukia' if status == 'laukia' else 'atšaukiama'}")
    now = db.now()
    sets = {"status": status, "updated": now, "wait_reason": reason if status == "laukia" else ""}
    if status == "vykdoma" and not x["started_at"]:
        sets["started_at"] = now
    if status == "atlikta":
        sets["done_at"] = now
    elif x["status"] == "atlikta":
        sets["done_at"] = None
    con.execute(f"UPDATE actions SET {', '.join(k + '=?' for k in sets)} WHERE id=?", (*sets.values(), action_id))
    con.execute("INSERT INTO action_log (action_id, user_id, at, kind, from_status, to_status, text) "
                "VALUES (?,?,?,?,?,?,?)", (action_id, user["id"], now, "status", x["status"], status, reason))
    db.log_event(con, user["id"], "action", action_id, "status", {"from": x["status"], "to": status})
    return get(con, action_id)


def comment(con, user, action_id, text: str) -> None:
    x = get(con, action_id)
    from .auth import perms_of
    if "view" not in perms_of(user) and x["owner_id"] != user["id"]:
        raise RuleError("Komentuoti gali projekto komanda")
    if not (text or "").strip():
        raise RuleError("Komentaras tuščias")
    con.execute("INSERT INTO action_log (action_id, user_id, at, kind, text) VALUES (?,?,?,?,?)",
                (action_id, user["id"], db.now(), "comment", text.strip()))


def history(con, action_id) -> list[dict]:
    out = db.rows(con.execute(
        "SELECT l.*, u.name AS user_name FROM action_log l LEFT JOIN users u ON u.id=l.user_id "
        "WHERE l.action_id=? ORDER BY l.at, l.id", (action_id,)))
    for h in out:
        h["from_label"] = STATUS_LABEL.get(h["from_status"] or "", h["from_status"])
        h["to_label"] = STATUS_LABEL.get(h["to_status"] or "", h["to_status"])
    return out


def wait_seconds(con, action_id, now: str | None = None) -> float:
    """Kiek iš viso užduotis išbuvo „Laukia“ – iš būsenų istorijos."""
    now = now or db.now()
    total, since = 0.0, None
    for h in db.rows(con.execute("SELECT at, to_status FROM action_log WHERE action_id=? AND kind='status' "
                                 "ORDER BY at, id", (action_id,))):
        if h["to_status"] == "laukia" and since is None:
            since = h["at"]
        elif h["to_status"] != "laukia" and since is not None:
            total += (db.parse_ts(h["at"]) - db.parse_ts(since)).total_seconds()
            since = None
    if since is not None:
        total += (db.parse_ts(now) - db.parse_ts(since)).total_seconds()
    return total
