"""Cecho būsena realiu laiku ir efektyvumo analitika.

Visi skaičiai kyla iš tų pačių įrašų, kuriuos rašo terminalas (intervalai,
pauzės, kiekiai) ir etapų žymos, tad analitika negali rodyti kitko, nei
matė cechas.
"""

from __future__ import annotations

from collections import defaultdict
from statistics import median

from .. import db
from .projects import PHASE_LABEL
from .tasks import PAUSE_LABEL, _secs, _work_seconds, block_reason

# Planuotos pauzės nėra nuostolis: jos rodomos, bet į centro prastovą neįeina,
# kitaip nakties „pamainos pabaiga“ užgožtų tikras priežastis.
PLANNED_PAUSES = {"pertrauka", "pamaina"}


def floor(con) -> list[dict]:
    """Kiekvienas darbo centras: dirba / pristabdyta / gali pradėti / laukia / nėra darbų."""
    out = []
    for c in db.rows(con.execute("SELECT * FROM work_centres WHERE active=1 ORDER BY sort, code")):
        st = {"centre": c, "state": "tuscia", "task": None, "next": None, "lock": None, "queue": 0}
        run = db.row(con.execute(
            "SELECT t.*, a.code AS assembly_code, p.code AS project_code FROM tasks t "
            "JOIN assemblies a ON a.id=t.assembly_id JOIN projects p ON p.id=t.project_id "
            "WHERE t.centre_id=? AND t.status IN ('vykdoma','pristabdyta') LIMIT 1", (c["id"],)))
        queue = db.rows(con.execute(
            "SELECT t.*, a.code AS assembly_code, p.code AS project_code FROM tasks t "
            "JOIN assemblies a ON a.id=t.assembly_id JOIN projects p ON p.id=t.project_id "
            "WHERE t.centre_id=? AND t.approved=1 AND t.status='laukia' ORDER BY t.queue_pos, t.id", (c["id"],)))
        st["queue"] = len(queue)
        if run:
            iv = db.row(con.execute("SELECT i.start, u.name FROM intervals i LEFT JOIN users u ON u.id=i.user_id "
                                    "WHERE task_id=? AND end IS NULL", (run["id"],)))
            pz = db.row(con.execute("SELECT p.start, p.reason, p.note, u.name FROM pauses p "
                                    "LEFT JOIN users u ON u.id=p.user_id WHERE task_id=? AND end IS NULL",
                                    (run["id"],)))
            st["task"] = run
            st["work_s"] = round(_work_seconds(con, run["id"], closed_only=True))
            if pz:
                st["state"] = "pristabdyta"
                st["since"], st["who"] = pz["start"], pz["name"]
                st["pause"] = PAUSE_LABEL.get(pz["reason"], pz["reason"]) + (f" – {pz['note']}" if pz["note"] else "")
            else:
                st["state"] = "dirba"
                st["since"], st["who"] = (iv or {}).get("start"), (iv or {}).get("name")
        elif queue:
            nxt = {**queue[0], "strict_order": c["strict_order"]}
            st["next"] = nxt
            st["lock"] = block_reason(con, nxt)
            st["state"] = "laukia" if st["lock"] else "gali"
        out.append(st)
    return out


def _in_range(start, end, a, b):
    """Intervalo dalis [a, b] ribose sekundėmis."""
    s = max(start, a) if a else start
    e = min(end, b) if b else end
    return max(0.0, (db.parse_ts(e) - db.parse_ts(s)).total_seconds()) if e > s else 0.0


def report(con, date_from: str | None = None, date_to: str | None = None) -> dict:
    """Efektyvumo ataskaita laikotarpiui (datos YYYY-MM-DD, imtinai)."""
    a = f"{date_from}T00:00:00+00:00" if date_from else None
    b = f"{date_to}T23:59:59+00:00" if date_to else None
    now = db.now()

    centres = {c["id"]: c for c in db.rows(con.execute("SELECT * FROM work_centres"))}
    per_c = defaultdict(lambda: {"work_s": 0.0, "pause_s": 0.0, "tasks_done": 0, "norm_s": 0.0,
                                 "fact_s_done": 0.0, "good": 0, "scrap": 0})
    task_work = defaultdict(float)
    for r in con.execute("SELECT i.task_id, i.start, i.end, t.centre_id FROM intervals i "
                         "JOIN tasks t ON t.id=i.task_id"):
        s = _in_range(r["start"], r["end"] or now, a, b)
        per_c[r["centre_id"]]["work_s"] += s
        task_work[r["task_id"]] += _secs(r["start"], r["end"])

    pauses = defaultdict(lambda: {"count": 0, "seconds": 0.0})
    for r in con.execute("SELECT p.*, t.centre_id FROM pauses p JOIN tasks t ON t.id=p.task_id"):
        s = _in_range(r["start"], r["end"] or now, a, b)
        if s <= 0:
            continue
        if r["reason"] not in PLANNED_PAUSES:
            per_c[r["centre_id"]]["pause_s"] += s
        pauses[r["reason"]]["count"] += 1
        pauses[r["reason"]]["seconds"] += s

    # užbaigtos užduotys: baigimo momentas – paskutinio intervalo pabaiga
    done = db.rows(con.execute(
        "SELECT t.*, (SELECT MAX(end) FROM intervals i WHERE i.task_id=t.id) AS finished "
        "FROM tasks t WHERE t.status='baigta'"))
    deviations = []
    for t in done:
        if not t["finished"] or (a and t["finished"] < a) or (b and t["finished"] > b):
            continue
        c = per_c[t["centre_id"]]
        c["tasks_done"] += 1
        c["good"] += t["qty_good"]
        c["scrap"] += t["qty_scrap"]
        fact = task_work[t["id"]]
        c["fact_s_done"] += fact
        if t["norm_min"]:
            norm = t["norm_min"] * 60 * max(t["qty_plan"], 1)
            c["norm_s"] += norm
            deviations.append({"task_id": t["id"], "name": t["name"], "centre": centres[t["centre_id"]]["code"],
                               "norm_s": norm, "fact_s": fact, "ratio": fact / norm if norm else None})

    centre_rows = []
    for cid, v in per_c.items():
        c = centres.get(cid)
        if not c:
            continue
        busy = v["work_s"] + v["pause_s"]
        centre_rows.append({
            "code": c["code"], "name": c["name"], **{k: round(x) if isinstance(x, float) else x for k, x in v.items()},
            "pause_share": round(v["pause_s"] / busy, 3) if busy else 0,
            "norm_ratio": round(v["fact_s_done"] / v["norm_s"], 2) if v["norm_s"] else None,
            "scrap_share": round(v["scrap"] / (v["good"] + v["scrap"]), 3) if (v["good"] + v["scrap"]) else 0,
        })
    centre_rows.sort(key=lambda x: -x["work_s"])

    pause_rows = sorted(({"reason": k, "label": PAUSE_LABEL.get(k, k), "count": v["count"],
                          "seconds": round(v["seconds"]), "planned": k in PLANNED_PAUSES}
                         for k, v in pauses.items()), key=lambda x: (x["planned"], -x["seconds"]))

    # laukimas maršrute: nuo ankstesnės operacijos pabaigos iki kitos pradžios
    waits = defaultdict(list)
    by_asm = defaultdict(list)
    for t in db.rows(con.execute(
            "SELECT t.id, t.assembly_id, t.seq, t.centre_id, "
            "(SELECT MIN(start) FROM intervals i WHERE i.task_id=t.id) AS first_start, "
            "(SELECT MAX(end) FROM intervals i WHERE i.task_id=t.id) AS last_end FROM tasks t")):
        by_asm[t["assembly_id"]].append(t)
    for lst in by_asm.values():
        lst.sort(key=lambda x: x["seq"])
        for prev, cur in zip(lst, lst[1:]):
            if prev["last_end"] and cur["first_start"] and (not a or cur["first_start"] >= a) \
                    and (not b or cur["first_start"] <= b):
                w = (db.parse_ts(cur["first_start"]) - db.parse_ts(prev["last_end"])).total_seconds()
                if w > 0:
                    waits[cur["centre_id"]].append(w)
    wait_rows = sorted(({"code": centres[cid]["code"], "name": centres[cid]["name"], "count": len(v),
                         "median_s": round(median(v)), "total_s": round(sum(v))} for cid, v in waits.items()),
                       key=lambda x: -x["median_s"])

    # etapai: planas prieš faktą (dienomis)
    phase_rows = defaultdict(lambda: {"count": 0, "late": 0, "plan_d": 0.0, "fact_d": 0.0})
    for ph in db.rows(con.execute("SELECT * FROM phases WHERE status='baigta'")):
        if (a and (ph["actual_end"] or "") < a) or (b and (ph["actual_end"] or "") > b):
            continue
        r = phase_rows[ph["kind"]]
        r["count"] += 1
        fact = (db.parse_ts(ph["actual_end"]) - db.parse_ts(ph["actual_start"])).total_seconds() / 86400
        r["fact_d"] += fact
        if ph["plan_start"] and ph["plan_end"]:
            from datetime import date
            plan = (date.fromisoformat(ph["plan_end"]) - date.fromisoformat(ph["plan_start"])).days + 1
            r["plan_d"] += plan
            if ph["actual_end"][:10] > ph["plan_end"]:
                r["late"] += 1
    phases_out = [{"kind": k, "label": PHASE_LABEL.get(k, k), "count": v["count"], "late": v["late"],
                   "avg_fact_d": round(v["fact_d"] / v["count"], 1), "avg_plan_d": round(v["plan_d"] / v["count"], 1)}
                  for k, v in phase_rows.items()]

    ncr = db.rows(con.execute(
        "SELECT category, COUNT(*) AS n FROM ncr WHERE (? IS NULL OR reported_at>=?) AND (? IS NULL OR reported_at<=?) "
        "GROUP BY category ORDER BY n DESC", (a, a, b, b)))

    from .components import supplier_report

    deviations.sort(key=lambda x: -(x["ratio"] or 0))
    return {"from": date_from, "to": date_to, "centres": centre_rows, "pauses": pause_rows,
            "waits": wait_rows, "phases": phases_out, "suppliers": supplier_report(con, a, b), "ncr": ncr, "worst_tasks": deviations[:10],
            "totals": {"work_s": round(sum(x["work_s"] for x in centre_rows)),
                       "pause_s": round(sum(x["pause_s"] for x in centre_rows)),
                       "tasks_done": sum(x["tasks_done"] for x in centre_rows),
                       "scrap": sum(x["scrap"] for x in centre_rows)}}
