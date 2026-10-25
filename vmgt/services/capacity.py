"""Resursų apkrova: departamentų poreikis prieš pajėgumą savaitėmis.

Vartotojo sprendimai (2026-10-25): departamentai – biuro skyriai IR gamybos
barai; poreikis – etapų planuojamos valandos ir cecho operacijų normos;
žingsnis – savaitė. Tikslas – matyti, kiek projektų vykdoma, kur trūksta
žmonių ir kiek dar galima prisiimti.

Iš kur valandos:

| Departamentas | Poreikis |
|---|---|
| biuro skyrius | etapo `hours`, paskirstytos tolygiai per etapo darbo dienas |
| gamybos baras | likusios cecho operacijų normos (norma × likęs kiekis), išdėstytos per to mazgo gamybos / surinkimo etapo laikotarpį; kol operacijų dar nėra (krepšelio projektas) – etapo `hours`, jei nurodytas baras |

Kad tas pats darbas nebūtų skaičiuojamas du kartus, gamybos etapo `hours`
naudojamos tik tol, kol jo apimtyje nėra nė vienos cecho operacijos: kai
technologas sudaro maršrutą, tikslios normos pakeičia įvertį.

Pajėgumas = žmonės × valandos per savaitę × prieinamumas (dalis laiko,
kuri lieka projektams po atostogų, ligų ir kitų darbų).

Krepšelio (dar nepradėti) projektai skaičiuojami ATSKIRAI – iš to ir
matosi, ką reikštų juos priimti.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta

from .. import db
from . import NotFound, RuleError
from .tasks import CENTRE_PHASE

PRODUCTION_KINDS = ("gamyba", "surinkimas")
WARN_UTIL = 0.85      # nuo čia – įspėjimas, beveik pilna
OVER_UTIL = 1.0       # virš – trūksta resurso


# ---------- departamentai ----------

def list_departments(con, active_only=False) -> list[dict]:
    q = ("SELECT d.*, ar.code AS area_code, ar.name AS area_name FROM departments d "
         "LEFT JOIN areas ar ON ar.id=d.area_id")
    if active_only:
        q += " WHERE d.active=1"
    out = db.rows(con.execute(q + " ORDER BY d.kind='production', d.sort, d.code"))
    for d in out:
        d["capacity_week"] = round(capacity_week(d), 1)
        d["phase_kind_list"] = [k for k in d["phase_kinds"].split(",") if k]
    return out


def capacity_week(d: dict) -> float:
    return d["headcount"] * d["hours_per_week"] * d["availability"]


def save_department(con, by, data: dict, dept_id=None) -> int:
    vals = {k: data[k] for k in ("code", "name", "kind", "area_id", "phase_kinds", "headcount",
                                  "hours_per_week", "availability", "sort", "active") if k in data}
    for k in ("headcount", "hours_per_week", "availability"):
        if k in vals:
            vals[k] = float(vals[k])
            if vals[k] < 0:
                raise RuleError("Reikšmės negali būti neigiamos")
    if "availability" in vals and vals["availability"] > 1:
        vals["availability"] = vals["availability"] / 100     # įvesta procentais
    if isinstance(vals.get("phase_kinds"), list):
        vals["phase_kinds"] = ",".join(vals["phase_kinds"])
    if dept_id is None:
        if not vals.get("code") or not vals.get("name"):
            raise RuleError("Reikia departamento kodo ir pavadinimo")
        if con.execute("SELECT 1 FROM departments WHERE code=?", (vals["code"],)).fetchone():
            raise RuleError(f"Departamentas {vals['code']} jau yra")
        vals.setdefault("sort", con.execute("SELECT COALESCE(MAX(sort),0)+1 FROM departments").fetchone()[0])
        cur = con.execute(f"INSERT INTO departments ({', '.join(vals)}) VALUES ({', '.join('?' * len(vals))})",
                          tuple(vals.values()))
        db.log_event(con, by, "department", cur.lastrowid, "create", vals)
        return cur.lastrowid
    if not con.execute("SELECT 1 FROM departments WHERE id=?", (dept_id,)).fetchone():
        raise NotFound("Departamento nėra")
    if vals:
        con.execute(f"UPDATE departments SET {', '.join(k + '=?' for k in vals)} WHERE id=?",
                    (*vals.values(), dept_id))
        db.log_event(con, by, "department", dept_id, "update", vals)
    return dept_id


# ---------- laikas ----------

def monday(d: date) -> date:
    return d - timedelta(days=d.weekday())


def workdays(a: date, b: date) -> list[date]:
    """Darbo dienos [a, b] imtinai."""
    out, x = [], a
    while x <= b:
        if x.weekday() < 5:
            out.append(x)
        x += timedelta(days=1)
    return out


def spread(hours: float, start: date, end: date, today: date, status: str) -> tuple[dict, str | None]:
    """Paskirsto valandas savaitėms. Grąžina ({savaitės pirmadienis: val.}, pastaba).

    - nepradėtas etapas, kurio pradžia praėjo, pasislenka į šiandien (darbas
      nepadarytas, tad jo trukmė tęsiasi nuo dabar);
    - vykdomo etapo praėjusių dienų dalis laikoma atlikta pagal planą;
    - vykdomas, bet vėluojantis etapas – likutis nežinomas, tad jo savaitės
      tempas tęsiamas dar vieną savaitę (konservatyviai, kad vėlavimas
      nepradingtų iš apkrovos).
    """
    if not hours or not start or not end or end < start:
        return {}, "be datų"
    days = workdays(start, end) or [start]
    rate = hours / len(days)
    note = None
    if status == "planuota" and start < today:
        # tiek pat DARBO dienų nuo šiandien: perkėlus kalendorinėmis dienomis
        # savaitgalis „suvalgytų“ dalį valandų
        n, x, days = len(days), today, []
        while len(days) < n:
            if x.weekday() < 5:
                days.append(x)
            x += timedelta(days=1)
        note = "pradžia pasislinko"
    elif end < today:
        wk = workdays(today, today + timedelta(days=6))[:5]
        days = wk
        rate = min(hours, rate * len(wk)) / len(wk)
        note = "vėluoja – tempas tęsiamas savaitę"
    out = defaultdict(float)
    for x in days:
        if x >= today:
            out[monday(x)] += rate
    return dict(out), note


# ---------- poreikis ----------

def _phase_has_tasks(con, ph) -> bool:
    """Ar gamybos etapo apimtyje jau yra cecho operacijų (tada normos tikslesnės)."""
    rows = con.execute(
        "SELECT c.kind FROM tasks t JOIN work_centres c ON c.id=t.centre_id WHERE t.project_id=? "
        + ("AND t.assembly_id=?" if ph["assembly_id"] else ""),
        (ph["project_id"], ph["assembly_id"]) if ph["assembly_id"] else (ph["project_id"],)).fetchall()
    return any(CENTRE_PHASE.get(r[0], "gamyba") == ph["kind"] for r in rows)


def report(con, weeks: int = 12, include_basket: bool = True, start: date | None = None) -> dict:
    today = date.fromisoformat(db.now()[:10])
    base = start or today
    # savaitgalį einamoji savaitė jau baigta – rodoma nuo kitos
    w0 = monday(base) if base.weekday() < 5 else monday(base) + timedelta(weeks=1)
    week_list = [w0 + timedelta(weeks=i) for i in range(weeks)]
    depts = list_departments(con, active_only=True)
    by_kind = {}
    for d in depts:
        for k in d["phase_kind_list"]:
            by_kind.setdefault(k, d["id"])
    by_area = {d["area_id"]: d["id"] for d in depts if d["kind"] == "production" and d["area_id"]}

    projects = {p["id"]: p for p in db.rows(con.execute(
        "SELECT id, code, name, status, due_date, priority FROM projects WHERE status IN ('vykdomas','krepselis')"))}
    # load[dept][week][project] = val.
    load = defaultdict(lambda: defaultdict(lambda: defaultdict(float)))
    unassigned, notes = [], []

    def add(dept_id, project_id, weeks_hours):
        for w, h in weeks_hours.items():
            if w < w0:
                continue
            key = w if w < w0 + timedelta(weeks=weeks) else "later"
            load[dept_id][key][project_id] += h

    phases = db.rows(con.execute(
        "SELECT ph.*, a.code AS assembly_code FROM phases ph LEFT JOIN assemblies a ON a.id=ph.assembly_id "
        "WHERE ph.status != 'baigta'"))
    for ph in phases:
        if ph["project_id"] not in projects:
            continue
        p = projects[ph["project_id"]]
        name = f"{p['code']} {ph['assembly_code'] or ''} {ph['kind']}".replace("  ", " ")
        if ph["kind"] in PRODUCTION_KINDS:
            if _phase_has_tasks(con, ph):
                continue                                   # skaičiuojama iš operacijų normų
            dept = ph["department_id"]
        else:
            dept = ph["department_id"] or by_kind.get(ph["kind"])
        if not ph["hours"]:
            if ph["kind"] not in PRODUCTION_KINDS or not _phase_has_tasks(con, ph):
                unassigned.append({"project": p["code"], "project_id": p["id"], "phase_id": ph["id"], "what": name,
                                   "why": "nenurodytos planuojamos valandos"})
            continue
        if not dept:
            unassigned.append({"project": p["code"], "project_id": p["id"], "phase_id": ph["id"], "what": name,
                               "why": "nenurodytas departamentas (barui – kuriame bus gaminama)"})
            continue
        wh, note = spread(ph["hours"], _d(ph["plan_start"]), _d(ph["plan_end"]), today, ph["status"])
        if note and note != "be datų":
            notes.append(f"{name}: {note}")
        if note == "be datų":
            unassigned.append({"project": p["code"], "project_id": p["id"], "phase_id": ph["id"], "what": name,
                               "why": "nenurodytos etapo datos"})
            continue
        add(dept, p["id"], wh)

    # cecho operacijos – likusios normos valandos
    tasks = db.rows(con.execute(
        "SELECT t.*, c.kind AS centre_kind, c.area_id FROM tasks t JOIN work_centres c ON c.id=t.centre_id "
        "WHERE t.status != 'baigta'"))
    for t in tasks:
        if t["project_id"] not in projects or not t["norm_min"]:
            continue
        left = max(0, t["qty_plan"] - t["qty_good"] - t["qty_scrap"])
        hours = t["norm_min"] * left / 60
        if hours <= 0:
            continue
        dept = by_area.get(t["area_id"])
        if not dept:
            unassigned.append({"project": projects[t["project_id"]]["code"], "project_id": t["project_id"],
                               "what": t["name"], "why": "darbo centro baras neturi departamento"})
            continue
        kind = CENTRE_PHASE.get(t["centre_kind"], "gamyba")
        ph = db.row(con.execute(
            "SELECT plan_start, plan_end FROM phases WHERE project_id=? AND kind=? AND (assembly_id=? OR assembly_id IS NULL) "
            "ORDER BY assembly_id IS NULL LIMIT 1", (t["project_id"], kind, t["assembly_id"])))
        a, b = (_d(ph["plan_start"]), _d(ph["plan_end"])) if ph else (None, None)
        if a and b and b >= today:
            # likęs darbas – per likusias etapo dienas (ne anksčiau nei šiandien)
            wh, _ = spread(hours, max(a, today), b, today, "vykdoma")
        else:
            # etapo nėra arba jis jau turėjo baigtis – likutis vis tiek padaromas, šią savaitę
            wh = {monday(today): hours}
        add(dept, t["project_id"], wh)

    # ---------- suvestinė ----------
    rows, shortages = [], []
    for d in depts:
        cap = capacity_week(d)
        cells = []
        for w in week_list:
            per = load[d["id"]].get(w, {})
            committed = sum(h for pid, h in per.items() if projects[pid]["status"] == "vykdomas")
            basket = sum(h for pid, h in per.items() if projects[pid]["status"] == "krepselis")
            total = committed + (basket if include_basket else 0)
            util = total / cap if cap else (None if not total else float("inf"))
            cell = {"week": w.isoformat(), "committed": round(committed, 1), "basket": round(basket, 1),
                    "capacity": round(cap, 1), "util": round(util, 3) if util not in (None, float("inf")) else util,
                    "shortage": round(max(0.0, total - cap), 1),
                    "projects": sorted(({"project_id": pid, "code": projects[pid]["code"], "hours": round(h, 1),
                                         "basket": projects[pid]["status"] == "krepselis"}
                                        for pid, h in per.items() if h > 0.05), key=lambda x: -x["hours"])}
            cells.append(cell)
            if cell["shortage"] > 0.5:
                shortages.append({"department": d["name"], "code": d["code"], "week": cell["week"],
                                  # ar trūksta jau dabar, ar tik priėmus krepšelio projektus
                                  "basket_only": committed <= cap,
                                  "demand": round(total, 1), "capacity": cell["capacity"], "shortage": cell["shortage"],
                                  "people": round(cell["shortage"] / (d["hours_per_week"] * d["availability"]), 1)
                                  if d["hours_per_week"] * d["availability"] else None,
                                  "projects": cell["projects"][:4]})
        later = load[d["id"]].get("later", {})
        free = sum(max(0.0, c["capacity"] - c["committed"]) for c in cells)
        peak = max((c["util"] for c in cells if isinstance(c["util"], (int, float))), default=0)
        rows.append({**{k: d[k] for k in ("id", "code", "name", "kind", "headcount", "hours_per_week", "availability",
                                           "area_name")},
                     "capacity_week": round(cap, 1), "cells": cells, "peak_util": peak,
                     "free_hours": round(free, 1),
                     "basket_hours": round(sum(c["basket"] for c in cells), 1),
                     "later_hours": round(sum(later.values()), 1)})
    shortages.sort(key=lambda x: (x["week"], -x["shortage"]))

    active = [p for p in projects.values() if p["status"] == "vykdomas"]
    basket = [p for p in projects.values() if p["status"] == "krepselis"]
    # Ar krepšelio projektą galima priimti: KIEKVIENĄ savaitę vykdomi + šis
    # projektas turi tilpti į pajėgumą. Lyginti viso laikotarpio sumas
    # negalima – 700 val. „tilptų“ į 12 sav. laisvą laiką, nors darbas
    # suplanuotas per 2 savaites ir tada trūksta pusės žmonių.
    fit = []
    for p in sorted(basket, key=lambda x: (x["priority"], x["due_date"] or "9999")):
        need = []
        for r in rows:
            h, over, worst = 0.0, 0.0, None
            for c in r["cells"]:
                mine = sum(x["hours"] for x in c["projects"] if x["project_id"] == p["id"])
                h += mine
                ex = c["committed"] + mine - c["capacity"]
                if mine > 0.05 and ex > 0.5:          # trūkumą sukelia (bent dalį) šis projektas
                    over += min(ex, mine)
                    if worst is None or ex > worst[1]:
                        worst = (c["week"], round(ex, 1))
            if h > 0.05:
                need.append({"code": r["code"], "name": r["name"], "hours": round(h, 1),
                             "over": round(over, 1), "worst_week": worst[0] if worst else None,
                             "ok": over <= 0.5})
        fit.append({"project_id": p["id"], "code": p["code"], "name": p["name"], "due_date": p["due_date"],
                    "needs": need, "fits": all(n["ok"] for n in need) if need else None})

    return {"today": today.isoformat(), "weeks": [{"start": w.isoformat(), "label": f"S{w.isocalendar()[1]}"}
                                                   for w in week_list],
            "include_basket": include_basket, "departments": rows, "shortages": shortages,
            "unassigned": unassigned, "notes": sorted(set(notes)),
            "projects_active": len(active), "projects_basket": len(basket), "basket_fit": fit,
            "thresholds": {"warn": WARN_UTIL, "over": OVER_UTIL}}


def _d(s):
    return date.fromisoformat(s[:10]) if s else None
