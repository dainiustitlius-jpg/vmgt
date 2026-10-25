"""Projekto komandos užduotys: biuro darbai su atsakingu, terminu ir statusais.

Tai ne cecho operacijos (`tasks`), o projektuotojų, technologų, pirkimų,
programuotojų ir vadovo darbai: „Išleisti mazgo 200 brėžinius“, „Gauti
užsakovo patvirtinimą“. Dalis jų gimsta susitikimuose (`meeting_id`).

Užduotis be projekto – **asmeninė**: ją mato ir keičia tik atsakingasis,
kitam priskirti ją galima tik susiejus su projektu (tada ją mato komanda).
Kiekvienas savo užduotis – ir asmenines, ir projektų – planuojasi savaitės
plane (`plan_date`, `estimate_h`, `week`).

Statusai keičiami tik leistinais perėjimais (`TRANSITIONS`), o kiekvienas
pakeitimas įrašomas į `action_log` – iš jo matoma visa užduoties istorija ir
skaičiuojama, kiek laiko užduotis laukė. Laukimui ir atšaukimui priežastis
būtina: be jos po savaitės niekas neprisimena, kodėl darbas stovi.
"""

from __future__ import annotations

from datetime import date, timedelta

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
DAY_HOURS = 8           # vienos dienos planas, kad perkrauta diena matytųsi iškart
WEEKDAYS = ["Pirmadienis", "Antradienis", "Trečiadienis", "Ketvirtadienis", "Penktadienis", "Šeštadienis",
            "Sekmadienis"]


def _transitions(x) -> tuple:
    # asmeninę užduotį galima tiesiog pažymėti atlikta – tai darbų sąrašas sau,
    # o projekto užduotis pirma turi būti pradėta (matoma, kada pradėta)
    t = TRANSITIONS.get(x["status"], ())
    return t + ("atlikta",) if x.get("project_id") is None and x["status"] == "nauja" else t

_SELECT = ("SELECT x.*, p.code AS project_code, p.name AS project_name, u.name AS owner_name, "
           "a.code AS assembly_code, m.title AS meeting_title, m.held_at AS meeting_at "
           "FROM actions x LEFT JOIN projects p ON p.id=x.project_id LEFT JOIN users u ON u.id=x.owner_id "
           "LEFT JOIN assemblies a ON a.id=x.assembly_id LEFT JOIN meetings m ON m.id=x.meeting_id")


def decorate(x: dict, today: str) -> dict:
    x["status_label"] = STATUS_LABEL.get(x["status"], x["status"])
    x["overdue"] = bool(x["status"] in OPEN and x["due_date"] and x["due_date"] < today)
    x["personal"] = x["project_id"] is None
    x["next"] = [{"key": s, "label": STATUS_LABEL[s], "reason": s in NEED_REASON} for s in _transitions(x)]
    return x


def _today():
    return db.now()[:10]


def get(con, action_id) -> dict:
    x = db.row(con.execute(_SELECT + " WHERE x.id=?", (action_id,)))
    if not x:
        raise NotFound("Užduoties nėra")
    return decorate(x, _today())


def list_actions(con, project_id=None, owner_id=None, status=None, meeting_id=None, viewer_id=None) -> list[dict]:
    """`viewer_id` – kas žiūri: asmeninės užduotys matomos tik jų atsakingajam."""
    q, args = _SELECT + " WHERE (x.project_id IS NOT NULL OR x.owner_id=?)", [viewer_id or -1]
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
    if x.get("project_id") is None:
        return x.get("owner_id") == user["id"]
    return "actions" in perms_of(user) or x.get("owner_id") == user["id"]


def _visible(con, user, action_id) -> dict:
    x = get(con, action_id)
    if x["personal"] and x["owner_id"] != user["id"]:
        raise NotFound("Užduoties nėra")        # svetima asmeninė – lyg jos nebūtų
    return x


def can_see(user: dict, x: dict) -> bool:
    from .auth import perms_of
    if x.get("project_id") is None or "view" not in perms_of(user):
        return x.get("owner_id") == user["id"]
    return True


def create(con, user_id, data: dict, meeting_id=None) -> int:
    """Be projekto – asmeninė užduotis, ji visada kūrėjo."""
    if not (data.get("title") or "").strip():
        raise RuleError("Reikia užduoties pavadinimo")
    pid = data.get("project_id") or None
    owner = (data.get("owner_id") or None) if pid else user_id
    now = db.now()
    cur = con.execute(
        "INSERT INTO actions (project_id, assembly_id, phase_id, meeting_id, title, description, owner_id, priority, "
        "due_date, created_by, created, updated, plan_date, estimate_h) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (pid, data.get("assembly_id") or None, data.get("phase_id") or None, meeting_id,
         data["title"].strip(), data.get("description", ""), owner,
         int(data.get("priority") or 2), data.get("due_date") or None, user_id, now, now,
         data.get("plan_date") or None, _hours(data.get("estimate_h"))))
    aid = cur.lastrowid
    con.execute("INSERT INTO action_log (action_id, user_id, at, kind, to_status, text) VALUES (?,?,?,?,?,?)",
                (aid, user_id, now, "status", "nauja", "sukurta" + (" susitikime" if meeting_id else "")))
    db.log_event(con, user_id, "action", aid, "create", {k: data.get(k) for k in ("title", "owner_id", "due_date")})
    return aid


def update(con, user, action_id, data: dict) -> None:
    x = _visible(con, user, action_id)
    if not can_edit(user, x):
        raise RuleError("Šią užduotį keisti gali jos atsakingasis arba projekto vadovas")
    fields = ("title", "description", "owner_id", "priority", "due_date", "assembly_id", "phase_id", "project_id",
              "plan_date", "estimate_h")
    vals = {k: (data[k] if data[k] != "" else None) for k in fields if k in data}
    if "title" in vals and not (vals["title"] or "").strip():
        raise RuleError("Pavadinimas negali būti tuščias")
    if "estimate_h" in vals:
        vals["estimate_h"] = _hours(vals["estimate_h"])
    if vals.get("plan_date") and vals["plan_date"] < _today() and vals["plan_date"] != x["plan_date"]:
        raise RuleError("Suplanuoti į praeitį negalima")
    # planas – atsakingojo reikalas: kitas jo dienos nedėlioja
    if any(k in vals for k in ("plan_date", "estimate_h")) and x["owner_id"] != user["id"]:
        raise RuleError("Darbų dieną planuoja pats atsakingasis")
    pid = vals.get("project_id", x["project_id"])
    if x["project_id"] and "project_id" in vals and vals["project_id"] != x["project_id"]:
        raise RuleError("Projekto užduoties perkelti į kitą projektą ar paversti asmenine negalima")
    if pid and not x["project_id"]:
        from .auth import perms_of
        if "view" not in perms_of(user):
            raise RuleError("Susieti su projektu gali projektų komanda")
    owner = vals.get("owner_id", x["owner_id"])
    if not pid and owner != user["id"]:
        raise RuleError("Kolegai priskirti galima tik projekto užduotį – pirma pasirinkite projektą")
    if owner != x["owner_id"] and "plan_date" not in vals:
        vals["plan_date"] = None            # kito žmogaus planas – jo paties
    if not vals:
        return
    changes = [f"{k}: {x.get(k) or '—'} → {v or '—'}" for k, v in vals.items() if str(x.get(k) or "") != str(v or "")]
    con.execute(f"UPDATE actions SET {', '.join(k + '=?' for k in vals)}, updated=? WHERE id=?",
                (*vals.values(), db.now(), action_id))
    if changes:
        con.execute("INSERT INTO action_log (action_id, user_id, at, kind, text) VALUES (?,?,?,?,?)",
                    (action_id, user["id"], db.now(), "edit", "; ".join(changes)))


def set_status(con, user, action_id, status: str, reason: str = "") -> dict:
    x = _visible(con, user, action_id)
    if not can_edit(user, x):
        raise RuleError("Statusą keisti gali užduoties atsakingasis arba projekto vadovas")
    if status not in _transitions(x):
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
    x = _visible(con, user, action_id)
    if not can_see(user, x):
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


def _hours(v) -> float | None:
    if v in (None, ""):
        return None
    try:
        h = float(str(v).replace(",", "."))
    except ValueError:
        raise RuleError("Įvertis – valandos skaičiumi") from None
    if h < 0 or h > 200:
        raise RuleError("Įvertis turi būti nuo 0 iki 200 val.")
    return h


# ---------- asmeninis savaitės planas ----------

def week(con, user_id, start: date | None = None) -> dict:
    """Savaitės planas: neplanuotos, dienos ir vėlesnės. Neatlikta praėjusios
    dienos užduotis rodoma šiandien („perkelta iš …“) – planas neperrašomas,
    tad matoma, kiek kartų ir nuo kada ji stumiama."""
    today = date.fromisoformat(_today())
    # savaitgalį planas prasideda pirmadienį (kaip resursų apkrovoje)
    work_day = today + timedelta(days=(7 - today.weekday()) % 7 if today.weekday() >= 5 else 0)
    start = start or work_day
    start = start - timedelta(days=start.weekday())
    end = start + timedelta(days=6)
    days = {start + timedelta(days=i): [] for i in range(7)}
    unplanned, later = [], []
    # atliktos – kurios atliktos arba buvo suplanuotos šią savaitę (savaitgalį
    # pažymėta atlikta pirmadienio užduotis neturi dingti iš pirmadienio)
    q = _SELECT + (" WHERE x.owner_id=? AND (x.status IN ({}) OR (x.status='atlikta' AND (substr(x.done_at,1,10) "
                   "BETWEEN ? AND ? OR x.plan_date BETWEEN ? AND ?))) "
                   "ORDER BY x.priority, x.due_date IS NULL, x.due_date, x.id").format(",".join("?" * len(OPEN)))
    for x in db.rows(con.execute(q, (user_id, *OPEN, *(start.isoformat(), end.isoformat()) * 2))):
        decorate(x, today.isoformat())
        pd = date.fromisoformat(x["plan_date"]) if x["plan_date"] else None
        if x["status"] == "atlikta":
            # atlikta rodoma tą dieną, kurią planuota (jei šią savaitę), kitaip – kurią atlikta
            d = pd if pd and start <= pd <= end else date.fromisoformat(x["done_at"][:10])
            days[d].append(x)
            continue
        x["rolled_from"] = x["plan_date"] if pd and pd < work_day else None
        x["late_plan"] = bool(pd and x["due_date"] and x["plan_date"] > x["due_date"])
        eff = (pd if pd >= work_day else work_day) if pd else None
        if eff is None:
            unplanned.append(x)
        elif eff > end:
            later.append(x)
        elif eff >= start:
            days[eff].append(x)
        # suplanuota anksčiau už rodomą (būsimą) savaitę – matoma tos dienos savaitėje
    out = []
    for d, items in days.items():
        h = sum(x["estimate_h"] or 0 for x in items)
        out.append({"date": d.isoformat(), "label": WEEKDAYS[d.weekday()], "today": d == today,
                    "past": d < today, "weekend": d.weekday() >= 5, "hours": h, "capacity": DAY_HOURS,
                    "over": h > DAY_HOURS, "items": items})
    return {"start": start.isoformat(), "end": end.isoformat(), "today": today.isoformat(),
            "work_day": work_day.isoformat(), "days": out,
            "unplanned": unplanned, "later": later,
            "open": sum(1 for d in out for x in d["items"] if x["status"] != "atlikta") + len(unplanned) + len(later)}
