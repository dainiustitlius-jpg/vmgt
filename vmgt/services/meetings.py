"""Susitikimų protokolai (Minutes of Meetings).

Protokolas = dalyviai, darbotvarkė, užrašai, sprendimai ir veiksmai. Kiekvienas
veiksmas su atsakingu ir terminu iškart tampa projekto užduotimi
(`actions`, `meeting_id`), tad jo eiga matoma Kanban lentoje, o kitame
susitikime – sąraše „Ankstesnių susitikimų veiksmai“.

Patvirtintas protokolas užrakinamas: tekstas yra susitarimo įrašas, jo
keisti po fakto negalima. Iš jo kilusios užduotys gyvena toliau.
"""

from __future__ import annotations

import json

from .. import db
from . import NotFound, RuleError, actions

STATUSES = [("juodrastis", "Juodraštis"), ("patvirtintas", "Patvirtintas")]
STATUS_LABEL = dict(STATUSES)
TEXT_FIELDS = ("title", "held_at", "location", "chair_id", "guests", "agenda", "notes", "decisions")


def list_meetings(con, project_id=None) -> list[dict]:
    q = ("SELECT m.*, p.code AS project_code, u.name AS chair_name, "
         "(SELECT COUNT(*) FROM actions x WHERE x.meeting_id=m.id) AS actions_total, "
         "(SELECT COUNT(*) FROM actions x WHERE x.meeting_id=m.id AND x.status IN ('atlikta','atsaukta')) AS actions_closed "
         "FROM meetings m JOIN projects p ON p.id=m.project_id LEFT JOIN users u ON u.id=m.chair_id")
    args = []
    if project_id:
        q += " WHERE m.project_id=?"; args.append(project_id)
    out = db.rows(con.execute(q + " ORDER BY m.held_at DESC, m.id DESC", args))
    for m in out:
        m["status_label"] = STATUS_LABEL[m["status"]]
    return out


def get(con, meeting_id) -> dict:
    m = db.row(con.execute(
        "SELECT m.*, p.code AS project_code, p.name AS project_name, u.name AS chair_name, ua.name AS approved_name "
        "FROM meetings m JOIN projects p ON p.id=m.project_id LEFT JOIN users u ON u.id=m.chair_id "
        "LEFT JOIN users ua ON ua.id=m.approved_by WHERE m.id=?", (meeting_id,)))
    if not m:
        raise NotFound("Protokolo nėra")
    ids = json.loads(m["attendees"] or "[]")
    m["attendees"] = ids
    m["attendee_names"] = [r[0] for r in con.execute(
        f"SELECT name FROM users WHERE id IN ({','.join('?' * len(ids))}) ORDER BY name", ids)] if ids else []
    m["decision_list"] = [d.strip() for d in (m["decisions"] or "").splitlines() if d.strip()]
    m["status_label"] = STATUS_LABEL[m["status"]]
    m["actions"] = actions.list_actions(con, meeting_id=meeting_id)
    # ankstesnių susitikimų veiksmai, kurie dar neuždaryti – peržiūrai susitikimo pradžioje
    m["review"] = [x for x in actions.list_actions(con, project_id=m["project_id"], status="open")
                   if x["meeting_id"] and x["meeting_id"] != meeting_id and (x["meeting_at"] or "") < m["held_at"]]
    return m


def save(con, user, data: dict, meeting_id=None) -> int:
    vals = {k: data[k] for k in TEXT_FIELDS if k in data}
    if "attendees" in data:
        vals["attendees"] = json.dumps([int(i) for i in data["attendees"] or []])
    if meeting_id is None:
        if not data.get("project_id") or not (data.get("title") or "").strip() or not data.get("held_at"):
            raise RuleError("Reikia projekto, pavadinimo ir susitikimo datos")
        cols = ["project_id"] + list(vals) + ["created_by", "created"]
        cur = con.execute(f"INSERT INTO meetings ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})",
                          (data["project_id"], *vals.values(), user["id"], db.now()))
        meeting_id = cur.lastrowid
        db.log_event(con, user["id"], "meeting", meeting_id, "create", {"title": data["title"]})
    else:
        m = get(con, meeting_id)
        if m["status"] == "patvirtintas":
            raise RuleError("Patvirtinto protokolo keisti negalima")
        if vals:
            con.execute(f"UPDATE meetings SET {', '.join(k + '=?' for k in vals)} WHERE id=?",
                        (*vals.values(), meeting_id))
            db.log_event(con, user["id"], "meeting", meeting_id, "update", {k: v for k, v in vals.items() if k != "notes"})
    pid = con.execute("SELECT project_id FROM meetings WHERE id=?", (meeting_id,)).fetchone()[0]
    # nauji veiksmai – iškart projekto užduotys
    for a in data.get("new_actions") or []:
        if (a.get("title") or "").strip():
            actions.create(con, user["id"], {**a, "project_id": pid}, meeting_id=meeting_id)
    return meeting_id


def approve(con, user, meeting_id) -> None:
    m = get(con, meeting_id)
    if m["status"] == "patvirtintas":
        raise RuleError("Protokolas jau patvirtintas")
    if not m["attendees"] and not (m["guests"] or "").strip():
        raise RuleError("Protokole nenurodyti dalyviai")
    con.execute("UPDATE meetings SET status='patvirtintas', approved_by=?, approved_at=? WHERE id=?",
                (user["id"], db.now(), meeting_id))
    db.log_event(con, user["id"], "meeting", meeting_id, "approve")


def as_text(m: dict) -> str:
    """Protokolas tekstu – el. laiškui ar spausdinimui."""
    lines = [f"{m['project_code']} – {m['title']}", f"Data: {m['held_at'].replace('T', ' ')[:16]}"
             + (f", vieta: {m['location']}" if m["location"] else ""),
             f"Pirmininkas: {m['chair_name'] or '—'}",
             "Dalyviai: " + ", ".join(m["attendee_names"] + ([m["guests"]] if m["guests"] else [])), ""]
    if m["agenda"]:
        lines += ["DARBOTVARKĖ", m["agenda"], ""]
    if m["notes"]:
        lines += ["APTARTA", m["notes"], ""]
    if m["decision_list"]:
        lines += ["SPRENDIMAI"] + [f"{i}. {d}" for i, d in enumerate(m["decision_list"], 1)] + [""]
    if m["actions"]:
        lines += ["VEIKSMAI"] + [f"- {x['title']} – {x['owner_name'] or 'nepriskirta'}, iki {x['due_date'] or '—'} "
                                 f"[{x['status_label']}]" for x in m["actions"]]
    lines += ["", f"Būsena: {m['status_label']}" + (f" ({m['approved_name']}, {m['approved_at'][:10]})"
                                                    if m["approved_at"] else "")]
    return "\n".join(lines)
