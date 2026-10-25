"""Užduotys, darbo centrų eilės ir vykdymas terminale.

Užduotis – viena mazgo maršruto operacija viename darbo centre
(pvz. „Rėmas 100 · Suvirinimas · 4 vnt.“). Taisyklės, kada ją galima pradėti,
gyvena vienoje vietoje – `block_reason`: jos klausia ir terminalas (ką rodyti),
ir serveris (ar leisti). Dvi vietos reikštų, kad ekranas ir serveris gali
atsakyti skirtingai.
"""

from __future__ import annotations

from .. import db
from . import NotFound, RuleError, components
from .projects import PHASE_LABEL

PAUSE_REASONS = [
    ("medziaga", "Trūksta medžiagos ar detalių"),
    ("gedimas", "Įrangos gedimas"),
    ("kokybe", "Kokybės klausimas"),
    ("laukiama", "Laukiama ankstesnės operacijos"),
    ("brezinys", "Neaiškus brėžinys"),
    ("irankiai", "Įrankiai, derinimas"),
    ("pertrauka", "Pertrauka"),
    ("pamaina", "Pamainos pabaiga"),
    ("kita", "Kita"),
]
PAUSE_LABEL = dict(PAUSE_REASONS)

# Centro rūšis pasako, kurio projekto etapo darbas vyksta – pirmas pradėtas
# darbas tą etapą pažymi „vykdoma“, tad projekto eiga matoma be ataskaitų.
CENTRE_PHASE = {"surinkimas": "surinkimas", "elektra": "surinkimas", "programavimas": "programavimas",
                "testavimas": "testavimas"}


def _task(con, task_id) -> dict:
    t = db.row(con.execute(
        "SELECT t.*, c.code AS centre_code, c.name AS centre_name, c.kind AS centre_kind, "
        "c.strict_order, ar.code AS area_code, a.code AS assembly_code, a.name AS assembly_name, "
        "p.code AS project_code, p.name AS project_name "
        "FROM tasks t JOIN work_centres c ON c.id=t.centre_id JOIN assemblies a ON a.id=t.assembly_id "
        "LEFT JOIN areas ar ON ar.id=c.area_id "
        "JOIN projects p ON p.id=t.project_id WHERE t.id=?", (task_id,)))
    if not t:
        raise NotFound("Užduoties nėra")
    return t


# ---------- kūrimas ir keitimas ----------

def create_task(con, by, data: dict) -> int:
    for k in ("project_id", "assembly_id", "centre_id", "name"):
        if not data.get(k):
            raise RuleError(f"Trūksta lauko: {k}")
    seq = data.get("seq")
    if seq is None:
        seq = con.execute("SELECT COALESCE(MAX(seq),0)+10 FROM tasks WHERE assembly_id=?",
                          (data["assembly_id"],)).fetchone()[0]
    pos = con.execute("SELECT COALESCE(MAX(queue_pos),0)+1 FROM tasks WHERE centre_id=?",
                      (data["centre_id"],)).fetchone()[0]
    cur = con.execute(
        "INSERT INTO tasks (project_id, assembly_id, centre_id, seq, name, part_no, qty_plan, norm_min, "
        "drawing_no, drawing_rev, queue_pos, created) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        (data["project_id"], data["assembly_id"], data["centre_id"], int(seq), data["name"],
         data.get("part_no", ""), int(data.get("qty_plan") or 1), float(data.get("norm_min") or 0),
         data.get("drawing_no", ""), data.get("drawing_rev", ""), pos, db.now()))
    db.log_event(con, by, "task", cur.lastrowid, "create", data)
    return cur.lastrowid


def update_task(con, by, task_id, data: dict) -> None:
    t = _task(con, task_id)
    vals = {k: data[k] for k in ("name", "part_no", "qty_plan", "norm_min", "drawing_no", "drawing_rev", "seq")
            if k in data}
    if "centre_id" in data and data["centre_id"] != t["centre_id"]:
        if t["status"] != "laukia" or _work_seconds(con, task_id) > 0:
            raise RuleError("Pradėtos užduoties perkelti į kitą centrą negalima")
        vals["centre_id"] = data["centre_id"]
        vals["queue_pos"] = con.execute("SELECT COALESCE(MAX(queue_pos),0)+1 FROM tasks WHERE centre_id=?",
                                        (data["centre_id"],)).fetchone()[0]
        vals["approved"] = 0
    if vals:
        con.execute(f"UPDATE tasks SET {', '.join(k + '=?' for k in vals)} WHERE id=?", (*vals.values(), task_id))
        db.log_event(con, by, "task", task_id, "update", vals)


def delete_task(con, by, task_id) -> None:
    _task(con, task_id)
    if con.execute("SELECT 1 FROM intervals WHERE task_id=?", (task_id,)).fetchone():
        raise RuleError("Užduotis jau vykdyta – jos ištrinti negalima")
    con.execute("DELETE FROM tasks WHERE id=?", (task_id,))
    db.log_event(con, by, "task", task_id, "delete")


# ---------- eilė ----------

def _open_tasks(con, centre_id) -> list[dict]:
    return db.rows(con.execute(
        "SELECT t.*, a.code AS assembly_code, a.name AS assembly_name, p.code AS project_code, "
        "p.name AS project_name, p.priority, p.due_date "
        "FROM tasks t JOIN assemblies a ON a.id=t.assembly_id JOIN projects p ON p.id=t.project_id "
        "WHERE t.centre_id=? AND t.status!='baigta' ORDER BY t.queue_pos, t.id", (centre_id,)))


def move(con, by, task_id, where: str) -> None:
    """Perkelia užduotį centro eilėje: up, down, top."""
    t = _task(con, task_id)
    if t["status"] == "baigta":
        raise RuleError("Atlikta užduotis eilėje nedalyvauja")
    ids = [x["id"] for x in _open_tasks(con, t["centre_id"])]
    i = ids.index(task_id)
    if where == "up" and i > 0:
        ids[i - 1], ids[i] = ids[i], ids[i - 1]
    elif where == "down" and i < len(ids) - 1:
        ids[i + 1], ids[i] = ids[i], ids[i + 1]
    elif where == "top":
        ids.insert(0, ids.pop(i))
    else:
        return
    for pos, tid in enumerate(ids, start=1):
        con.execute("UPDATE tasks SET queue_pos=? WHERE id=?", (pos, tid))
    db.log_event(con, by, "task", task_id, "move", {"where": where})


def approve_queue(con, by, centre_id) -> int:
    """Planuotojas patvirtina centro eilę: terminalas mato tik patvirtintas."""
    n = con.execute("UPDATE tasks SET approved=1 WHERE centre_id=? AND status!='baigta' AND approved=0",
                    (centre_id,)).rowcount
    db.log_event(con, by, "centre", centre_id, "approve_queue", {"count": n})
    return n


# ---------- taisyklės ----------

def current_revision(con, drawing_no) -> str | None:
    if not drawing_no:
        return None
    r = con.execute("SELECT revision FROM drawings WHERE number=? ORDER BY uploaded_at DESC, id DESC LIMIT 1",
                    (drawing_no,)).fetchone()
    return r[0] if r else None


def _running_in_centre(con, centre_id, exclude=None) -> dict | None:
    return db.row(con.execute(
        "SELECT t.id, t.name, t.status, a.code AS assembly_code FROM tasks t "
        "JOIN assemblies a ON a.id=t.assembly_id "
        "WHERE t.centre_id=? AND t.status IN ('vykdoma','pristabdyta') AND t.id!=? LIMIT 1",
        (centre_id, exclude or 0)))


def block_reason(con, t: dict) -> str | None:
    """Kodėl užduoties dabar pradėti negalima; None – galima."""
    if t["status"] == "baigta":
        return "Užduotis jau atlikta"
    if t["status"] in ("vykdoma", "pristabdyta"):
        return None
    if not t["approved"]:
        return "Eilė dar nepatvirtinta planuotojo"
    busy = _running_in_centre(con, t["centre_id"], exclude=t["id"])
    if busy:
        if busy["status"] == "pristabdyta":
            return f"Pristabdyta užduotis {busy['assembly_code']} · {busy['name']} – pirma ją pratęskite arba baikite"
        return f"Centre jau vykdoma {busy['assembly_code']} · {busy['name']}"
    if t.get("strict_order", 1):
        first = db.row(con.execute(
            "SELECT t.id, t.name, a.code AS assembly_code FROM tasks t JOIN assemblies a ON a.id=t.assembly_id "
            "WHERE t.centre_id=? AND t.approved=1 AND t.status!='baigta' ORDER BY t.queue_pos, t.id LIMIT 1",
            (t["centre_id"],)))
        if first and first["id"] != t["id"]:
            return f"Pirma eilėje: {first['assembly_code']} · {first['name']}"
    # Ankstesnė maršruto operacija turi būti atlikta arba perdavusi bent dalį
    # kiekio – vienetinėje gamyboje dalinis perdavimas yra kasdienybė.
    up = db.row(con.execute(
        "SELECT t.name, c.code AS centre_code FROM tasks t JOIN work_centres c ON c.id=t.centre_id "
        "WHERE t.assembly_id=? AND t.seq<? AND t.status!='baigta' AND t.qty_good=0 "
        "ORDER BY t.seq DESC LIMIT 1", (t["assembly_id"], t["seq"])))
    if up:
        return f"Laukiama ankstesnės operacijos: {up['centre_code']} · {up['name']}"
    # pirmoji mazgo operacija laukia mazgų, nuo kurių jis priklauso
    if not con.execute("SELECT 1 FROM tasks WHERE assembly_id=? AND seq<?", (t["assembly_id"], t["seq"])).fetchone():
        req = con.execute("SELECT requires, project_id FROM assemblies WHERE id=?", (t["assembly_id"],)).fetchone()
        codes = [c for c in (req["requires"] if req else "").split(",") if c]
        if codes:
            waiting = [r[0] for r in con.execute(
                f"SELECT DISTINCT a.code FROM assemblies a JOIN tasks x ON x.assembly_id=a.id "
                f"WHERE a.project_id=? AND a.code IN ({','.join('?' * len(codes))}) AND x.status!='baigta' "
                f"ORDER BY a.code", (req["project_id"], *codes))]
            if waiting:
                return f"Laukiama mazgų: {', '.join(waiting)}"
    cur = current_revision(con, t["drawing_no"])
    if cur and t["drawing_rev"] and cur != t["drawing_rev"]:
        return f"Brėžinio {t['drawing_no']} revizija pasikeitė: {t['drawing_rev']} → {cur}. Reikia meistro patvirtinimo"
    return None


# ---------- vykdymas ----------

def _open_interval(con, task_id):
    return db.row(con.execute("SELECT * FROM intervals WHERE task_id=? AND end IS NULL", (task_id,)))


def _open_pause(con, task_id):
    return db.row(con.execute("SELECT * FROM pauses WHERE task_id=? AND end IS NULL", (task_id,)))


def _check_user(user, t):
    from .auth import can_centre

    if not can_centre(user, t["centre_code"], t.get("area_code")):
        raise RuleError("Šis darbo centras jums nepriskirtas")


def start(con, user, task_id) -> None:
    t = _task(con, task_id)
    _check_user(user, t)
    if t["status"] == "vykdoma":
        raise RuleError("Užduotis jau vykdoma")
    if t["status"] == "pristabdyta":
        raise RuleError("Užduotis pristabdyta – spauskite „Tęsti“")
    why = block_reason(con, t)
    if why:
        raise RuleError(why)
    now = db.now()
    con.execute("INSERT INTO intervals (task_id, user_id, start) VALUES (?,?,?)", (task_id, user["id"], now))
    con.execute("UPDATE tasks SET status='vykdoma' WHERE id=?", (task_id,))
    con.execute("UPDATE projects SET status='vykdomas' WHERE id=? AND status='krepselis'", (t["project_id"],))
    _touch_phase(con, user["id"], t)
    db.log_event(con, user["id"], "task", task_id, "start")


def _touch_phase(con, user_id, t):
    kind = CENTRE_PHASE.get(t["centre_kind"], "gamyba")
    ph = db.row(con.execute(
        "SELECT id FROM phases WHERE project_id=? AND kind=? AND status='planuota' "
        "AND (assembly_id=? OR assembly_id IS NULL) ORDER BY assembly_id IS NULL LIMIT 1",
        (t["project_id"], kind, t["assembly_id"])))
    if ph:
        con.execute("UPDATE phases SET status='vykdoma', actual_start=? WHERE id=?", (db.now(), ph["id"]))
        db.log_event(con, user_id, "phase", ph["id"], "status", {"status": "vykdoma", "auto": True})


def pause(con, user, task_id, reason, note="") -> None:
    t = _task(con, task_id)
    _check_user(user, t)
    if t["status"] != "vykdoma":
        raise RuleError("Pristabdyti galima tik vykdomą užduotį")
    if reason not in PAUSE_LABEL:
        raise RuleError("Pasirinkite pauzės priežastį")
    if reason == "kita" and not (note or "").strip():
        raise RuleError("Priežasčiai „Kita“ būtina pastaba")
    now = db.now()
    con.execute("UPDATE intervals SET end=? WHERE task_id=? AND end IS NULL", (now, task_id))
    con.execute("INSERT INTO pauses (task_id, user_id, start, reason, note) VALUES (?,?,?,?,?)",
                (task_id, user["id"], now, reason, note or ""))
    con.execute("UPDATE tasks SET status='pristabdyta' WHERE id=?", (task_id,))
    db.log_event(con, user["id"], "task", task_id, "pause", {"reason": reason, "note": note})


def resume(con, user, task_id) -> None:
    t = _task(con, task_id)
    _check_user(user, t)
    if t["status"] != "pristabdyta":
        raise RuleError("Užduotis nepristabdyta")
    now = db.now()
    con.execute("UPDATE pauses SET end=? WHERE task_id=? AND end IS NULL", (now, task_id))
    con.execute("INSERT INTO intervals (task_id, user_id, start) VALUES (?,?,?)", (task_id, user["id"], now))
    con.execute("UPDATE tasks SET status='vykdoma' WHERE id=?", (task_id,))
    db.log_event(con, user["id"], "task", task_id, "resume")


def stop(con, user, task_id, good: int, scrap: int = 0, finish: bool | None = None) -> dict:
    """Baigia darbo intervalą ir įrašo kiekį.

    `finish=None` – užduotis baigiama, kai visas planuotas kiekis padarytas
    (gera + brokas); kitaip ji lieka eilėje savo vietoje su likusiu kiekiu.
    Grąžina naują būseną ir ar siūlyti neatitikties įrašą (brokas > 0).
    """
    t = _task(con, task_id)
    _check_user(user, t)
    if t["status"] not in ("vykdoma", "pristabdyta"):
        raise RuleError("Užduotis nevykdoma")
    good, scrap = int(good or 0), int(scrap or 0)
    if good < 0 or scrap < 0:
        raise RuleError("Kiekis negali būti neigiamas")
    now = db.now()
    con.execute("UPDATE intervals SET end=? WHERE task_id=? AND end IS NULL", (now, task_id))
    con.execute("UPDATE pauses SET end=? WHERE task_id=? AND end IS NULL", (now, task_id))
    total_good, total_scrap = t["qty_good"] + good, t["qty_scrap"] + scrap
    if finish is None:
        finish = total_good + total_scrap >= t["qty_plan"]
    status = "baigta" if finish else "laukia"
    con.execute("UPDATE tasks SET status=?, qty_good=?, qty_scrap=? WHERE id=?",
                (status, total_good, total_scrap, task_id))
    db.log_event(con, user["id"], "task", task_id, "stop",
                 {"good": good, "scrap": scrap, "status": status})
    return {"status": status, "suggest_ncr": scrap > 0, "qty_good": total_good, "qty_scrap": total_scrap}


def ack_revision(con, user, task_id) -> None:
    t = _task(con, task_id)
    cur = current_revision(con, t["drawing_no"])
    if not cur or cur == t["drawing_rev"]:
        raise RuleError("Revizija nepasikeitė")
    con.execute("UPDATE tasks SET drawing_rev=? WHERE id=?", (cur, task_id))
    db.log_event(con, user["id"], "task", task_id, "ack_revision", {"from": t["drawing_rev"], "to": cur})


# ---------- laikai ----------

def _secs(start, end, now=None) -> float:
    a = db.parse_ts(start)
    b = db.parse_ts(end or now or db.now())
    return max(0.0, (b - a).total_seconds())


def _work_seconds(con, task_id, closed_only=False) -> float:
    """Darbo laikas. `closed_only` – be atviro intervalo: naršyklė jį prideda
    pati ir skaičiuoja kas sekundę, kitaip jis būtų įskaičiuotas du kartus."""
    q = "SELECT start, end FROM intervals WHERE task_id=?" + (" AND end IS NOT NULL" if closed_only else "")
    return sum(_secs(r["start"], r["end"]) for r in con.execute(q, (task_id,)))


# ---------- terminalo vaizdas ----------

def terminal_view(con, centre: dict) -> dict:
    """Viskas, ką rodo darbo centro terminalas."""
    now = db.now()
    tasks = _open_tasks(con, centre["id"])
    running = None
    queue = []
    unapproved = 0
    for t in tasks:
        t["centre_code"], t["strict_order"] = centre["code"], centre["strict_order"]
        cur_rev = current_revision(con, t["drawing_no"])
        t["drawing_current"] = cur_rev
        t["work_s"] = round(_work_seconds(con, t["id"], closed_only=True))
        # įspėjimas, ne draudimas: dalį darbo dažnai galima pradėti ir be
        # visų pirktinių komponentų, sprendžia meistras
        t["components_missing"] = components.missing_for_assembly(con, t["assembly_id"])
        if t["status"] in ("vykdoma", "pristabdyta"):
            iv = _open_interval(con, t["id"])
            pz = _open_pause(con, t["id"])
            t["since"] = (iv or pz or {}).get("start")
            if pz:
                pz["reason_label"] = PAUSE_LABEL.get(pz["reason"], pz["reason"])
            t["pause"] = pz
            running = t
            continue
        if not t["approved"]:
            unapproved += 1
            continue
        t["lock"] = block_reason(con, t)
        queue.append(t)
    done = db.rows(con.execute(
        "SELECT t.id, t.name, t.qty_good, t.qty_scrap, a.code AS assembly_code, p.code AS project_code "
        "FROM tasks t JOIN assemblies a ON a.id=t.assembly_id JOIN projects p ON p.id=t.project_id "
        "WHERE t.centre_id=? AND t.status='baigta' AND substr(("
        "  SELECT MAX(end) FROM intervals i WHERE i.task_id=t.id),1,10)=substr(?,1,10) "
        "ORDER BY t.id DESC LIMIT 20", (centre["id"], now)))
    return {"centre": centre, "now": now, "running": running, "queue": queue,
            "unapproved": unapproved, "done_today": done,
            "pause_reasons": [{"key": k, "label": v} for k, v in PAUSE_REASONS]}


def plan_view(con, centre: dict) -> list[dict]:
    """Planuotojo vaizdas: visa centro eilė su būsena ir blokavimo priežastimi."""
    out = []
    for t in _open_tasks(con, centre["id"]):
        t["strict_order"] = centre["strict_order"]
        t["lock"] = None if t["status"] != "laukia" else block_reason(con, {**t, "approved": 1})
        t["components_missing"] = components.missing_for_assembly(con, t["assembly_id"])
        out.append(t)
    return out


def phase_label(kind):
    return PHASE_LABEL.get(kind, kind)
