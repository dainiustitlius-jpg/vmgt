"""Projektų krepšelis, mazgai, etapai ir darbo centrai."""

from __future__ import annotations

from .. import db
from . import NotFound, RuleError

PHASE_KINDS = [
    ("projektavimas", "Projektavimas"),
    ("technologija", "Technologinis paruošimas"),
    ("komponentai", "Komponentų užsakymas"),
    ("gamyba", "Gamyba"),
    ("surinkimas", "Surinkimas"),
    ("programavimas", "Programavimas (PLC, robotai)"),
    ("testavimas", "Testavimas"),
]
PHASE_LABEL = dict(PHASE_KINDS)
PHASE_STATUSES = ("planuota", "vykdoma", "baigta")

PROJECT_STATUSES = [
    ("krepselis", "Krepšelyje"),
    ("vykdomas", "Vykdomas"),
    ("sustabdytas", "Sustabdytas"),
    ("baigtas", "Baigtas"),
]
PROJECT_LABEL = dict(PROJECT_STATUSES)

CENTRE_KINDS = [
    ("pjovimas", "Pjovimas"),
    ("lenkimas", "Lenkimas"),
    ("suvirinimas", "Suvirinimas"),
    ("mechaninis", "Mechaninis apdirbimas"),
    ("dazymas", "Dažymas"),
    ("surinkimas", "Surinkimas"),
    ("elektra", "Elektros surinkimas"),
    ("testavimas", "Testavimas"),
    ("kita", "Kita"),
]


# ---------- projektai ----------

def list_projects(con, include_done=False) -> list[dict]:
    q = "SELECT p.*, u.name AS manager_name FROM projects p LEFT JOIN users u ON u.id=p.manager_id"
    if not include_done:
        q += " WHERE p.status != 'baigtas'"
    q += " ORDER BY p.priority, COALESCE(p.due_date,'9999'), p.code"
    out = db.rows(con.execute(q))
    for p in out:
        p.update(_progress(con, p["id"]))
        p["status_label"] = PROJECT_LABEL.get(p["status"], p["status"])
    return out


def _progress(con, project_id) -> dict:
    t = con.execute(
        "SELECT COUNT(*), SUM(status='baigta'), SUM(status IN ('vykdoma','pristabdyta')) "
        "FROM tasks WHERE project_id=?", (project_id,)).fetchone()
    ph = db.rows(con.execute(
        "SELECT kind, status FROM phases WHERE project_id=? ORDER BY sort, id", (project_id,)))
    ncr_open = con.execute(
        "SELECT COUNT(*) FROM ncr WHERE project_id=? AND status!='uzdaryta'", (project_id,)).fetchone()[0]
    active = sorted({PHASE_LABEL.get(x["kind"], x["kind"]) for x in ph if x["status"] == "vykdoma"})
    return {
        "tasks_total": t[0] or 0,
        "tasks_done": t[1] or 0,
        "tasks_running": t[2] or 0,
        "phases_total": len(ph),
        "phases_done": sum(1 for x in ph if x["status"] == "baigta"),
        "active_phases": active,
        "ncr_open": ncr_open,
    }


def get_project(con, project_id) -> dict:
    p = db.row(con.execute(
        "SELECT p.*, u.name AS manager_name FROM projects p LEFT JOIN users u ON u.id=p.manager_id "
        "WHERE p.id=?", (project_id,)))
    if not p:
        raise NotFound("Projekto nėra")
    p.update(_progress(con, project_id))
    p["status_label"] = PROJECT_LABEL.get(p["status"], p["status"])
    p["assemblies"] = db.rows(con.execute(
        "SELECT * FROM assemblies WHERE project_id=? ORDER BY sort, code", (project_id,)))
    p["phases"] = list_phases(con, project_id)
    p["tasks"] = db.rows(con.execute(
        "SELECT t.*, c.code AS centre_code, c.name AS centre_name, a.code AS assembly_code "
        "FROM tasks t JOIN work_centres c ON c.id=t.centre_id JOIN assemblies a ON a.id=t.assembly_id "
        "WHERE t.project_id=? ORDER BY a.sort, a.code, t.seq, t.id", (project_id,)))
    return p


def save_project(con, by, data: dict, project_id=None) -> int:
    fields = ("code", "name", "customer", "due_date", "priority", "status", "manager_id", "ext_ref", "notes")
    vals = {k: data.get(k) for k in fields if k in data}
    if "status" in vals and vals["status"] not in PROJECT_LABEL:
        raise RuleError("Nežinoma projekto būsena")
    if project_id is None:
        if not vals.get("code") or not vals.get("name"):
            raise RuleError("Reikia projekto kodo ir pavadinimo")
        if con.execute("SELECT 1 FROM projects WHERE code=?", (vals["code"],)).fetchone():
            raise RuleError(f"Projektas {vals['code']} jau yra")
        vals.setdefault("customer", "")
        vals.setdefault("priority", 3)
        vals.setdefault("status", "krepselis")
        cols = list(vals) + ["created"]
        cur = con.execute(
            f"INSERT INTO projects ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})",
            (*vals.values(), db.now()))
        project_id = cur.lastrowid
        db.log_event(con, by, "project", project_id, "create", vals)
    else:
        if not con.execute("SELECT 1 FROM projects WHERE id=?", (project_id,)).fetchone():
            raise NotFound("Projekto nėra")
        if vals:
            con.execute(f"UPDATE projects SET {', '.join(k + '=?' for k in vals)} WHERE id=?",
                        (*vals.values(), project_id))
            db.log_event(con, by, "project", project_id, "update", vals)
    return project_id


# ---------- mazgai ----------

def save_assembly(con, by, project_id, data: dict, assembly_id=None) -> int:
    if assembly_id is None:
        if not data.get("code") or not data.get("name"):
            raise RuleError("Reikia mazgo kodo ir pavadinimo")
        if con.execute("SELECT 1 FROM assemblies WHERE project_id=? AND code=?",
                       (project_id, data["code"])).fetchone():
            raise RuleError(f"Mazgas {data['code']} šiame projekte jau yra")
        sort = con.execute("SELECT COALESCE(MAX(sort),0)+1 FROM assemblies WHERE project_id=?",
                           (project_id,)).fetchone()[0]
        cur = con.execute(
            "INSERT INTO assemblies (project_id, code, name, revision, qty, requires, sort) VALUES (?,?,?,?,?,?,?)",
            (project_id, data["code"], data["name"], data.get("revision", ""), int(data.get("qty") or 1),
             _codes(data.get("requires")), sort))
        db.log_event(con, by, "assembly", cur.lastrowid, "create", data)
        return cur.lastrowid
    vals = {k: data[k] for k in ("code", "name", "revision", "qty") if k in data}
    if "requires" in data:
        vals["requires"] = _codes(data["requires"])
    if vals:
        con.execute(f"UPDATE assemblies SET {', '.join(k + '=?' for k in vals)} WHERE id=?",
                    (*vals.values(), assembly_id))
        db.log_event(con, by, "assembly", assembly_id, "update", vals)
    return assembly_id


def _codes(v) -> str:
    """„100, 200“ ar sąrašas → „100,200“."""
    if not v:
        return ""
    items = v if isinstance(v, (list, tuple)) else str(v).replace(";", ",").split(",")
    return ",".join(x.strip() for x in items if str(x).strip())


# ---------- etapai ----------

def list_phases(con, project_id) -> list[dict]:
    out = db.rows(con.execute(
        "SELECT ph.*, a.code AS assembly_code, a.name AS assembly_name, u.name AS owner_name "
        "FROM phases ph LEFT JOIN assemblies a ON a.id=ph.assembly_id LEFT JOIN users u ON u.id=ph.owner_id "
        "WHERE ph.project_id=? ORDER BY COALESCE(a.sort, 9999), ph.sort, ph.id", (project_id,)))
    for x in out:
        x["kind_label"] = PHASE_LABEL.get(x["kind"], x["kind"])
    return out


def save_phase(con, by, project_id, data: dict, phase_id=None) -> int:
    if phase_id is None:
        if data.get("kind") not in PHASE_LABEL:
            raise RuleError("Nežinomas etapo tipas")
        sort = [k for k, _ in PHASE_KINDS].index(data["kind"])
        cur = con.execute(
            "INSERT INTO phases (project_id, assembly_id, kind, owner_id, plan_start, plan_end, sort) "
            "VALUES (?,?,?,?,?,?,?)",
            (project_id, data.get("assembly_id"), data["kind"], data.get("owner_id"),
             data.get("plan_start"), data.get("plan_end"), sort))
        db.log_event(con, by, "phase", cur.lastrowid, "create", data)
        return cur.lastrowid
    vals = {k: data[k] for k in ("owner_id", "plan_start", "plan_end") if k in data}
    if vals.get("plan_start") and vals.get("plan_end") and vals["plan_end"] < vals["plan_start"]:
        raise RuleError("Etapo pabaiga ankstesnė už pradžią")
    if vals:
        con.execute(f"UPDATE phases SET {', '.join(k + '=?' for k in vals)} WHERE id=?",
                    (*vals.values(), phase_id))
        db.log_event(con, by, "phase", phase_id, "update", vals)
    return phase_id


def set_phase_status(con, by, phase_id, status) -> None:
    """Etapo pradžia ir pabaiga fiksuojama momentu, kada pažymėta – iš jų
    skaičiuojamas planas prieš faktą ir laukimas tarp etapų."""
    if status not in PHASE_STATUSES:
        raise RuleError("Nežinoma etapo būsena")
    ph = db.row(con.execute("SELECT * FROM phases WHERE id=?", (phase_id,)))
    if not ph:
        raise NotFound("Etapo nėra")
    t = db.now()
    if status == "vykdoma":
        con.execute("UPDATE phases SET status=?, actual_start=COALESCE(actual_start, ?), actual_end=NULL "
                    "WHERE id=?", (status, t, phase_id))
    elif status == "baigta":
        con.execute("UPDATE phases SET status=?, actual_start=COALESCE(actual_start, ?), actual_end=? "
                    "WHERE id=?", (status, t, t, phase_id))
    else:
        con.execute("UPDATE phases SET status=?, actual_start=NULL, actual_end=NULL WHERE id=?",
                    (status, phase_id))
    # pirmas pradėtas etapas projektą iš krepšelio perkelia į vykdomus
    if status != "planuota":
        con.execute("UPDATE projects SET status='vykdomas' WHERE id=? AND status='krepselis'",
                    (ph["project_id"],))
    db.log_event(con, by, "phase", phase_id, "status", {"status": status})


# ---------- darbo centrai ----------

def list_centres(con, active_only=True) -> list[dict]:
    q = "SELECT * FROM work_centres"
    if active_only:
        q += " WHERE active=1"
    return db.rows(con.execute(q + " ORDER BY sort, code"))


def centre_by_code(con, code) -> dict:
    c = db.row(con.execute("SELECT * FROM work_centres WHERE code=?", (code,)))
    if not c:
        raise NotFound(f"Darbo centro {code} nėra")
    return c


def save_centre(con, by, data: dict, centre_id=None) -> int:
    if centre_id is None:
        if not data.get("code") or not data.get("name"):
            raise RuleError("Reikia centro kodo ir pavadinimo")
        if con.execute("SELECT 1 FROM work_centres WHERE code=?", (data["code"],)).fetchone():
            raise RuleError(f"Centras {data['code']} jau yra")
        sort = con.execute("SELECT COALESCE(MAX(sort),0)+1 FROM work_centres").fetchone()[0]
        cur = con.execute(
            "INSERT INTO work_centres (code, name, kind, manual, strict_order, sort) VALUES (?,?,?,?,?,?)",
            (data["code"], data["name"], data.get("kind", "kita"), int(data.get("manual", 1)),
             int(data.get("strict_order", 1)), sort))
        db.log_event(con, by, "centre", cur.lastrowid, "create", data)
        return cur.lastrowid
    vals = {k: data[k] for k in ("name", "kind", "manual", "strict_order", "active") if k in data}
    if vals:
        con.execute(f"UPDATE work_centres SET {', '.join(k + '=?' for k in vals)} WHERE id=?",
                    (*vals.values(), centre_id))
        db.log_event(con, by, "centre", centre_id, "update", vals)
    return centre_id
