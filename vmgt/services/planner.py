"""Planuotojo langas: visų departamentų darbai laike ir pakeitimų poveikis.

Vartotojo sprendimai (2026-10-26): **Gantt pagal departamentus** (biuro
skyriai ir gamybos barai), **poveikio peržiūra prieš įrašant + pranešimai**
paveiktiems projektams.

Poveikis skaičiuojamas ne spėjant, o tuo pačiu apkrovos skaičiavimu kaip
lange „Apkrova“ (`capacity.report`): pakeitimas laikinai pritaikomas bazėje
(SAVEPOINT), apkrova perskaičiuojama ir palyginama su buvusia, tada
atšaukiama. Tad peržiūra rodo lygiai tai, kas bus įrašius.

Paveiktas projektas – kitas projektas, kurio darbas yra departamento
savaitėje, kuri dėl pakeitimo persikrovė (> 100 %) arba priartėjo prie ribos
(> 85 %); centro eilėje – kurio darbai pasislinko atgal.
"""

from __future__ import annotations

from datetime import date, timedelta

from .. import db
from . import NotFound, RuleError, capacity, projects, signals, tasks, workcal

WEEKS = 16
KINDS = ("phase", "priority", "queue", "activate")


# ---------- Gantt ----------

def board(con, weeks: int = 12, include_basket=True) -> dict:
    today = date.fromisoformat(db.now()[:10])
    start = capacity.monday(today) - timedelta(weeks=1)
    end = start + timedelta(weeks=weeks) - timedelta(days=1)
    cap = capacity.report(con, weeks=weeks, include_basket=include_basket, start=start)
    depts = capacity.list_departments(con, active_only=True)
    by_kind = {}
    for d in depts:
        for k in d["phase_kind_list"]:
            by_kind.setdefault(k, d["id"])
    by_area = {d["area_id"]: d["id"] for d in depts if d["kind"] == "production" and d["area_id"]}
    statuses = ("vykdomas", "krepselis") if include_basket else ("vykdomas",)
    plist = db.rows(con.execute(
        f"SELECT id, code, name, status, priority, due_date FROM projects WHERE status IN ({','.join('?' * len(statuses))}) "
        "ORDER BY priority, due_date IS NULL, due_date, code", statuses))
    pids = {p["id"] for p in plist}
    bars = {d["id"]: [] for d in depts}
    unplaced = []
    for ph in db.rows(con.execute(
            "SELECT ph.*, a.code AS assembly_code, u.name AS owner_name FROM phases ph "
            "LEFT JOIN assemblies a ON a.id=ph.assembly_id LEFT JOIN users u ON u.id=ph.owner_id "
            "ORDER BY ph.plan_start")):
        if ph["project_id"] not in pids:
            continue
        if not ph["plan_start"] or not ph["plan_end"]:
            unplaced.append(ph)
            continue
        if ph["plan_end"] < start.isoformat() and ph["status"] == "baigta":
            continue
        for dept_id, share in _phase_departments(con, ph, by_kind, by_area):
            if dept_id in bars:
                bars[dept_id].append({**_bar(ph, today), "share": share})
    rows = []
    cap_by = {r["id"]: r for r in cap["departments"]}
    cal = workcal.Calendar(con)
    for d in depts:
        rows.append({"id": d["id"], "code": d["code"], "name": d["name"], "kind": d["kind"],
                     "off": _off_days(cal, d, start, end),
                     "capacity_week": cap_by[d["id"]]["capacity_week"],
                     "load": [{"week": c["week"], "util": c["util"], "shortage": c["shortage"],
                               "hours": round(c["committed"] + (c["basket"] if include_basket else 0), 1)}
                              for c in cap_by[d["id"]]["cells"]],
                     "bars": bars[d["id"]]})
    return {"today": today.isoformat(), "start": start.isoformat(), "end": end.isoformat(),
            "weeks": cap["weeks"], "departments": rows, "projects": plist,
            "unplaced": [{"phase_id": p["id"], "project_id": p["project_id"], "kind": p["kind"],
                          "label": projects.PHASE_LABEL.get(p["kind"], p["kind"])} for p in unplaced]}


def _off_days(cal, d, start, end) -> list[dict]:
    """Departamento neįprastos dienos grafikui: nedarbo (savaitgalis, šventė,
    uždaryta), papildomas darbas, remontas; barui – ir jo centrų remontai."""
    scope = ("area", d["area_id"]) if d["kind"] == "production" and d["area_id"] else ("factory", 0)
    centres = [c for c in cal.centres.values() if scope[0] == "area" and c["area_id"] == scope[1] and c["active"]]
    out, x = [], start
    while x <= end:
        day = cal.day(*scope, x)
        if day["kind"] != "darbo":
            out.append({"d": x.isoformat(), "kind": day["kind"], "off": not day["minutes"],
                        "text": day["label"] + (f": {day['note']}" if day["note"] else "")
                        + (f" ({day['hours']})" if day["minutes"] and day["kind"] != "poilsio" else "")})
        rep = [c["code"] for c in centres if cal.day("centre", c["id"], x)["kind"] == "remontas"
               and cal.day("centre", c["id"], x)["own"]]
        if rep and day["minutes"]:
            out.append({"d": x.isoformat(), "kind": "remontas", "off": False,
                        "text": "Remontas: " + ", ".join(rep)})
        x += timedelta(days=1)
    return out


def _bar(ph, today) -> dict:
    late = ph["status"] != "baigta" and ph["plan_end"] < today.isoformat()
    late_start = ph["status"] == "planuota" and ph["plan_start"] < today.isoformat()
    return {"phase_id": ph["id"], "project_id": ph["project_id"], "assembly": ph["assembly_code"],
            "kind": ph["kind"], "label": projects.PHASE_LABEL.get(ph["kind"], ph["kind"]),
            "plan_start": ph["plan_start"], "plan_end": ph["plan_end"], "status": ph["status"],
            "actual_start": ph["actual_start"], "actual_end": ph["actual_end"], "hours": ph["hours"],
            "owner": ph["owner_name"], "late": late, "late_start": late_start}


def _phase_departments(con, ph, by_kind, by_area) -> list[tuple[int, float | None]]:
    """Kuriame departamente etapo darbas. Gamybos / surinkimo etapas – kiekviename
    bare, kuriame yra jo operacijų (su to baro normų valandomis)."""
    if ph["kind"] not in capacity.PRODUCTION_KINDS:
        d = ph["department_id"] or by_kind.get(ph["kind"])
        return [(d, ph["hours"])] if d else []
    q = ("SELECT c.area_id, c.kind, SUM(t.norm_min * t.qty_plan) / 60.0 AS h FROM tasks t "
         "JOIN work_centres c ON c.id=t.centre_id WHERE t.project_id=?")
    args = [ph["project_id"]]
    if ph["assembly_id"]:
        q += " AND t.assembly_id=?"
        args.append(ph["assembly_id"])
    out = {}
    for r in con.execute(q + " GROUP BY c.area_id, c.kind", args):
        if tasks.CENTRE_PHASE.get(r["kind"], "gamyba") == ph["kind"] and by_area.get(r["area_id"]):
            d = by_area[r["area_id"]]
            out[d] = out.get(d, 0) + (r["h"] or 0)
    if out:
        return [(d, round(h, 1)) for d, h in out.items()]
    return [(ph["department_id"], ph["hours"])] if ph["department_id"] else []


# ---------- poveikis ----------

def _snapshot(con) -> dict:
    r = capacity.report(con, weeks=WEEKS, include_basket=True)
    cells = {}
    for d in r["departments"]:
        for c in d["cells"]:
            cells[(d["code"], c["week"])] = {
                "dept": d["name"], "cap": c["capacity"], "committed": c["committed"],
                "total": c["committed"] + c["basket"],
                "projects": {x["project_id"]: x["hours"] for x in c["projects"]}}
    return {"cells": cells, "weeks": {w["start"]: w["label"] for w in r["weeks"]}}


def _pct(v, cap):
    return f"{round(100 * v / cap)} %" if cap else "—"


def _compare(before, after, mover_id, committed_only=False) -> tuple[list, list]:
    """Kurių KITŲ projektų departamentų savaitės persikrovė; kur atsilaisvino."""
    key = "committed" if committed_only else "total"
    affected, freed = {}, []
    codes = {}
    for k, a in after["cells"].items():
        b = before["cells"].get(k)
        if not b or not a["cap"]:
            continue
        va, vb, cap = a[key], b[key], a["cap"]
        label = after["weeks"].get(k[1], k[1])
        if va > vb + 0.5 and va > cap * capacity.WARN_UTIL:
            sev = "red" if va > cap + 0.5 else "yellow"
            reason = (f"{a['dept']} {label}: apkrova {_pct(vb, cap)} → {_pct(va, cap)}"
                      + (f" (trūksta {round(va - cap)} val.)" if va > cap + 0.5 else ""))
            for pid in a["projects"]:
                if pid == mover_id:
                    continue
                x = affected.setdefault(pid, {"project_id": pid, "severity": sev, "reasons": []})
                if sev == "red":
                    x["severity"] = "red"
                x["reasons"].append(reason)
        elif vb > cap + 0.5 and va < vb - 0.5:
            freed.append(f"{a['dept']} {label}: apkrova {_pct(vb, cap)} → {_pct(va, cap)}")
    return list(affected.values()), freed


def _queue_state(con, centre_id) -> list[dict]:
    return db.rows(con.execute(
        "SELECT t.id, t.name, t.project_id, t.norm_min, t.qty_plan, t.qty_good, t.qty_scrap, a.code AS assembly_code "
        "FROM tasks t JOIN assemblies a ON a.id=t.assembly_id WHERE t.centre_id=? AND t.status!='baigta' "
        "ORDER BY t.queue_pos, t.id", (centre_id,)))


def _left_h(t):
    return (t["norm_min"] or 0) * max(0, t["qty_plan"] - t["qty_good"] - t["qty_scrap"]) / 60


def _apply(con, user, change: dict):
    kind = change.get("kind")
    if kind == "phase":
        ph = db.row(con.execute("SELECT * FROM phases WHERE id=?", (change.get("phase_id"),)))
        if not ph:
            raise NotFound("Etapo nėra")
        a, b = change.get("plan_start"), change.get("plan_end")
        if not a or not b:
            raise RuleError("Nurodykite etapo pradžią ir pabaigą")
        projects.save_phase(con, user["id"], None, {"plan_start": a, "plan_end": b}, ph["id"])
        return ph["project_id"]
    if kind == "priority":
        pr = int(change.get("priority") or 0)
        if not 1 <= pr <= 5:
            raise RuleError("Prioritetas – nuo 1 (aukščiausias) iki 5")
        projects.save_project(con, user["id"], {"priority": pr}, change["project_id"])
        return change["project_id"]
    if kind == "queue":
        t = tasks._task(con, change.get("task_id"))
        tasks.move(con, user["id"], t["id"], change.get("where", ""))
        return t["project_id"]
    if kind == "activate":
        p = db.row(con.execute("SELECT status FROM projects WHERE id=?", (change.get("project_id"),)))
        if not p:
            raise NotFound("Projekto nėra")
        if p["status"] != "krepselis":
            raise RuleError("Patvirtinti galima tik krepšelio projektą")
        projects.save_project(con, user["id"], {"status": "vykdomas"}, change["project_id"])
        return change["project_id"]
    raise RuleError("Nežinomas pakeitimas")


def _own_warnings(con, change, project_id) -> list[str]:
    """Paties projekto nuoseklumas po pakeitimo (skaičiuojama jau pritaikius)."""
    out = []
    p = db.row(con.execute("SELECT code, due_date FROM projects WHERE id=?", (project_id,)))
    if change["kind"] == "phase":
        ph = db.row(con.execute("SELECT * FROM phases WHERE id=?", (change["phase_id"],)))
        label = projects.PHASE_LABEL.get(ph["kind"], ph["kind"])
        if p["due_date"] and ph["plan_end"] > p["due_date"]:
            out.append(f"{label} baigsis {ph['plan_end']} – po projekto termino {p['due_date']}")
        order = [k for k, _ in projects.PHASE_KINDS]
        for o in db.rows(con.execute(
                "SELECT * FROM phases WHERE project_id=? AND id!=? AND status!='baigta' "
                "AND (assembly_id IS ? OR assembly_id IS NULL OR ? IS NULL)",
                (project_id, ph["id"], ph["assembly_id"], ph["assembly_id"]))):
            if not o["plan_start"] or not o["plan_end"]:
                continue
            ol = projects.PHASE_LABEL.get(o["kind"], o["kind"])
            if order.index(o["kind"]) > order.index(ph["kind"]) and o["plan_start"] < ph["plan_end"] \
                    and o["kind"] in ("surinkimas", "programavimas", "testavimas") and ph["kind"] in ("gamyba", "surinkimas"):
                out.append(f"{ol} prasideda {o['plan_start']}, o {label.lower()} baigsis tik {ph['plan_end']}")
    return out


def impact(con, user, change: dict) -> dict:
    """Ką pakeitimas paveiktų – nieko neįrašant."""
    if change.get("kind") not in KINDS:
        raise RuleError("Nežinomas pakeitimas")
    before = _snapshot(con)
    q_before = None
    if change["kind"] == "queue":
        t = tasks._task(con, change.get("task_id"))
        q_before = _queue_state(con, t["centre_id"])
    con.execute("SAVEPOINT plan_impact")
    try:
        pid = _apply(con, user, change)
        after = _snapshot(con)
        own = _own_warnings(con, change, pid)
        q_after = _queue_state(con, t["centre_id"]) if q_before is not None else None
    finally:
        con.execute("ROLLBACK TO plan_impact")
        con.execute("RELEASE plan_impact")
    affected, freed = _compare(before, after, pid, committed_only=change["kind"] == "activate")
    if q_before is not None:
        affected += _queue_affected(q_before, q_after, pid, t["centre_code"])
    if change["kind"] == "priority":
        affected += _priority_affected(con, before, pid, int(change["priority"]))
    return _finish(con, pid, change, affected, freed, own)


def _queue_affected(qb, qa, mover_pid, centre) -> list[dict]:
    pos_b = {t["id"]: i for i, t in enumerate(qb)}
    out = {}
    for i, t in enumerate(qa):
        if t["project_id"] == mover_pid or i <= pos_b[t["id"]]:
            continue
        ahead_now = {x["id"] for x in qa[:i]} - {x["id"] for x in qb[:pos_b[t["id"]]]}
        h = sum(_left_h(x) for x in qa if x["id"] in ahead_now)
        x = out.setdefault(t["project_id"], {"project_id": t["project_id"], "severity": "yellow", "reasons": []})
        x["reasons"].append(f"{centre}: „{t['assembly_code']} · {t['name']}“ eilėje {pos_b[t['id']] + 1} → {i + 1} vieta"
                            + (f" (~{round(h, 1)} val. vėliau)" if h else ""))
    return list(out.values())


def _priority_affected(con, snap, pid, new_prio) -> list[dict]:
    """Kitiems projektams, su kuriais dalijamasi departamentais tomis pačiomis
    savaitėmis: kas dabar bus aukštesnio prioriteto."""
    p = db.row(con.execute("SELECT code, priority FROM projects WHERE id=?", (pid,)))
    if new_prio >= p["priority"]:
        return []
    shared = {}
    for (dept, week), c in snap["cells"].items():
        if pid in c["projects"]:
            for other in c["projects"]:
                if other != pid:
                    shared.setdefault(other, set()).add(c["dept"])
    out = []
    for other, deps in shared.items():
        op = db.row(con.execute("SELECT priority FROM projects WHERE id=?", (other,)))
        if op and new_prio <= op["priority"] <= p["priority"]:
            out.append({"project_id": other, "severity": "yellow",
                        "reasons": [f"{p['code']} prioritetas P{p['priority']} → P{new_prio}: pirmenybė "
                                    f"bendruose departamentuose ({', '.join(sorted(deps))})"]})
    return out


def _finish(con, pid, change, affected, freed, own) -> dict:
    merged = {}
    for a in affected:
        x = merged.setdefault(a["project_id"], {"project_id": a["project_id"], "severity": a["severity"], "reasons": []})
        if a["severity"] == "red":
            x["severity"] = "red"
        x["reasons"] += [r for r in a["reasons"] if r not in x["reasons"]]
    for x in merged.values():
        pr = db.row(con.execute("SELECT code, name FROM projects WHERE id=?", (x["project_id"],)))
        x["code"], x["name"] = pr["code"], pr["name"]
    p = db.row(con.execute("SELECT code, name FROM projects WHERE id=?", (pid,))) if pid else None
    return {"project_id": pid, "project_code": p["code"] if p else None, "summary": describe(con, change),
            "affected": sorted(merged.values(), key=lambda x: (x["severity"] != "red", x["code"])),
            "freed": freed, "own": own}


def describe(con, change) -> str:
    k = change["kind"]
    if k == "calendar":
        return change["summary"]
    if k == "phase":
        ph = db.row(con.execute("SELECT ph.*, p.code, a.code AS ac FROM phases ph JOIN projects p ON p.id=ph.project_id "
                                "LEFT JOIN assemblies a ON a.id=ph.assembly_id WHERE ph.id=?", (change["phase_id"],)))
        label = projects.PHASE_LABEL.get(ph["kind"], ph["kind"])
        return (f"{ph['code']}{' ' + ph['ac'] if ph['ac'] else ''} {label.lower()}: "
                f"{ph['plan_start']}…{ph['plan_end']} → {change['plan_start']}…{change['plan_end']}")
    if k == "priority":
        p = db.row(con.execute("SELECT code, priority FROM projects WHERE id=?", (change["project_id"],)))
        return f"{p['code']} prioritetas P{p['priority']} → P{change['priority']}"
    if k == "queue":
        t = tasks._task(con, change["task_id"])
        where = {"top": "į eilės pradžią", "up": "aukštyn", "down": "žemyn"}.get(change.get("where"), "")
        return f"{t['centre_code']} eilė: {t['project_code']} {t['assembly_code']} · {t['name']} {where}"
    p = db.row(con.execute("SELECT code, name FROM projects WHERE id=?", (change["project_id"],)))
    return f"patvirtintas projektas {p['code']} {p['name']}"


def apply(con, user, change: dict, note: str = "") -> dict:
    """Įrašo pakeitimą ir praneša paveiktiems projektams."""
    imp = impact(con, user, change)
    pid = _apply(con, user, change)
    kind = change["kind"]
    if kind == "activate":
        # tas pats signalas, kaip ir projektui tapus vykdomu kitaip (pradėtas darbas)
        signals.record(con, user["id"], "activate", pid, imp["summary"], imp["affected"], note, imp["own"],
                       key=f"activate:{pid}", link="#/apkrova")
    else:
        imp["change_id"] = signals.record(con, user["id"], kind, pid, imp["summary"], imp["affected"], note, imp["own"])
    return imp


# ---------- darbo kalendorius ----------

def calendar_change(con, user, do, note: str = "") -> dict:
    """Kalendoriaus pakeitimas (nedarbo diena, remontas, pamaina) paveikia
    visų tame bare / centre dirbančių projektų darbus. `do()` įrašo pakeitimą
    ir grąžina {summary}; prieš ir po palyginamos apkrovos savaitės ir
    operacijų prognozė – paveiktiems projektams išsiunčiami pranešimai."""
    from . import forecast
    before, fb = _snapshot(con), forecast.forecast(con)
    res = do()
    after, fa = _snapshot(con), forecast.forecast(con)
    affected, freed = _compare(before, after, None)
    moved, earlier = _forecast_affected(con, fb, fa)
    imp = _finish(con, None, {"kind": "calendar", "summary": res["summary"]}, affected + moved, freed + earlier, [])
    imp["change_id"] = signals.record(con, user["id"], "calendar", None, imp["summary"], imp["affected"], note,
                                      link="#/kalendorius")
    return {**res, **imp}


def _forecast_affected(con, fb, fa) -> tuple[list[dict], list[str]]:
    """Kurių projektų operacijos dėl kalendoriaus baigsis vėliau (≥ 1 val.)
    arba nebespės iki etapo pabaigos; kurių – anksčiau."""
    ids = [i for i in fa if i in fb]
    info = {r["id"]: r for r in db.rows(con.execute(
        f"SELECT t.id, t.project_id, t.name, c.code AS centre, a.code AS asm FROM tasks t "
        f"JOIN work_centres c ON c.id=t.centre_id JOIN assemblies a ON a.id=t.assembly_id "
        f"WHERE t.id IN ({','.join('?' * len(ids))})", ids))} if ids else {}
    per, early = {}, {}
    fmt = workcal.local_text
    for i in ids:
        a, b = fb[i], fa[i]
        if not (a["end"] or b["end"]):
            continue
        t = info[i]
        late = (b["end"] is None) or (a["end"] and b["end"] > a["end"]
                                      and (db.parse_ts(b["end"]) - db.parse_ts(a["end"])).total_seconds() >= 3600)
        if late:
            x = per.setdefault(t["project_id"], {"project_id": t["project_id"], "severity": "yellow", "reasons": []})
            newly = b["late"] and not a["late"]
            if newly:
                x["severity"] = "red"
            x["reasons"].append(f"{t['centre']}: {t['asm']} · {t['name']} baigsis {fmt(a['end'])} → {fmt(b['end'])}"
                                + (f" – nespės iki {b['due']}" if newly else ""))
        elif a["end"] and b["end"] and (db.parse_ts(a["end"]) - db.parse_ts(b["end"])).total_seconds() >= 3600:
            early[t["project_id"]] = early.get(t["project_id"], 0) + 1
    for x in per.values():
        if len(x["reasons"]) > 5:
            x["reasons"] = x["reasons"][:5] + [f"ir dar {len(x['reasons']) - 5} operacijų"]
    codes = dict(con.execute("SELECT id, code FROM projects").fetchall())
    return list(per.values()), [f"{codes.get(p)}: {n} operacijų baigsis anksčiau" for p, n in early.items()]


def impact_of_activation(con, project_id) -> dict:
    """Projektas JAU vykdomas: palyginama su būsena, kai jis dar buvo krepšelyje."""
    after = _snapshot(con)
    con.execute("SAVEPOINT plan_activate")
    try:
        con.execute("UPDATE projects SET status='krepselis' WHERE id=?", (project_id,))
        before = _snapshot(con)
    finally:
        con.execute("ROLLBACK TO plan_activate")
        con.execute("RELEASE plan_activate")
    affected, freed = _compare(before, after, project_id, committed_only=True)
    return _finish(con, project_id, {"kind": "activate", "project_id": project_id}, affected, freed, [])
