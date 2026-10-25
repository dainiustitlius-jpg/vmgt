"""Technologinis srautas ir detalių atsekamumas.

Mazgo maršrutas – ne viena eilė, o medis: kiekviena detalė turi savo
atšaką (pvz. lazeris → lenkimas), atšakos susilieja į mazgo operacijas
(suvirinimas → dažymas), o baigtas mazgas keliauja į mazgą, kuris jo laukia
(`assemblies.requires`). Atšaką nusako operacijos `part_no`: tuščias –
mazgo operacija. Tad tas pats CSV stulpelis „detale“ ir yra srauto aprašas.

Technologas maršrutą **išleidžia į gamybą** (`release`) – tik tada užduotys
gali būti tvirtinamos ir pradėtos, o maršrutas užrakinamas: pakeisti jį
galima tik grąžinus (`unrelease`), ir abu veiksmai lieka žurnale.

Perdavimas – vienas veiksmas: operatorius spaudžia Stop su gerų kiekiu, ir
detalės iškart priskiriamos kitai operacijai (`transfers`), o terminalas
parodo, kur jas nunešti.
"""

from __future__ import annotations

from .. import db
from . import NotFound, RuleError

STORE = "Mazgas baigtas – į sandėlį / išsiuntimui"

_OPS_SQL = (
    "SELECT t.id, t.assembly_id, t.project_id, t.seq, t.name, t.part_no, t.qty_plan, t.qty_good, t.qty_scrap, "
    "t.norm_min, t.status, t.approved, t.drawing_no, t.drawing_rev, t.centre_id, "
    "c.code AS centre_code, c.name AS centre_name, c.needs_files, ar.code AS area_code, ar.name AS area_name "
    "FROM tasks t JOIN work_centres c ON c.id=t.centre_id LEFT JOIN areas ar ON ar.id=c.area_id ")


def _assembly(con, assembly_id) -> dict:
    a = db.row(con.execute(
        "SELECT a.*, p.code AS project_code, p.name AS project_name, u.name AS released_by_name "
        "FROM assemblies a JOIN projects p ON p.id=a.project_id LEFT JOIN users u ON u.id=a.released_by "
        "WHERE a.id=?", (assembly_id,)))
    if not a:
        raise NotFound("Mazgo nėra")
    return a


def structure(con, assembly_id) -> dict:
    """Detalių atšakos (pagal pirmos operacijos seką) ir mazgo operacijos."""
    ops = db.rows(con.execute(_OPS_SQL + "WHERE t.assembly_id=? ORDER BY t.seq, t.id", (assembly_id,)))
    branches: dict[str, list] = {}
    main = []
    for o in ops:
        (branches.setdefault(o["part_no"], []) if o["part_no"] else main).append(o)
    return {"branches": [{"part": k, "ops": v} for k, v in branches.items()], "main": main}


def is_released(con, assembly_id) -> bool:
    r = con.execute("SELECT released_at FROM assemblies WHERE id=?", (assembly_id,)).fetchone()
    return bool(r and r[0])


def _lane(st, t):
    if t["part_no"]:
        return next((b["ops"] for b in st["branches"] if b["part"] == t["part_no"]), [])
    return st["main"]


def upstream(con, t: dict, st: dict | None = None) -> list[dict]:
    """Operacijos, iš kurių detalės ateina į `t`. Pirmai mazgo operacijai –
    visų atšakų paskutinės operacijos (čia detalės susilieja)."""
    st = st or structure(con, t["assembly_id"])
    lane = _lane(st, t)
    i = next(i for i, o in enumerate(lane) if o["id"] == t["id"])
    if i > 0:
        return [lane[i - 1]]
    if not t["part_no"]:
        return [b["ops"][-1] for b in st["branches"]]
    return []


def is_entry(con, t: dict, st: dict | None = None) -> bool:
    """Ar čia į mazgą ateina mazgai, kurių jis laukia (`requires`): pirmoji
    mazgo operacija, o jei jų nėra – kiekvienos atšakos pirmoji. Detalės
    pjaunamos lygiagrečiai, nelaukdamos pomazgių – jų laukia tik surinkimas."""
    st = st or structure(con, t["assembly_id"])
    if st["main"]:
        return st["main"][0]["id"] == t["id"]
    return _lane(st, t)[0]["id"] == t["id"]


def _entries(st) -> list[dict]:
    if st["main"]:
        return [st["main"][0]]
    return [b["ops"][0] for b in st["branches"]]


def _consumers(con, assembly_id) -> list[dict]:
    """Mazgai, kurie laukia šio (`requires`)."""
    a = con.execute("SELECT project_id, code FROM assemblies WHERE id=?", (assembly_id,)).fetchone()
    out = []
    for r in db.rows(con.execute("SELECT id, code, name, requires FROM assemblies WHERE project_id=? ORDER BY sort, code",
                                 (a["project_id"],))):
        if a["code"] in [c for c in r["requires"].split(",") if c]:
            out.append(r)
    return out


def next_steps(con, t: dict, st: dict | None = None) -> list[dict]:
    """Kur detalės keliauja po operacijos `t`. Tuščias `task_id` – sandėlis."""
    st = st or structure(con, t["assembly_id"])
    lane = _lane(st, t)
    i = next(i for i, o in enumerate(lane) if o["id"] == t["id"])
    if i + 1 < len(lane):
        return [_dest(lane[i + 1])]
    if t["part_no"] and st["main"]:
        return [_dest(st["main"][0], joins=len(st["branches"]))]
    out = []
    for asm in _consumers(con, t["assembly_id"]):
        for e in _entries(structure(con, asm["id"])):
            out.append(_dest(e, assembly=f"{asm['code']} {asm['name']}"))
    return out or [{"task_id": None, "label": STORE}]


def _dest(o, joins=0, assembly=None) -> dict:
    return {"task_id": o["id"], "centre_code": o["centre_code"], "centre_name": o["centre_name"],
            "area_name": o["area_name"], "name": o["name"], "part_no": o["part_no"], "assembly": assembly,
            "joins": joins, "label": f"{o['centre_code']} {o['centre_name']}"}


def record_transfer(con, user_id, t: dict, qty: int) -> list[dict]:
    """Stop su gerais vienetais = perdavimas. Grąžina, kur juos nunešti."""
    dests = next_steps(con, t)
    if qty > 0:
        for d in dests:
            con.execute("INSERT INTO transfers (from_task_id, to_task_id, qty, at, user_id) VALUES (?,?,?,?,?)",
                        (t["id"], d["task_id"], qty, db.now(), user_id))
    return dests


def arrived(t: dict, ups: list[dict]) -> int | None:
    """Kiek vienetų atkeliavo ir dar neapdirbta šioje operacijoje. Tik kai
    ateina iš vienos tos pačios atšakos operacijos – kitaip vienetai skiriasi
    (4 plokštės ≠ 1 rėmas) ir sumuoti negalima."""
    if len(ups) != 1 or ups[0]["part_no"] != t["part_no"]:
        return None
    return max(0, ups[0]["qty_good"] - t["qty_good"] - t["qty_scrap"])


# ---------- išleidimas į gamybą ----------

def _files(con, ops) -> dict:
    from .ncfiles import list_for
    return list_for(con, [o["id"] for o in ops])


def check(con, assembly_id) -> dict:
    """Ar maršrutą galima išleisti. Klaidos draudžia, įspėjimai – ne."""
    st = structure(con, assembly_id)
    errors, warnings = [], []
    ops = [o for b in st["branches"] for o in b["ops"]] + st["main"]
    if not ops:
        errors.append("Maršrute nėra nė vienos operacijos")
    if st["main"] and st["branches"]:
        last_part = max(o["seq"] for b in st["branches"] for o in b["ops"])
        early = [o for o in st["main"] if o["seq"] < last_part]
        if early:
            errors.append(f"Mazgo operacija „{early[0]['name']}“ (seka {early[0]['seq']}) eina prieš detalių "
                          f"operacijas – detalių operacijų seka turi būti mažesnė")
    if len(st["branches"]) > 1 and not st["main"]:
        warnings.append("Kelios detalės, bet nėra mazgo operacijos (be detalės kodo) – atšakos niekur nesusilieja")
    files = _files(con, ops)
    for o in ops:
        # staklėms be programos pjauti nėra kuo – tai klaida, ne įspėjimas
        if o["needs_files"] and not files[o["id"]]:
            part = f" ({o['part_no']})" if o["part_no"] else ""
            errors.append(f"{o['centre_code']} · {o['name']}{part}: nepridėtas programos / DXF failas")
        if not o["norm_min"]:
            warnings.append(f"{o['centre_code']} · {o['name']}: nenurodyta norma")
        if not o["drawing_no"]:
            warnings.append(f"{o['centre_code']} · {o['name']}: nenurodytas brėžinys")
    a = _assembly(con, assembly_id)
    for code in [c for c in a["requires"].split(",") if c]:
        r = con.execute("SELECT released_at FROM assemblies WHERE project_id=? AND code=?",
                        (a["project_id"], code)).fetchone()
        if not r:
            errors.append(f"Laukiamo mazgo {code} projekte nėra")
        elif not r[0]:
            warnings.append(f"Laukiamo mazgo {code} maršrutas dar neišleistas")
    return {"errors": errors, "warnings": warnings}


def release(con, by, assembly_id) -> dict:
    a = _assembly(con, assembly_id)
    if a["released_at"]:
        raise RuleError("Maršrutas jau išleistas į gamybą")
    res = check(con, assembly_id)
    if res["errors"]:
        raise RuleError("Maršruto išleisti negalima: " + "; ".join(res["errors"]))
    con.execute("UPDATE assemblies SET released_at=?, released_by=? WHERE id=?", (db.now(), by, assembly_id))
    db.log_event(con, by, "assembly", assembly_id, "release", {"warnings": res["warnings"]})
    return res


def unrelease(con, by, assembly_id, reason: str) -> None:
    """Grąžinti maršrutą keisti. Pradėti darbai tęsiami, nepradėti
    užrakinami, kol technologas išleis iš naujo."""
    a = _assembly(con, assembly_id)
    if not a["released_at"]:
        raise RuleError("Maršrutas dar neišleistas")
    if not (reason or "").strip():
        raise RuleError("Nurodykite, kodėl maršrutas keičiamas")
    con.execute("UPDATE assemblies SET released_at=NULL, released_by=NULL WHERE id=?", (assembly_id,))
    db.log_event(con, by, "assembly", assembly_id, "unrelease", {"reason": reason})


def ensure_editable(con, assembly_id) -> None:
    if is_released(con, assembly_id):
        raise RuleError("Maršrutas išleistas į gamybą – pirma grąžinkite jį keisti („Keisti maršrutą“)")


# ---------- atsekamumas ----------

def _where(o, ups, first_in_lane) -> str | None:
    """Kas šiuo metu yra prie operacijos – žmogui suprantamai."""
    if o["status"] == "vykdoma":
        return "apdirbama"
    if o["status"] == "pristabdyta":
        return "pristabdyta"
    if o["status"] == "baigta":
        return None
    n = arrived(o, ups)
    if n:
        return f"laukia {n} vnt."
    if first_in_lane and not ups:
        left = o["qty_plan"] - o["qty_good"] - o["qty_scrap"]
        return f"liko {left} vnt." if o["qty_good"] or o["qty_scrap"] else "laukia pradžios"
    if ups and all(u["status"] == "baigta" or u["qty_good"] > 0 for u in ups) and n is None:
        return "detalės atkeliavo"
    return None


def trace(con, assembly_id) -> dict:
    """Visas mazgo srautas su būsenomis: kur kas dabar ir kas kam perduota."""
    from .tasks import block_reason

    a = _assembly(con, assembly_id)
    st = structure(con, assembly_id)
    files = _files(con, [o for b in st["branches"] for o in b["ops"]] + st["main"])

    def lane(ops, part):
        out = []
        for i, o in enumerate(ops):
            o["files"] = files[o["id"]]
            ups = upstream(con, o, st)
            o["here"] = _where(o, ups, i == 0)
            o["arrived"] = arrived(o, ups)
            o["lock"] = block_reason(con, {**o, "strict_order": 0}) if o["status"] == "laukia" else None
            out.append(o)
        last = ops[-1] if ops else None
        return {"part": part, "ops": out, "done": bool(ops) and all(o["status"] == "baigta" for o in ops),
                "next": next_steps(con, last, st) if last else []}

    lanes = [lane(b["ops"], b["part"]) for b in st["branches"]]
    main = lane(st["main"], "") if st["main"] else None
    moves = db.rows(con.execute(
        "SELECT x.qty, x.at, u.name AS user_name, f.name AS from_name, f.part_no AS from_part, "
        "fc.code AS from_centre, t.name AS to_name, tc.code AS to_centre, ta.code AS to_assembly "
        "FROM transfers x JOIN tasks f ON f.id=x.from_task_id JOIN work_centres fc ON fc.id=f.centre_id "
        "LEFT JOIN tasks t ON t.id=x.to_task_id LEFT JOIN work_centres tc ON tc.id=t.centre_id "
        "LEFT JOIN assemblies ta ON ta.id=t.assembly_id LEFT JOIN users u ON u.id=x.user_id "
        "WHERE f.assembly_id=? OR t.assembly_id=? ORDER BY x.at DESC, x.id DESC LIMIT 200",
        (assembly_id, assembly_id)))
    for m in moves:
        m["to_label"] = f"{m['to_centre']} · {m['to_name']}" if m["to_centre"] else STORE
    needs = [r for r in _consumers(con, assembly_id)]
    feeds = []
    for code in [c for c in a["requires"].split(",") if c]:
        r = db.row(con.execute("SELECT id, code, name FROM assemblies WHERE project_id=? AND code=?",
                               (a["project_id"], code)))
        if r:
            left = con.execute("SELECT COUNT(*) FROM tasks WHERE assembly_id=? AND status!='baigta'",
                               (r["id"],)).fetchone()[0]
            feeds.append({**r, "done": left == 0})
    return {"assembly": a, "released": bool(a["released_at"]), "branches": lanes, "main": main,
            "requires": feeds, "consumers": [{"id": r["id"], "code": r["code"], "name": r["name"]} for r in needs],
            "transfers": moves, "check": check(con, assembly_id)}


# ---------- technologo darbo aplinka ----------

def copy_route(con, nc_dir, user, from_assembly, to_assembly, with_files=True) -> dict:
    """Nukopijuoti maršrutą iš panašaus mazgo – vienetinėje gamyboje dažnai
    kartojasi tie patys sprendimai. Kiekiai perskaičiuojami pagal mazgų
    kiekį (2 plokštės vienam rėmui → 12 šešiems)."""
    from .ncfiles import copy_files
    from .tasks import create_task

    src, dst = _assembly(con, from_assembly), _assembly(con, to_assembly)
    ensure_editable(con, to_assembly)
    if from_assembly == to_assembly:
        raise RuleError("Pasirinkite kitą mazgą")
    ops = db.rows(con.execute("SELECT * FROM tasks WHERE assembly_id=? ORDER BY seq, id", (from_assembly,)))
    if not ops:
        raise RuleError(f"Mazgas {src['code']} neturi operacijų")
    n = nf = 0
    for o in ops:
        per = o["qty_plan"] / max(1, src["qty"])
        tid = create_task(con, user["id"], {
            "project_id": dst["project_id"], "assembly_id": to_assembly, "centre_id": o["centre_id"],
            "seq": o["seq"], "name": o["name"], "part_no": o["part_no"], "qty_plan": max(1, round(per * dst["qty"])),
            "norm_min": o["norm_min"], "drawing_no": o["drawing_no"], "drawing_rev": o["drawing_rev"]})
        n += 1
        if with_files:
            nf += copy_files(con, nc_dir, user, o["id"], tid)
    db.log_event(con, user["id"], "assembly", to_assembly, "copy_route",
                 {"from": f"{src['project_code']} {src['code']}", "ops": n, "files": nf})
    return {"ops": n, "files": nf}


def worklist(con, user_id=None) -> list[dict]:
    """Technologo darbų sąrašas: neišleisti maršrutai ir kas jiems trukdo.
    Vykdomų ir krepšelio projektų mazgai; `user_id` – tik tie, kurių
    technologijos etapas priskirtas jam (arba visam projektui)."""
    rows = db.rows(con.execute(
        "SELECT a.id, a.code, a.name, a.qty, a.released_at, p.id AS project_id, p.code AS project_code, "
        "p.name AS project_name, p.status AS project_status, p.priority, p.due_date "
        "FROM assemblies a JOIN projects p ON p.id=a.project_id "
        "WHERE p.status IN ('krepselis','vykdomas') ORDER BY p.priority, p.due_date IS NULL, p.due_date, p.code, a.sort"))
    out = []
    for a in rows:
        ph = db.row(con.execute(
            "SELECT ph.plan_end, ph.status, ph.owner_id, u.name AS owner_name FROM phases ph "
            "LEFT JOIN users u ON u.id=ph.owner_id WHERE ph.project_id=? AND ph.kind='technologija' "
            "AND (ph.assembly_id=? OR ph.assembly_id IS NULL) ORDER BY ph.assembly_id IS NULL LIMIT 1",
            (a["project_id"], a["id"])))
        if user_id and not (ph and ph["owner_id"] == user_id):
            continue
        st = structure(con, a["id"])
        ops = [o for b in st["branches"] for o in b["ops"]] + st["main"]
        files = _files(con, ops)
        a.update({
            "ops": len(ops), "parts": len(st["branches"]),
            "no_norm": sum(1 for o in ops if not o["norm_min"]),
            "no_file": sum(1 for o in ops if o["needs_files"] and not files[o["id"]]),
            "files": sum(len(v) for v in files.values()),
            "pending_ack": sum(1 for v in files.values() for f in v if f["needs_ack"]),
            "tech_due": ph["plan_end"] if ph else None, "tech_owner": ph["owner_name"] if ph else None,
            "tech_status": ph["status"] if ph else None,
        })
        a["state"] = "isleista" if a["released_at"] else "juodrastis" if ops else "nera"
        a["state_label"] = {"isleista": "Išleista į gamybą", "juodrastis": "Juodraštis",
                            "nera": "Nėra maršruto"}[a["state"]]
        a["errors"] = 0 if a["released_at"] or not ops else len(check(con, a["id"])["errors"])
        out.append(a)
    return out
