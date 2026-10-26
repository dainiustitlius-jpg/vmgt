"""Cecho planas: barai ir darbo centrai, išdėstyti kaip ceche, su gyvomis būsenomis.

Vartotojo sprendimai (2026-10-26): **planas redaguojamas nutempiant**
(preliminarų sudeda sistema pagal technologinį srautą), plane – **dabartinis
darbas ir laikmatis, detalių judėjimas, projekto filtras, įspėjimai**;
vieta – lange „Cechas“ kaip skirtukas (tinka ir sieniniam ekranui).

Koordinatės – sąlyginiais metrais. Baro vieta – visame plane, centro – baro
viduje: perkėlus barą, jo centrai keliauja kartu. Kol vieta neišsaugota
(`layout` NULL), ji apskaičiuojama automatiškai – tad naujas centras plane
atsiranda iškart, nieko nedarant.
"""

from __future__ import annotations

import json
import math

from .. import db
from . import RuleError, routing
from .analytics import floor
from .tasks import PAUSE_LABEL, _task

CELL = (8, 6)            # centro dydis
GAP = 2
HEAD = 4                 # baro pavadinimo juosta
ROW_W = 110              # automatinio išdėstymo eilutės plotis
PLANNED = ("pertrauka", "pamaina")
LONG_PAUSE_MIN = 60


def _cols(n):
    return max(1, n if n <= 3 else math.ceil(math.sqrt(n)) if n <= 6 else math.ceil(n / 2))


def auto_layout(areas: list[dict]) -> dict:
    """Barai iš kairės į dešinę technologinio srauto tvarka (`areas.sort`),
    eilutėmis; centrai – tinkleliu baro viduje."""
    out, x, y, row_h = {}, 0, 0, 0
    for a in areas:
        n = len(a["centres"])
        cols = _cols(n)
        rows = max(1, math.ceil(n / cols))
        w = cols * (CELL[0] + GAP) + GAP
        h = HEAD + rows * (CELL[1] + GAP) + GAP
        if x and x + w > ROW_W:
            x, y, row_h = 0, y + row_h + 3, 0
        out[a["id"]] = {"x": x, "y": y, "w": w, "h": h,
                        "centres": {c["id"]: {"x": GAP + (i % cols) * (CELL[0] + GAP),
                                              "y": HEAD + (i // cols) * (CELL[1] + GAP),
                                              "w": CELL[0], "h": CELL[1]} for i, c in enumerate(a["centres"])}}
        x += w + 3
        row_h = max(row_h, h)
    return out


def _load(v):
    try:
        d = json.loads(v) if v else None
        return d if d and all(isinstance(d.get(k), (int, float)) for k in ("x", "y", "w", "h")) else None
    except ValueError:
        return None


def plan(con, project_id=None) -> dict:
    """Visas planas: barai, centrai su būsenomis, šiandienos detalių judėjimas,
    projekto kelias (jei pasirinktas)."""
    state = {s["centre"]["id"]: s for s in floor(con)}
    areas = db.rows(con.execute("SELECT id, code, name, layout, sort FROM areas WHERE active=1 ORDER BY sort, code"))
    centres = db.rows(con.execute("SELECT id, code, name, kind, area_id, layout, needs_files, manual FROM work_centres "
                                  "WHERE active=1 ORDER BY sort, code"))
    known = {a["id"] for a in areas}
    loose = [c for c in centres if c["area_id"] not in known]
    if loose:
        areas.append({"id": 0, "code": "", "name": "Be baro", "layout": None, "sort": 9999})
    for a in areas:
        a["centres"] = [c for c in centres if (c["area_id"] if c["area_id"] in known else 0) == a["id"]]
    auto = auto_layout(areas)
    now = db.parse_ts(db.now())
    alerts = _alerts(con, now)
    waiting = _waiting(con)
    for a in areas:
        a["box"] = _load(a.pop("layout")) or {k: auto[a["id"]][k] for k in ("x", "y", "w", "h")}
        a["auto"] = a["box"] == {k: auto[a["id"]][k] for k in ("x", "y", "w", "h")}
        for c in a["centres"]:
            c["box"] = _load(c.pop("layout")) or auto[a["id"]]["centres"][c["id"]]
            st = state.get(c["id"], {})
            t = st.get("task")
            c.update({"state": st.get("state", "tuscia"), "queue": st.get("queue", 0), "since": st.get("since"),
                      "work_s": st.get("work_s", 0), "who": st.get("who"), "pause": st.get("pause"),
                      "lock": st.get("lock"),
                      "task": {k: t[k] for k in ("id", "name", "project_code", "assembly_code", "qty_plan", "qty_good",
                                                 "norm_min", "project_id")} if t else None,
                      "next": {k: st["next"][k] for k in ("name", "project_code", "assembly_code")} if st.get("next") else None,
                      "alerts": alerts.get(c["id"], []), "waiting": waiting.get(c["id"], 0)})
    w = max((a["box"]["x"] + a["box"]["w"] for a in areas), default=40)
    h = max((a["box"]["y"] + a["box"]["h"] for a in areas), default=20)
    return {"now": db.now(), "size": {"w": w, "h": h}, "areas": areas, "flows": _flows(con),
            "project": _project(con, project_id) if project_id else None,
            "projects": db.rows(con.execute("SELECT DISTINCT p.id, p.code, p.name FROM projects p "
                                            "JOIN tasks t ON t.project_id=p.id WHERE p.status='vykdomas' ORDER BY p.code"))}


def _alerts(con, now) -> dict:
    """Įspėjimai centrui: ilga neplanuota pauzė, viršyta norma, atvira neatitiktis,
    laukiamas meistro patvirtinimas, negauti komponentai."""
    out = {}
    add = lambda cid, sev, text: out.setdefault(cid, []).append({"severity": sev, "text": text})
    for r in con.execute("SELECT t.centre_id, p.reason, p.start, p.note FROM pauses p JOIN tasks t ON t.id=p.task_id "
                         "WHERE p.end IS NULL"):
        mins = (now - db.parse_ts(r["start"])).total_seconds() / 60
        if r["reason"] not in PLANNED and mins >= LONG_PAUSE_MIN:
            add(r["centre_id"], "red", f"{PAUSE_LABEL.get(r['reason'], r['reason'])} jau {int(mins // 60)} val. {int(mins % 60)} min.")
    for r in con.execute(
            "SELECT t.id, t.centre_id, t.norm_min, t.qty_plan, t.qty_good, t.qty_scrap, "
            "(SELECT start FROM intervals WHERE task_id=t.id AND end IS NULL) AS open_start "
            "FROM tasks t WHERE t.status='vykdoma' AND t.norm_min > 0"):
        work = sum((db.parse_ts(i["end"]) - db.parse_ts(i["start"])).total_seconds()
                   for i in con.execute("SELECT start, end FROM intervals WHERE task_id=? AND end IS NOT NULL", (r["id"],)))
        if r["open_start"]:
            work += (now - db.parse_ts(r["open_start"])).total_seconds()
        norm = r["norm_min"] * r["qty_plan"] * 60
        if work > norm * 1.25:
            add(r["centre_id"], "yellow", f"Viršyta norma: {round(work / norm * 100)} %")
    for r in con.execute("SELECT t.centre_id, COUNT(*) AS n FROM ncr n JOIN tasks t ON t.id=n.task_id "
                         "WHERE n.status!='uzdaryta' GROUP BY t.centre_id"):
        add(r["centre_id"], "red", f"Atvira neatitiktis: {r['n']}")
    for r in con.execute("SELECT t.centre_id, COUNT(*) AS n FROM task_files f JOIN tasks t ON t.id=f.task_id "
                         "WHERE f.current=1 AND f.needs_ack=1 AND t.status!='baigta' GROUP BY t.centre_id"):
        add(r["centre_id"], "yellow", f"Laukia meistro patvirtinimo: {r['n']} fail.")
    return out


def _waiting(con) -> dict:
    """Kiek detalių / partijų atkeliavo ir laukia prie centro (eilėje, ne vykdomos)."""
    out = {}
    for t in db.rows(con.execute("SELECT * FROM tasks WHERE status='laukia' AND approved=1")):
        st = routing.structure(con, t["assembly_id"])
        ups = routing.upstream(con, t, st)
        n = routing.arrived(t, ups)
        if n is None and ups and all(u["status"] == "baigta" or u["qty_good"] > 0 for u in ups):
            n = 1                                          # detalės susiliejo – mazgas laukia
        if n:
            out[t["centre_id"]] = out.get(t["centre_id"], 0) + n
    return out


def _flows(con) -> list[dict]:
    """Šiandien perduotos detalės: iš kurio centro į kurį ir kiek."""
    day = db.now()[:10]
    return db.rows(con.execute(
        "SELECT f.centre_id AS from_id, t.centre_id AS to_id, SUM(x.qty) AS qty, COUNT(*) AS n "
        "FROM transfers x JOIN tasks f ON f.id=x.from_task_id JOIN tasks t ON t.id=x.to_task_id "
        "WHERE substr(x.at, 1, 10)=? AND f.centre_id!=t.centre_id GROUP BY f.centre_id, t.centre_id", (day,)))


def _project(con, project_id) -> dict:
    """Projekto kelias per cechą: kuriuose centruose jo darbai (atlikta / vyksta /
    laukia) ir maršruto rodyklės tarp jų."""
    ts = db.rows(con.execute("SELECT id, centre_id, status, assembly_id FROM tasks WHERE project_id=?", (project_id,)))
    centres, edges = {}, {}
    for t in ts:
        c = centres.setdefault(t["centre_id"], {"done": 0, "open": 0, "running": 0})
        c["done" if t["status"] == "baigta" else "running" if t["status"] in ("vykdoma", "pristabdyta") else "open"] += 1
        for d in routing.next_steps(con, _task(con, t["id"])):
            if d["task_id"]:
                to = con.execute("SELECT centre_id FROM tasks WHERE id=?", (d["task_id"],)).fetchone()[0]
                if to != t["centre_id"]:
                    e = edges.setdefault((t["centre_id"], to), {"from_id": t["centre_id"], "to_id": to, "done": True})
                    e["done"] = e["done"] and t["status"] == "baigta"
    p = db.row(con.execute("SELECT id, code, name FROM projects WHERE id=?", (project_id,)))
    return {**p, "centres": centres, "edges": list(edges.values())}


def save(con, by, data: dict) -> None:
    """Išsaugo barų ir centrų vietas. `reset` – grąžinti automatinį išdėstymą."""
    if data.get("reset"):
        con.execute("UPDATE areas SET layout=NULL")
        con.execute("UPDATE work_centres SET layout=NULL")
        db.log_event(con, by, "layout", None, "reset")
        return
    def box(b):
        try:
            v = {k: round(float(b[k]), 1) for k in ("x", "y", "w", "h")}
        except (KeyError, TypeError, ValueError):
            raise RuleError("Netinkamos plano koordinatės") from None
        if v["w"] < 2 or v["h"] < 2 or v["x"] < 0 or v["y"] < 0 or v["x"] + v["w"] > 1000 or v["y"] + v["h"] > 1000:
            raise RuleError("Netinkamas dydis ar vieta plane")
        return json.dumps(v)
    for a in data.get("areas") or []:
        if a.get("id"):
            con.execute("UPDATE areas SET layout=? WHERE id=?", (box(a), int(a["id"])))
    for c in data.get("centres") or []:
        con.execute("UPDATE work_centres SET layout=? WHERE id=?", (box(c), int(c["id"])))
    db.log_event(con, by, "layout", None, "save", {"areas": len(data.get("areas") or []),
                                                    "centres": len(data.get("centres") or [])})
