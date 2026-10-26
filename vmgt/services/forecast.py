"""Operacijų prognozė: kada kiekviena eilės operacija prasidės ir baigsis.

Vartotojo sprendimas (2026-10-26, darbo kalendorius): kalendorius turi rodyti
ne tik pajėgumą, bet ir **kiekvienos operacijos numatomą pradžią ir pabaigą**
pagal centro eilę, normas ir darbo laiką, ir ar ji spės iki etapo termino.

Kaip skaičiuojama:

- kiekviename centre operacijos eina eilės tvarka (`queue_pos`); vykdoma ar
  pristabdyta – pirma, jos likutis = norma × planas − jau dirbta (bet ne
  mažiau 15 % likusių vienetų normos – viršijus normą pabaiga vis tiek ateityje);
- operacija negali prasidėti anksčiau, nei baigsis ankstesnė srauto operacija
  (jei ji dar nieko neperdavė) ir mazgai, kurių laukia (`requires`) – tos
  pačios taisyklės kaip `tasks.block_reason`;
- laikas dedamas tik į centro darbo langus (`workcal`): šventės, remontai,
  papildomos pamainos keičia prognozę iškart;
- centrai priklauso vienas nuo kito, tad skaičiuojama pakartotinai, kol
  rezultatas nebesikeičia (dažniausiai 2–4 kartai).

Supaprastinimai (sąmoningai): eilė laikoma griežta ir ten, kur operatorius
gali rinktis; kokybės kontrolės laukimas ir derinimo laikas neprognozuojami.
"""

from __future__ import annotations

from .. import db
from . import routing, workcal
from .tasks import CENTRE_PHASE, _work_seconds

MIN_LEFT = 0.15
PASSES = 30


def forecast(con, cal: workcal.Calendar | None = None, now: str | None = None) -> dict[int, dict]:
    """{užduoties id: {start, end, due, late, wait, no_time, loop}} visoms neatliktoms
    vykdomų ir krepšelio projektų operacijoms."""
    cal = cal or workcal.Calendar(con)
    now_dt = db.parse_ts(now or db.now())
    rows = db.rows(con.execute(
        "SELECT t.*, c.code AS centre_code, p.due_date, p.status AS project_status, a.released_at FROM tasks t "
        "JOIN work_centres c ON c.id=t.centre_id JOIN projects p ON p.id=t.project_id "
        "JOIN assemblies a ON a.id=t.assembly_id "
        "WHERE t.status!='baigta' AND p.status IN ('vykdomas','krepselis') "
        "ORDER BY t.centre_id, t.status NOT IN ('vykdoma','pristabdyta'), t.queue_pos, t.id"))
    ids = {t["id"] for t in rows}
    by_centre, deps, dur = {}, {}, {}
    structs = {}
    for t in rows:
        by_centre.setdefault(t["centre_id"], []).append(t)
        st = structs.get(t["assembly_id"]) or structs.setdefault(t["assembly_id"], routing.structure(con, t["assembly_id"]))
        # ankstesnė srauto operacija, kuri dar nieko neperdavė – kaip `block_reason`
        d = [u["id"] for u in routing.upstream(con, t, st)
             if u["status"] != "baigta" and u["qty_good"] == 0 and u["id"] in ids]
        if routing.is_entry(con, t, st):
            req = con.execute("SELECT requires FROM assemblies WHERE id=?", (t["assembly_id"],)).fetchone()
            codes = [c for c in (req[0] if req else "").split(",") if c]
            if codes:
                d += [r[0] for r in con.execute(
                    f"SELECT x.id FROM tasks x JOIN assemblies a ON a.id=x.assembly_id WHERE a.project_id=? "
                    f"AND a.code IN ({','.join('?' * len(codes))}) AND x.status!='baigta'",
                    (t["project_id"], *codes)) if r[0] in ids]
        deps[t["id"]] = d
        left = max(0, t["qty_plan"] - t["qty_good"] - t["qty_scrap"])
        norm = (t["norm_min"] or 0) * 60
        if t["status"] in ("vykdoma", "pristabdyta"):
            dur[t["id"]] = max(norm * t["qty_plan"] - _work_seconds(con, t["id"]), norm * left * MIN_LEFT)
        else:
            dur[t["id"]] = norm * left
    names = {t["id"]: f"{t['centre_code']} · {t['name']}" for t in rows}

    ends: dict[int, object] = {}
    out: dict[int, dict] = {}
    changed = set()
    for _ in range(PASSES):
        changed = set()
        for cid, lst in by_centre.items():
            cur = now_dt
            for t in lst:
                es, wait = cur, None
                for d in deps[t["id"]]:
                    e = ends.get(d, now_dt)
                    if e and e > es:
                        es, wait = e, d
                start = cal.add_work("centre", cid, es, 0)
                end = cal.add_work("centre", cid, start, dur[t["id"]]) if start else None
                if ends.get(t["id"], "x") != end:
                    changed.add(t["id"])
                ends[t["id"]] = end
                # neišleista / nepatvirtinta operacija skaičiuojama taip, lyg būtų
                # paleista dabar – kad matytųsi, ką reiškia delsti; ekrane pažymima
                pending = ("maršrutas neišleistas" if not t["released_at"]
                           else "eilė nepatvirtinta" if not t["approved"] else None)
                out[t["id"]] = {"start": start, "end": end, "wait": names[wait] if wait else None,
                                "no_time": start is None, "norm": bool(t["norm_min"]), "pending": pending}
                if end:
                    cur = end
        if not changed:
            break
    # vis dar keičiasi – eilių tvarka prieštarauja maršrutui (A laukia B, B stovi už A)
    loop = changed

    due = _due_dates(con, rows)
    for t in rows:
        o = out[t["id"]]
        end_local = workcal.local_date(o["end"]) if o["end"] else None
        o["due"] = due.get(t["id"])
        o["late"] = bool(o["due"] and (end_local is None or end_local.isoformat() > o["due"]))
        o["loop"] = t["id"] in loop
        o["start"] = o["start"].isoformat(timespec="minutes") if o["start"] else None
        o["end"] = o["end"].isoformat(timespec="minutes") if o["end"] else None
    return out


def _due_dates(con, rows) -> dict[int, str]:
    """Iki kada operacija turi būti atlikta: jos etapo (mazgo arba projekto)
    planuojama pabaiga, jei etapo nėra – projekto terminas."""
    phases = {}
    for ph in db.rows(con.execute("SELECT project_id, assembly_id, kind, plan_end FROM phases WHERE plan_end IS NOT NULL")):
        phases.setdefault((ph["project_id"], ph["kind"]), []).append(ph)
    kinds = dict(con.execute("SELECT id, kind FROM work_centres").fetchall())
    out = {}
    for t in rows:
        kind = CENTRE_PHASE.get(kinds.get(t["centre_id"]), "gamyba")
        cand = phases.get((t["project_id"], kind), [])
        ph = next((p for p in cand if p["assembly_id"] == t["assembly_id"]), None) or \
            next((p for p in cand if p["assembly_id"] is None), None)
        out[t["id"]] = (ph["plan_end"] if ph else t["due_date"]) or None
    return out


def project_end(fc: dict, task_ids) -> str | None:
    """Vėliausia projekto (ar mazgo) operacijų prognozuojama pabaiga."""
    ends = [fc[i]["end"] for i in task_ids if i in fc and fc[i]["end"]]
    return max(ends) if ends else None

