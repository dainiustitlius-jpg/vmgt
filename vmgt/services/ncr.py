"""Neatitiktys: registruoja operatorius, priskiria ir uždaro kokybės inžinierius.

Būsenos: atvira → priskirta → uzdaryta. Kokybės modulis (patikrų šablonai,
protokolai) bus vėlesnis etapas; čia – tik tai, ko reikia terminalui jau dabar,
kad neatitiktis būtų užfiksuota ten, kur ji pastebėta.
"""

from __future__ import annotations

from .. import db
from . import NotFound, RuleError

CATEGORIES = [
    ("matmenys", "Matmenys"),
    ("pjovimas", "Pjovimas"),
    ("lenkimas", "Lenkimas"),
    ("suvirinimas", "Suvirinimas"),
    ("pavirsius", "Paviršius, dažymas"),
    ("medziaga", "Medžiaga, komponentai"),
    ("brezinys", "Brėžinio klaida"),
    ("surinkimas", "Surinkimas"),
    ("kita", "Kita"),
]
CAT_LABEL = dict(CATEGORIES)
STATUSES = [("atvira", "Atvira"), ("priskirta", "Priskirta"), ("uzdaryta", "Uždaryta")]
STATUS_LABEL = dict(STATUSES)


def report(con, user, data: dict) -> int:
    if data.get("category") not in CAT_LABEL:
        raise RuleError("Pasirinkite neatitikties kategoriją")
    if not (data.get("description") or "").strip():
        raise RuleError("Aprašykite, kas negerai")
    project_id, assembly_id = data.get("project_id"), data.get("assembly_id")
    if data.get("task_id"):
        t = db.row(con.execute("SELECT project_id, assembly_id FROM tasks WHERE id=?", (data["task_id"],)))
        if not t:
            raise NotFound("Užduoties nėra")
        project_id, assembly_id = t["project_id"], t["assembly_id"]
    if not project_id:
        raise RuleError("Nurodykite projektą")
    cur = con.execute(
        "INSERT INTO ncr (project_id, assembly_id, task_id, reported_by, reported_at, qty, category, description) "
        "VALUES (?,?,?,?,?,?,?,?)",
        (project_id, assembly_id, data.get("task_id"), user["id"], db.now(), int(data.get("qty") or 0),
         data["category"], data["description"].strip()))
    db.log_event(con, user["id"], "ncr", cur.lastrowid, "report", data)
    return cur.lastrowid


def list_ncr(con, status=None, project_id=None) -> list[dict]:
    q = ("SELECT n.*, p.code AS project_code, a.code AS assembly_code, t.name AS task_name, "
         "c.code AS centre_code, ur.name AS reporter, ua.name AS assignee "
         "FROM ncr n JOIN projects p ON p.id=n.project_id LEFT JOIN assemblies a ON a.id=n.assembly_id "
         "LEFT JOIN tasks t ON t.id=n.task_id LEFT JOIN work_centres c ON c.id=t.centre_id "
         "LEFT JOIN users ur ON ur.id=n.reported_by LEFT JOIN users ua ON ua.id=n.assignee_id WHERE 1=1")
    args = []
    if status == "open":
        q += " AND n.status!='uzdaryta'"
    elif status:
        q += " AND n.status=?"; args.append(status)
    if project_id:
        q += " AND n.project_id=?"; args.append(project_id)
    out = db.rows(con.execute(q + " ORDER BY n.id DESC", args))
    for n in out:
        n["category_label"] = CAT_LABEL.get(n["category"], n["category"])
        n["status_label"] = STATUS_LABEL.get(n["status"], n["status"])
    return out


def assign(con, user, ncr_id, assignee_id) -> None:
    n = db.row(con.execute("SELECT * FROM ncr WHERE id=?", (ncr_id,)))
    if not n:
        raise NotFound("Neatitikties nėra")
    if n["status"] == "uzdaryta":
        raise RuleError("Uždaryta neatitiktis nebepriskiriama")
    con.execute("UPDATE ncr SET assignee_id=?, status='priskirta' WHERE id=?", (assignee_id, ncr_id))
    db.log_event(con, user["id"], "ncr", ncr_id, "assign", {"assignee_id": assignee_id})


def close(con, user, ncr_id, resolution: str) -> None:
    n = db.row(con.execute("SELECT * FROM ncr WHERE id=?", (ncr_id,)))
    if not n:
        raise NotFound("Neatitikties nėra")
    if not (resolution or "").strip():
        raise RuleError("Įrašykite sprendimą")
    con.execute("UPDATE ncr SET status='uzdaryta', resolution=?, closed_by=?, closed_at=? WHERE id=?",
                (resolution.strip(), user["id"], db.now(), ncr_id))
    db.log_event(con, user["id"], "ncr", ncr_id, "close", {"resolution": resolution})
