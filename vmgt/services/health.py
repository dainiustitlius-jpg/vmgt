"""Projekto „sveikata“ realiu laiku: faktas lyginamas su planu.

Keturios sritys (vartotojo pasirinkimas 2026-10-25): terminai ir etapai,
užduotys ir gamyba, komponentai, kokybė. Kiekviena gauna lygį
(žalia / geltona / raudona), trumpą išvadą ir PRIEŽASČIŲ sąrašą – lygis be
priežasties nieko nepasako, o priežastis rodo, ką daryti.

Viskas skaičiuojama iš tų pačių duomenų, kuriuos rodo kiti langai, tad
sveikata negali prieštarauti cechui ar pirkimams. Ribos – `LIMITS`, kad jas
būtų galima derinti vienoje vietoje.
"""

from __future__ import annotations

from datetime import date, timedelta

from .. import db
from . import actions as actions_mod
from . import components
from .projects import PHASE_LABEL

LEVEL_SCORE = {"green": 100, "yellow": 60, "red": 20}
LEVEL_LABEL = {"green": "Gerai", "yellow": "Dėmesio", "red": "Kritiška"}
WEIGHTS = {"schedule": 0.35, "execution": 0.25, "components": 0.25, "quality": 0.15}

LIMITS = {
    "phase_overdue_red_d": 5,       # etapas vėluoja ilgiau – raudona
    "late_start_yellow_d": 2,       # etapas turėjo prasidėti prieš tiek dienų
    "progress_gap_yellow": 0.10,    # gamyba atsilieka nuo laiko eigos
    "progress_gap_red": 0.25,
    "norm_ratio_yellow": 1.2,       # faktas / norma atliktose operacijose
    "norm_ratio_red": 1.5,
    "actions_overdue_red": 3,       # tiek ir daugiau vėluojančių užduočių
    "action_overdue_red_d": 7,      # arba bent viena vėluoja ilgiau
    "ncr_open_red": 3,
    "ncr_age_red_d": 7,
    "scrap_yellow": 0.0,
    "scrap_red": 0.05,
    "need_soon_d": 7,               # komponento reikia per tiek dienų
}

_RANK = {"green": 0, "yellow": 1, "red": 2}


def _worst(*levels):
    return max(levels, key=lambda x: _RANK[x]) if levels else "green"


def _d(s):
    return date.fromisoformat(s[:10]) if s else None


def _dim(key, label, level, headline, reasons, metrics):
    return {"key": key, "label": label, "level": level, "level_label": LEVEL_LABEL[level],
            "score": LEVEL_SCORE[level], "headline": headline, "reasons": reasons, "metrics": metrics}


def _schedule(con, p, today):
    phases = db.rows(con.execute(
        "SELECT ph.*, a.code AS assembly_code FROM phases ph LEFT JOIN assemblies a ON a.id=ph.assembly_id "
        "WHERE ph.project_id=?", (p["id"],)))
    reasons, levels, slip = [], [], 0
    open_ends = []
    late_done = 0
    for ph in phases:
        name = f"{ph['assembly_code'] + ' · ' if ph['assembly_code'] else ''}{PHASE_LABEL.get(ph['kind'], ph['kind'])}"
        ps, pe = _d(ph["plan_start"]), _d(ph["plan_end"])
        if ph["status"] == "baigta":
            if pe and ph["actual_end"] and _d(ph["actual_end"]) > pe:
                late_done += 1
            continue
        if pe:
            open_ends.append(pe)
        if pe and pe < today:
            od = (today - pe).days
            slip = max(slip, od)
            lvl = "red" if od > LIMITS["phase_overdue_red_d"] else "yellow"
            levels.append(lvl)
            reasons.append({"level": lvl, "text": f"{name}: turėjo baigtis {pe}, vėluoja {od} d."})
        elif ph["status"] == "planuota" and ps and ps < today:
            ls = (today - ps).days
            slip = max(slip, ls)
            lvl = "yellow" if ls > LIMITS["late_start_yellow_d"] else "green"
            levels.append(lvl)
            if lvl != "green":
                reasons.append({"level": lvl, "text": f"{name}: turėjo prasidėti {ps}, dar nepradėta ({ls} d.)"})
    # Prognozė paprasta ir paaiškinama: didžiausias dabartinis vėlavimas
    # perkeliamas į paskutinio neužbaigto etapo pabaigą – „jei atsilikimo
    # nepavysime“. Tikslesnei reikėtų etapų priklausomybių (vėlesnis etapas).
    forecast = (max(open_ends) + timedelta(days=slip)) if open_ends else None
    due = _d(p["due_date"])
    if due and forecast and forecast > due:
        levels.append("red")
        reasons.insert(0, {"level": "red", "text": f"Prognozuojama pabaiga {forecast} vėlesnė už terminą {due} "
                                                   f"({(forecast - due).days} d.)"})
    if due and due < today and p["status"] != "baigtas":
        levels.append("red")
        reasons.insert(0, {"level": "red", "text": f"Projekto terminas {due} jau praėjo"})
    if not phases:
        reasons.append({"level": "yellow", "text": "Projektui nesudarytas etapų planas"})
        levels.append("yellow")
    lvl = _worst(*levels) if levels else "green"
    head = {"green": "Etapai vyksta pagal planą", "yellow": "Yra atsilikimų nuo plano",
            "red": "Terminas rizikoje"}[lvl]
    return _dim("schedule", "Terminai ir etapai", lvl, head, reasons, {
        "phases": len(phases), "phases_done": sum(1 for x in phases if x["status"] == "baigta"),
        "slip_days": slip, "forecast_end": forecast.isoformat() if forecast else None,
        "due_date": p["due_date"], "late_done": late_done})


def _execution(con, p, today):
    reasons, levels = [], []
    acts = actions_mod.list_actions(con, project_id=p["id"], status="open")
    overdue = [x for x in acts if x["overdue"]]
    waiting = [x for x in acts if x["status"] == "laukia"]
    if overdue:
        oldest = max((today - _d(x["due_date"])).days for x in overdue)
        lvl = "red" if len(overdue) >= LIMITS["actions_overdue_red"] or oldest > LIMITS["action_overdue_red_d"] else "yellow"
        levels.append(lvl)
        reasons.append({"level": lvl, "text": f"Vėluoja užduočių: {len(overdue)} (seniausia – {oldest} d.): "
                        + ", ".join(x["title"] for x in overdue[:3]) + ("…" if len(overdue) > 3 else "")})
    if waiting:
        levels.append("yellow")
        reasons.append({"level": "yellow", "text": f"Laukia: {len(waiting)} – "
                        + "; ".join(f"{x['title']} ({x['wait_reason']})" for x in waiting[:3])})

    # gamyba: atlikta dalis (pagal normuotas valandas) prieš laiko eigą gamybos etapuose
    ops = db.rows(con.execute("SELECT status, qty_plan, qty_good, norm_min, id FROM tasks WHERE project_id=?",
                              (p["id"],)))
    total = done = 0.0
    for t in ops:
        w = (t["norm_min"] or 1) * max(t["qty_plan"], 1)
        total += w
        done += w if t["status"] == "baigta" else w * min(1, t["qty_good"] / max(t["qty_plan"], 1))
    actual = done / total if total else None
    win = con.execute("SELECT MIN(plan_start), MAX(plan_end) FROM phases WHERE project_id=? "
                      "AND kind IN ('gamyba','surinkimas','testavimas')", (p["id"],)).fetchone()
    expected = None
    if win[0] and win[1]:
        a, b = _d(win[0]), _d(win[1]) + timedelta(days=1)
        expected = min(1.0, max(0.0, (today - a).days / max(1, (b - a).days)))
    if actual is not None and expected is not None:
        gap = expected - actual
        if gap > LIMITS["progress_gap_red"]:
            lvl = "red"
        elif gap > LIMITS["progress_gap_yellow"]:
            lvl = "yellow"
        else:
            lvl = "green"
        levels.append(lvl)
        if lvl != "green":
            reasons.append({"level": lvl, "text": f"Gamyba atsilieka: atlikta {round(100 * actual)}%, "
                                                  f"pagal planą turėtų būti ~{round(100 * expected)}%"})
    # faktas prieš normą atliktose operacijose
    from .tasks import _work_seconds
    norm = fact = 0.0
    for t in ops:
        if t["status"] == "baigta" and t["norm_min"]:
            norm += t["norm_min"] * 60 * max(t["qty_plan"], 1)
            fact += _work_seconds(con, t["id"])
    ratio = fact / norm if norm else None
    if ratio and ratio > LIMITS["norm_ratio_yellow"]:
        lvl = "red" if ratio > LIMITS["norm_ratio_red"] else "yellow"
        levels.append(lvl)
        reasons.append({"level": lvl, "text": f"Atliktos operacijos užtruko {ratio:.2f} karto ilgiau nei normuota"})
    lvl = _worst(*levels) if levels else "green"
    head = {"green": "Užduotys ir gamyba pagal planą", "yellow": "Yra vėluojančių darbų",
            "red": "Darbai ženkliai atsilieka"}[lvl]
    return _dim("execution", "Užduotys ir gamyba", lvl, head, reasons, {
        "actions_open": len(acts), "actions_overdue": len(overdue), "actions_waiting": len(waiting),
        "ops_total": len(ops), "ops_done": sum(1 for t in ops if t["status"] == "baigta"),
        "progress_actual": round(actual, 3) if actual is not None else None,
        "progress_expected": round(expected, 3) if expected is not None else None,
        "norm_ratio": round(ratio, 2) if ratio else None})


def _components(con, p, today):
    rows = [c for c in components.list_components(con, project_id=p["id"]) if c["status"] != "atsaukta"]
    reasons, levels = [], []
    soon = (today + timedelta(days=LIMITS["need_soon_d"])).isoformat()
    for c in rows:
        if c["status"] == "gauta":
            continue
        nm = f"{c['name']}{' (' + c['assembly_code'] + ')' if c['assembly_code'] else ''}"
        if c["overdue_need"]:
            levels.append("red"); reasons.append({"level": "red", "text": f"{nm}: reikėjo iki {c['need_date']}, dar negauta"})
        elif c["late"]:
            lvl = "red" if c["need_date"] and c["need_date"] <= soon else "yellow"
            levels.append(lvl); reasons.append({"level": lvl, "text": f"{nm}: tiekėjas vėluoja (žadėta {c['promised_date']})"})
        elif c["risk"]:
            levels.append("yellow")
            why = "atvyks vėliau nei reikia" if c["promised_date"] else "reikia greitai, data nepatvirtinta"
            reasons.append({"level": "yellow", "text": f"{nm}: {why}"})
        elif c["status"] == "reikia":
            levels.append("yellow"); reasons.append({"level": "yellow", "text": f"{nm}: dar neužsakyta"})
    sm = components.summary(rows)
    lvl = _worst(*levels) if levels else "green"
    head = ("Pirkimų nėra" if not rows else
            {"green": f"Gauta {sm['received_pct']}%, rizikų nėra", "yellow": "Yra pirkimų rizikų",
             "red": "Trūkstami komponentai stabdys darbus"}[lvl])
    reasons.sort(key=lambda r: -_RANK[r["level"]])
    return _dim("components", "Komponentai", lvl, head, reasons, {
        "lines": len(rows), "received_pct": sm["received_pct"], "late": sm["late"], "risk": sm["risk"],
        "not_ordered": sm["by_status"]["reikia"]})


def _quality(con, p, today):
    reasons, levels = [], []
    open_ncr = db.rows(con.execute("SELECT * FROM ncr WHERE project_id=? AND status!='uzdaryta'", (p["id"],)))
    if open_ncr:
        oldest = max((today - _d(n["reported_at"])).days for n in open_ncr)
        lvl = "red" if len(open_ncr) >= LIMITS["ncr_open_red"] or oldest > LIMITS["ncr_age_red_d"] else "yellow"
        levels.append(lvl)
        reasons.append({"level": lvl, "text": f"Atvirų neatitikčių: {len(open_ncr)} (seniausia – {oldest} d.)"})
    good, scrap = con.execute("SELECT COALESCE(SUM(qty_good),0), COALESCE(SUM(qty_scrap),0) FROM tasks "
                              "WHERE project_id=?", (p["id"],)).fetchone()
    share = scrap / (good + scrap) if (good + scrap) else 0
    if scrap:
        lvl = "red" if share > LIMITS["scrap_red"] else "yellow"
        levels.append(lvl)
        reasons.append({"level": lvl, "text": f"Brokas: {scrap} vnt. ({round(100 * share, 1)}%)"})
    lvl = _worst(*levels) if levels else "green"
    head = {"green": "Neatitikčių nėra", "yellow": "Yra atvirų kokybės klausimų", "red": "Kokybės problemos"}[lvl]
    return _dim("quality", "Kokybė", lvl, head, reasons, {
        "ncr_open": len(open_ncr), "scrap": scrap, "scrap_share": round(share, 3)})


def project_health(con, project_id) -> dict:
    p = db.row(con.execute("SELECT * FROM projects WHERE id=?", (project_id,)))
    if not p:
        from . import NotFound
        raise NotFound("Projekto nėra")
    today = date.fromisoformat(db.now()[:10])
    dims = [_schedule(con, p, today), _execution(con, p, today), _components(con, p, today), _quality(con, p, today)]
    score = round(sum(WEIGHTS[d["key"]] * d["score"] for d in dims))
    # Bendras lygis – blogiausia sritis: vidurkis paslėptų vieną kritišką
    # sritį už trijų gerų, o būtent jos ir reikia nepraleisti.
    level = _worst(*(d["level"] for d in dims))
    return {"project_id": project_id, "updated": db.now(), "level": level, "level_label": LEVEL_LABEL[level],
            "score": score, "dimensions": dims, "limits": LIMITS}
