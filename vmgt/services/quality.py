"""Kokybė pagal EN 1090 / ISO 3834: patikros maršrute, medžiagų atsekamumas,
suvirintojų kvalifikacijos, kokybės dosjė.

Vartotojo sprendimai (2026-10-26): visos keturios dalys; taisyklės
**griežtos** – neužbaigus patikros detalės toliau neperduodamos,
nekvalifikuotas suvirintojas darbo nepradeda (išimtį patikrai gali leisti
meistras ar kokybės inžinierius, su priežastimi); patikrą atlieka **tas,
kurį nurodė technologas** – operatorius (savikontrolė terminale) arba
kokybės inžinierius (kokybės eilė).

Kaip veikia ceche:

- Stop su gerais vienetais: operatoriaus patikros turi būti įvestos, o
  EXC2+ projekto pjovimo operacijai – nurodytas medžiagos lydinys.
- Jei lieka kokybės inžinieriaus patikra – kiekis įrašomas, bet detalės
  **sulaikomos**: perdavimas kitai operacijai įrašomas tik užbaigus patikras
  (`release_transfers`), o kita operacija iki tol užrakinta.
- NOK rezultatas iškart sukuria neatitiktį; patikra lieka atvira, kol
  pakartotinis matavimas OK arba leista išimtis.
- Suvirinimo operacijai su WPS – pradėti gali tik suvirintojas su galiojančia
  kvalifikacija tam procesui ir medžiagų grupei.
"""

from __future__ import annotations

import io
import json
import re
import secrets
import zipfile
from pathlib import Path

from .. import db
from . import NotFound, RuleError, routing

EXC_CLASSES = ["", "EXC1", "EXC2", "EXC3", "EXC4"]
TRACE_FROM = "EXC2"            # nuo šios klasės – medžiagų atsekamumas ir WPS privalomi
PERFORMERS = [("operator", "Operatorius (savikontrolė)"), ("qc", "Kokybės inžinierius")]
DISPOSITIONS = [("naudoti", "Naudoti kaip yra"), ("perdaryti", "Perdaryti"), ("remontuoti", "Remontuoti"),
                ("brokas", "Brokas"), ("grazinti", "Grąžinti tiekėjui")]
DISPOSITION_LABEL = dict(DISPOSITIONS)
CERT_TYPES = ["2.2", "3.1", "3.2"]
# patikros NOK → neatitikties kategorija pagal centro rūšį
NCR_BY_KIND = {"suvirinimas": "suvirinimas", "dazymas": "pavirsius", "pavirsius": "pavirsius",
               "pjovimas": "pjovimas", "lenkimas": "lenkimas", "surinkimas": "surinkimas"}


def traced(exc_class: str) -> bool:
    return bool(exc_class) and exc_class >= TRACE_FROM


def _perms(user):
    from .auth import perms_of
    return perms_of(user)


def _task(con, task_id) -> dict:
    t = db.row(con.execute(
        "SELECT t.*, c.code AS centre_code, c.kind AS centre_kind, ar.code AS area_code, p.code AS project_code, "
        "p.exc_class, a.code AS assembly_code FROM tasks t JOIN work_centres c ON c.id=t.centre_id "
        "LEFT JOIN areas ar ON ar.id=c.area_id JOIN projects p ON p.id=t.project_id "
        "JOIN assemblies a ON a.id=t.assembly_id WHERE t.id=?", (task_id,)))
    if not t:
        raise NotFound("Užduoties nėra")
    return t


# ---------- patikrų šablonai ----------

def list_templates(con, active_only=True) -> list[dict]:
    return db.rows(con.execute("SELECT * FROM check_templates" + (" WHERE active=1" if active_only else "")
                               + " ORDER BY code"))


def _check_fields(data: dict) -> dict:
    v = {k: data[k] for k in ("name", "kind", "unit", "nominal", "tol_minus", "tol_plus", "performer", "instruction")
         if k in data}
    if "kind" in v and v["kind"] not in ("check", "measure"):
        raise RuleError("Patikros tipas – „check“ (OK/NOK) arba „measure“ (matavimas)")
    if "performer" in v and v["performer"] not in dict(PERFORMERS):
        raise RuleError("Nurodykite, kas atlieka patikrą")
    for k in ("nominal", "tol_minus", "tol_plus"):
        if k in v:
            v[k] = None if v[k] in (None, "") else float(str(v[k]).replace(",", "."))
    if v.get("kind") == "measure" and v.get("nominal") is None:
        raise RuleError("Matavimui reikia vardinės reikšmės ir tolerancijų")
    return v


def save_template(con, by, data: dict, template_id=None) -> int:
    v = _check_fields(data)
    if "code" in data:
        v["code"] = data["code"].strip()
    if "active" in data:
        v["active"] = int(bool(data["active"]))
    if template_id is None:
        if not v.get("code") or not (v.get("name") or "").strip():
            raise RuleError("Reikia šablono kodo ir pavadinimo")
        cur = con.execute(f"INSERT INTO check_templates ({', '.join(v)}) VALUES ({', '.join('?' * len(v))})",
                          tuple(v.values()))
        db.log_event(con, by, "check_template", cur.lastrowid, "create", v)
        return cur.lastrowid
    con.execute(f"UPDATE check_templates SET {', '.join(k + '=?' for k in v)} WHERE id=?", (*v.values(), template_id))
    return template_id


# ---------- patikros prie operacijų ----------

def add_check(con, by, task_id, data: dict) -> int:
    t = _task(con, task_id)
    if t["status"] == "baigta":
        raise RuleError("Operacija jau atlikta")
    if data.get("template_id"):
        tpl = db.row(con.execute("SELECT * FROM check_templates WHERE id=?", (data["template_id"],)))
        if not tpl:
            raise NotFound("Šablono nėra")
        v = {k: tpl[k] for k in ("name", "kind", "unit", "nominal", "tol_minus", "tol_plus", "performer", "instruction")}
        v.update(_check_fields({k: data[k] for k in data if k != "template_id"}))
        v["template_id"] = tpl["id"]
    else:
        v = {"kind": "check", "performer": "operator", **_check_fields(data)}
        if not (v.get("name") or "").strip():
            raise RuleError("Reikia patikros pavadinimo")
    v["sort"] = con.execute("SELECT COALESCE(MAX(sort),0)+1 FROM task_checks WHERE task_id=?", (task_id,)).fetchone()[0]
    v["task_id"] = task_id
    cur = con.execute(f"INSERT INTO task_checks ({', '.join(v)}) VALUES ({', '.join('?' * len(v))})", tuple(v.values()))
    db.log_event(con, by, "task", task_id, "check_add", {"name": v["name"], "performer": v["performer"]})
    return cur.lastrowid


def remove_check(con, by, check_id) -> None:
    c = _check(con, check_id)
    if c["status"] != "laukia":
        raise RuleError("Atliktos patikros pašalinti negalima – ji yra kokybės įrašas")
    # išleistame maršrute patikrų mažinti negalima – kitaip kontrolė „dingtų“ be pėdsako
    routing.ensure_editable(con, _task(con, c["task_id"])["assembly_id"])
    con.execute("DELETE FROM task_checks WHERE id=?", (check_id,))
    db.log_event(con, by, "task", c["task_id"], "check_remove", {"name": c["name"]})


def _check(con, check_id) -> dict:
    c = db.row(con.execute("SELECT * FROM task_checks WHERE id=?", (check_id,)))
    if not c:
        raise NotFound("Patikros nėra")
    return c


def checks_for(con, task_ids) -> dict[int, list[dict]]:
    ids = list(task_ids)
    out = {i: [] for i in ids}
    if not ids:
        return out
    for c in db.rows(con.execute(
            "SELECT c.*, u.name AS done_by_name FROM task_checks c LEFT JOIN users u ON u.id=c.done_by "
            f"WHERE c.task_id IN ({','.join('?' * len(ids))}) ORDER BY c.sort, c.id", ids)):
        c["tolerance"] = _tol_text(c)
        out[c["task_id"]].append(c)
    return out


def _tol_text(c) -> str:
    if c["kind"] != "measure" or c["nominal"] is None:
        return ""
    lo, hi = c["tol_minus"] or 0, c["tol_plus"] or 0
    tol = f"±{_n(hi)}" if lo == hi else f"−{_n(lo)} / +{_n(hi)}"
    return f"{_n(c['nominal'])} {tol} {c['unit']}".strip()


def _n(x):
    return f"{x:g}".replace(".", ",")


def pending(con, task_id, performer=None) -> list[dict]:
    """Neužbaigtos patikros (laukia arba NOK be išimties)."""
    q = "SELECT * FROM task_checks WHERE task_id=? AND status IN ('laukia','nok')"
    args = [task_id]
    if performer:
        q += " AND performer=?"
        args.append(performer)
    return db.rows(con.execute(q + " ORDER BY sort, id", args))


def record(con, user, check_id, ok=None, value=None, note="") -> dict:
    """Patikros rezultatas. Matavimui OK apskaičiuojamas pagal toleranciją."""
    c = _check(con, check_id)
    t = _task(con, c["task_id"])
    perms = _perms(user)
    if c["performer"] == "qc":
        if "quality" not in perms:
            raise RuleError("Šią patikrą atlieka kokybės inžinierius")
    else:
        from .auth import can_centre
        if not ({"quality", "execute"} & perms) or ("quality" not in perms and not can_centre(user, t["centre_code"], t["area_code"])):
            raise RuleError("Šią patikrą atlieka centro operatorius")
    if c["status"] in ("ok", "isimtis"):
        raise RuleError("Patikra jau užbaigta")
    if c["kind"] == "measure":
        if value in (None, ""):
            raise RuleError("Įveskite išmatuotą reikšmę")
        value = float(str(value).replace(",", "."))
        ok = c["nominal"] - (c["tol_minus"] or 0) - 1e-9 <= value <= c["nominal"] + (c["tol_plus"] or 0) + 1e-9
    elif ok is None:
        raise RuleError("Pažymėkite OK arba NOK")
    ok = bool(ok)
    if not ok and not (note or "").strip() and c["kind"] == "check":
        raise RuleError("NOK – aprašykite, kas negerai")
    now = db.now()
    con.execute("INSERT INTO check_results (check_id, ok, value, note, user_id, at) VALUES (?,?,?,?,?,?)",
                (check_id, int(ok), value, note or "", user["id"], now))
    ncr_id = c["ncr_id"]
    if not ok:
        from . import ncr
        what = f"{_n(value)} {c['unit']} (reikia {_tol_text(c)})" if c["kind"] == "measure" else note
        ncr_id = ncr.report(con, user, {
            "task_id": t["id"], "category": "matmenys" if c["kind"] == "measure" else NCR_BY_KIND.get(t["centre_kind"], "kita"),
            "description": f"Patikra „{c['name']}“ – NOK: {what}" + (f". {note}" if note and c["kind"] == "measure" else "")})
        con.execute("UPDATE ncr SET check_id=? WHERE id=?", (check_id, ncr_id))
    con.execute("UPDATE task_checks SET status=?, value=?, done_by=?, done_at=?, ncr_id=? WHERE id=?",
                ("ok" if ok else "nok", value, user["id"], now, ncr_id, check_id))
    db.log_event(con, user["id"], "task", t["id"], "check", {"check": c["name"], "ok": ok, "value": value})
    moved = release_transfers(con, user["id"], t["id"]) if ok else 0
    return {"ok": ok, "ncr_id": ncr_id if not ok else None, "released": moved}


def waive(con, user, check_id, reason: str) -> dict:
    """Išimtis: patikra laikoma užbaigta be OK rezultato (pvz. klientas sutiko
    su nukrypimu). Leidžia meistras ar kokybės inžinierius, su priežastimi."""
    if not {"quality", "ack_rev"} & _perms(user):
        raise RuleError("Išimtį leidžia meistras arba kokybės inžinierius")
    if not (reason or "").strip():
        raise RuleError("Nurodykite išimties priežastį")
    c = _check(con, check_id)
    if "quality" not in _perms(user):
        from .auth import require_at
        t = _task(con, c["task_id"])
        require_at(user, "ack_rev", t["centre_code"], t["area_code"])     # meistras – savo baruose
    if c["status"] in ("ok", "isimtis"):
        raise RuleError("Patikra jau užbaigta")
    now = db.now()
    con.execute("INSERT INTO check_results (check_id, ok, note, kind, user_id, at) VALUES (?,?,?,?,?,?)",
                (check_id, 1, reason.strip(), "waiver", user["id"], now))
    con.execute("UPDATE task_checks SET status='isimtis', waiver_reason=?, done_by=?, done_at=? WHERE id=?",
                (reason.strip(), user["id"], now, check_id))
    db.log_event(con, user["id"], "task", c["task_id"], "check_waiver", {"check": c["name"], "reason": reason})
    return {"released": release_transfers(con, user["id"], c["task_id"])}


def release_transfers(con, user_id, task_id) -> int:
    """Užbaigus visas patikras – perduoti sulaikytas detales (tik skirtumą tarp
    gerų ir jau perduotų: pakartotinis kvietimas nieko nedubliuoja)."""
    if pending(con, task_id):
        return 0
    t = db.row(con.execute("SELECT * FROM tasks WHERE id=?", (task_id,)))
    done = con.execute("SELECT COALESCE(MAX(s), 0) FROM (SELECT SUM(qty) AS s FROM transfers WHERE from_task_id=? "
                       "GROUP BY to_task_id)", (task_id,)).fetchone()[0]
    diff = t["qty_good"] - int(done or 0)
    if diff > 0:
        routing.record_transfer(con, user_id, t, diff)
    return max(0, diff)


def held(con, task_id) -> list[dict]:
    """Kodėl detalės sulaikytos (yra gerų, bet patikros neužbaigtos)."""
    t = db.row(con.execute("SELECT qty_good FROM tasks WHERE id=?", (task_id,)))
    return pending(con, task_id) if t and t["qty_good"] > 0 else []


# ---------- medžiagos ----------

def requires_material(t: dict) -> bool:
    return traced(t.get("exc_class") or "") and t.get("centre_kind") == "pjovimas"


def save_lot(con, files_dir: Path, user, data: dict, cert: bytes | None = None, filename="", lot_id=None) -> int:
    v = {k: (data[k] or "").strip() if isinstance(data.get(k), str) else data[k]
         for k in ("heat_no", "material", "product", "supplier", "cert_no", "cert_type", "unit", "note") if k in data}
    if "qty" in data:
        v["qty"] = float(data["qty"] or 0)
    if v.get("cert_type") and v["cert_type"] not in CERT_TYPES:
        raise RuleError("Sertifikato tipas pagal EN 10204: 2.2, 3.1 arba 3.2")
    if cert:
        if not cert.startswith(b"%PDF"):
            raise RuleError("Sertifikatas – PDF failas")
        v["cert_file"] = _store(files_dir / "sertifikatai", f"{data.get('heat_no') or 'lydinys'}", cert)
    if lot_id is None:
        if not v.get("heat_no") or not v.get("material"):
            raise RuleError("Reikia lydinio numerio ir medžiagos (pvz. S355J2+N)")
        if con.execute("SELECT 1 FROM material_lots WHERE heat_no=? AND material=? AND product=?",
                       (v["heat_no"], v["material"], v.get("product", ""))).fetchone():
            raise RuleError(f"Lydinys {v['heat_no']} ({v['material']}) jau užregistruotas")
        v.update(received_at=db.now(), received_by=user["id"] if user else None)
        cur = con.execute(f"INSERT INTO material_lots ({', '.join(v)}) VALUES ({', '.join('?' * len(v))})",
                          tuple(v.values()))
        db.log_event(con, user["id"] if user else None, "material_lot", cur.lastrowid, "create",
                     {k: v[k] for k in ("heat_no", "material")})
        return cur.lastrowid
    if v:
        con.execute(f"UPDATE material_lots SET {', '.join(k + '=?' for k in v)} WHERE id=?", (*v.values(), lot_id))
    return lot_id


def set_lot_status(con, user, lot_id, status, note="") -> None:
    if status not in ("tinkama", "blokuota"):
        raise RuleError("Būsena – tinkama arba blokuota")
    if status == "blokuota" and not (note or "").strip():
        raise RuleError("Nurodykite, kodėl medžiaga blokuojama")
    con.execute("UPDATE material_lots SET status=?, note=? WHERE id=?", (status, note or "", lot_id))
    db.log_event(con, user["id"], "material_lot", lot_id, "status", {"status": status, "note": note})


def list_lots(con, q="", only_ok=False) -> list[dict]:
    sql = ("SELECT l.*, u.name AS received_by_name, (SELECT COUNT(*) FROM task_materials m WHERE m.lot_id=l.id) AS used "
           "FROM material_lots l LEFT JOIN users u ON u.id=l.received_by WHERE 1=1")
    args = []
    if q:
        sql += " AND (l.heat_no LIKE ? OR l.material LIKE ? OR l.product LIKE ? OR l.cert_no LIKE ?)"
        args += [f"%{q}%"] * 4
    if only_ok:
        sql += " AND l.status='tinkama'"
    return db.rows(con.execute(sql + " ORDER BY l.received_at DESC, l.id DESC LIMIT 300", args))


def use_lot(con, user, task_id, lot_id, qty=1) -> int:
    t = _task(con, task_id)
    lot = db.row(con.execute("SELECT * FROM material_lots WHERE id=?", (lot_id,)))
    if not lot:
        raise NotFound("Lydinio nėra")
    if lot["status"] != "tinkama":
        raise RuleError(f"Lydinys {lot['heat_no']} blokuotas: {lot['note']}")
    from .auth import can_centre
    if "quality" not in _perms(user) and not can_centre(user, t["centre_code"], t["area_code"]):
        raise RuleError("Šis darbo centras jums nepriskirtas")
    cur = con.execute("INSERT INTO task_materials (task_id, lot_id, qty, user_id, at) VALUES (?,?,?,?,?)",
                      (task_id, lot_id, float(qty or 1), user["id"], db.now()))
    db.log_event(con, user["id"], "task", task_id, "material", {"heat_no": lot["heat_no"], "qty": qty})
    return cur.lastrowid


def materials_for(con, task_ids) -> dict[int, list[dict]]:
    ids = list(task_ids)
    out = {i: [] for i in ids}
    if ids:
        for m in db.rows(con.execute(
                "SELECT m.*, l.heat_no, l.material, l.product, l.cert_no, l.cert_type, l.cert_file IS NOT NULL AS has_cert "
                f"FROM task_materials m JOIN material_lots l ON l.id=m.lot_id WHERE m.task_id IN ({','.join('?' * len(ids))}) "
                "ORDER BY m.at", ids)):
            out[m["task_id"]].append(m)
    return out


# ---------- suvirinimas: WPS ir kvalifikacijos ----------

def list_wps(con, active_only=True) -> list[dict]:
    return db.rows(con.execute("SELECT * FROM wps" + (" WHERE active=1" if active_only else "") + " ORDER BY code"))


def save_wps(con, files_dir, by, data: dict, file: bytes | None = None, wps_id=None) -> int:
    v = {k: (data[k] or "").strip() for k in ("code", "process", "material_group", "description") if k in data}
    if "active" in data:
        v["active"] = int(bool(data["active"]))
    if file:
        v["file"] = _store(files_dir / "wps", v.get("code") or "wps", file)
    if wps_id is None:
        if not v.get("code") or not v.get("process") or not v.get("material_group"):
            raise RuleError("Reikia WPS kodo, proceso (pvz. 135) ir medžiagų grupės (pvz. 1.1)")
        cur = con.execute(f"INSERT INTO wps ({', '.join(v)}) VALUES ({', '.join('?' * len(v))})", tuple(v.values()))
        db.log_event(con, by, "wps", cur.lastrowid, "create", v)
        return cur.lastrowid
    con.execute(f"UPDATE wps SET {', '.join(k + '=?' for k in v)} WHERE id=?", (*v.values(), wps_id))
    return wps_id


def list_qualifications(con, user_id=None) -> list[dict]:
    today = db.now()[:10]
    q = ("SELECT q.*, u.name AS user_name, u.login FROM qualifications q JOIN users u ON u.id=q.user_id WHERE q.active=1"
         + (" AND q.user_id=?" if user_id else "") + " ORDER BY u.name, q.process")
    out = db.rows(con.execute(q, (user_id,) if user_id else ()))
    for x in out:
        x["valid"] = x["valid_until"] >= today
        x["expires_soon"] = x["valid"] and x["valid_until"] <= _plus(today, 30)
    return out


def _plus(day, n):
    from datetime import date, timedelta
    return (date.fromisoformat(day) + timedelta(days=n)).isoformat()


def save_qualification(con, files_dir, by, data: dict, file: bytes | None = None, qid=None) -> int:
    v = {k: data[k] for k in ("user_id", "standard", "process", "material_group", "cert_no", "valid_until", "note")
         if k in data}
    if "active" in data:
        v["active"] = int(bool(data["active"]))
    if file:
        v["file"] = _store(files_dir / "kvalifikacijos", str(v.get("cert_no") or "kvalifikacija"), file)
    if qid is None:
        for k in ("user_id", "process", "material_group", "valid_until"):
            if not v.get(k):
                raise RuleError("Reikia suvirintojo, proceso, medžiagų grupės ir galiojimo datos")
        cur = con.execute(f"INSERT INTO qualifications ({', '.join(v)}) VALUES ({', '.join('?' * len(v))})",
                          tuple(v.values()))
        db.log_event(con, by, "qualification", cur.lastrowid, "create", {k: v[k] for k in v if k != "file"})
        return cur.lastrowid
    con.execute(f"UPDATE qualifications SET {', '.join(k + '=?' for k in v)} WHERE id=?", (*v.values(), qid))
    return qid


def welder_lock(con, user, t: dict) -> str | None:
    """Kodėl šis žmogus negali pradėti suvirinimo pagal WPS (None – gali)."""
    if not t.get("wps_id"):
        return None
    w = db.row(con.execute("SELECT * FROM wps WHERE id=?", (t["wps_id"],)))
    if not w:
        return None
    today = db.now()[:10]
    ok = con.execute("SELECT 1 FROM qualifications WHERE user_id=? AND active=1 AND process=? AND material_group=? "
                     "AND valid_until>=?", (user["id"], w["process"], w["material_group"], today)).fetchone()
    if ok:
        return None
    old = con.execute("SELECT MAX(valid_until) FROM qualifications WHERE user_id=? AND active=1 AND process=? "
                      "AND material_group=?", (user["id"], w["process"], w["material_group"])).fetchone()[0]
    why = f"kvalifikacija baigė galioti {old}" if old else "nėra kvalifikacijos"
    return (f"Suvirinimas pagal {w['code']} (procesas {w['process']}, grupė {w['material_group']}): "
            f"{user['name']} – {why}")


# ---------- patikra prieš pradedant / baigiant (kviečia tasks) ----------

def check_stop(con, user, t: dict, good: int) -> None:
    if good <= 0:
        return
    own = pending(con, t["id"], "operator")
    if own:
        raise RuleError("Pirma įveskite patikrų rezultatus: " + ", ".join(c["name"] for c in own))
    if requires_material(t) and not con.execute("SELECT 1 FROM task_materials WHERE task_id=?", (t["id"],)).fetchone():
        raise RuleError(f"{t['exc_class']} projektas: nurodykite, iš kurio lydinio (sertifikato) pjauta")


def route_check(con, assembly_id, ops) -> tuple[list, list]:
    """Išleidimo patikra (kviečia `routing.check`): EXC2+ suvirinimui – WPS."""
    exc = con.execute("SELECT p.exc_class FROM assemblies a JOIN projects p ON p.id=a.project_id WHERE a.id=?",
                      (assembly_id,)).fetchone()
    errors, warnings = [], []
    if not exc or not traced(exc[0]):
        return errors, warnings
    kinds = {r[0]: r[1] for r in con.execute("SELECT id, kind FROM work_centres")}
    checks = checks_for(con, [o["id"] for o in ops])
    for o in ops:
        if kinds.get(o["centre_id"]) != "suvirinimas":
            continue
        wps = con.execute("SELECT wps_id FROM tasks WHERE id=?", (o["id"],)).fetchone()[0]
        if not wps:
            errors.append(f"{o['centre_code']} · {o['name']}: {exc[0]} – nenurodytas WPS")
        if not any(c["performer"] == "qc" for c in checks[o["id"]]):
            warnings.append(f"{o['centre_code']} · {o['name']}: nėra kokybės inžinieriaus suvirinimo patikros")
    return errors, warnings


# ---------- kokybės eilė ----------

def qc_queue(con) -> list[dict]:
    """Kokybės inžinieriaus laukiančios patikros: pirmiausia tos, dėl kurių
    sulaikytos detalės (operacija jau padarė gerų vienetų)."""
    rows = db.rows(con.execute(
        "SELECT c.*, t.name AS task_name, t.qty_good, t.qty_plan, t.status AS task_status, c2.code AS centre_code, "
        "p.code AS project_code, a.code AS assembly_code, t.part_no FROM task_checks c JOIN tasks t ON t.id=c.task_id "
        "JOIN work_centres c2 ON c2.id=t.centre_id JOIN projects p ON p.id=t.project_id "
        "JOIN assemblies a ON a.id=t.assembly_id "
        "WHERE c.performer='qc' AND c.status IN ('laukia','nok') AND p.status IN ('vykdomas','krepselis') "
        "ORDER BY t.qty_good=0, c.status='laukia', p.priority, t.id"))
    for r in rows:
        r["tolerance"] = _tol_text(r)
        r["holding"] = r["qty_good"] > 0
    return rows


# ---------- NCR 8D ----------

def update_ncr(con, user, ncr_id, data: dict) -> None:
    n = db.row(con.execute("SELECT * FROM ncr WHERE id=?", (ncr_id,)))
    if not n:
        raise NotFound("Neatitikties nėra")
    if n["status"] == "uzdaryta":
        raise RuleError("Uždarytos neatitikties keisti negalima")
    v = {k: (data[k] or "").strip() for k in ("containment", "root_cause", "corrective", "preventive", "disposition")
         if k in data}
    if v.get("disposition") and v["disposition"] not in DISPOSITION_LABEL:
        raise RuleError("Nežinomas sprendimas dėl gaminio")
    if v:
        con.execute(f"UPDATE ncr SET {', '.join(k + '=?' for k in v)} WHERE id=?", (*v.values(), ncr_id))
        db.log_event(con, user["id"], "ncr", ncr_id, "8d", v)


def add_ncr_file(con, files_dir, user, ncr_id, filename, content: bytes) -> int:
    if not db.row(con.execute("SELECT 1 FROM ncr WHERE id=?", (ncr_id,))):
        raise NotFound("Neatitikties nėra")
    ext = (filename.rsplit(".", 1)[-1] if "." in filename else "").lower()
    if ext not in ("jpg", "jpeg", "png", "webp", "heic", "pdf"):
        raise RuleError("Nuotrauka (jpg, png, webp, heic) arba PDF")
    if len(content) > 20 * 1024 * 1024:
        raise RuleError("Failas per didelis (daugiau nei 20 MB)")
    stored = _store(files_dir / "ncr", f"ncr{ncr_id}", content, ext)
    cur = con.execute("INSERT INTO ncr_files (ncr_id, name, stored, user_id, at) VALUES (?,?,?,?,?)",
                      (ncr_id, Path(filename).name, stored, user["id"], db.now()))
    return cur.lastrowid


def ncr_files(con, ncr_id) -> list[dict]:
    return db.rows(con.execute("SELECT f.*, u.name AS user_name FROM ncr_files f LEFT JOIN users u ON u.id=f.user_id "
                               "WHERE ncr_id=? ORDER BY at", (ncr_id,)))


def _store(folder: Path, stem: str, content: bytes, ext="pdf") -> str:
    folder.mkdir(parents=True, exist_ok=True)
    name = f"{re.sub(r'[^A-Za-z0-9._-]+', '_', stem)[:60]}_{secrets.token_hex(4)}.{ext}"
    (folder / name).write_bytes(content)
    return f"{folder.name}/{name}"


def stored_path(files_dir: Path, rel: str) -> Path:
    p = (files_dir / rel).resolve()
    if files_dir.resolve() not in p.parents:
        raise NotFound("Failo nėra")
    return p


# ---------- kokybės dosjė ----------

def dossier(con, project_id) -> dict:
    """Projekto kokybės dokumentų paketas: medžiagų atsekamumas, suvirinimo
    žurnalas, patikrų protokolas, neatitiktys (8D)."""
    from . import ncr as ncr_mod
    p = db.row(con.execute("SELECT p.*, u.name AS manager_name FROM projects p LEFT JOIN users u ON u.id=p.manager_id "
                           "WHERE p.id=?", (project_id,)))
    if not p:
        raise NotFound("Projekto nėra")
    ops = db.rows(con.execute(
        "SELECT t.*, c.code AS centre_code, c.kind AS centre_kind, a.code AS assembly_code, a.name AS assembly_name, "
        "w.code AS wps_code, w.process AS wps_process, w.material_group AS wps_group FROM tasks t "
        "JOIN work_centres c ON c.id=t.centre_id JOIN assemblies a ON a.id=t.assembly_id "
        "LEFT JOIN wps w ON w.id=t.wps_id WHERE t.project_id=? ORDER BY a.sort, a.code, t.seq, t.id", (project_id,)))
    ids = [o["id"] for o in ops]
    mats, checks = materials_for(con, ids), checks_for(con, ids)
    material = [{"assembly": f"{o['assembly_code']} {o['assembly_name']}", "part": o["part_no"], "operation": o["name"],
                 "centre": o["centre_code"], **{k: m[k] for k in ("heat_no", "material", "product", "cert_no", "cert_type",
                                                                    "lot_id", "has_cert", "at")}}
                for o in ops for m in mats[o["id"]]]
    welding = []
    for o in ops:
        if o["centre_kind"] != "suvirinimas":
            continue
        who = db.rows(con.execute(
            "SELECT DISTINCT u.id, u.name, MIN(i.start) AS start, MAX(i.end) AS end FROM intervals i "
            "JOIN users u ON u.id=i.user_id WHERE i.task_id=? GROUP BY u.id", (o["id"],)))
        for w in who:
            q = db.row(con.execute(
                "SELECT cert_no, valid_until, process, material_group FROM qualifications WHERE user_id=? AND active=1 "
                "AND (? IS NULL OR (process=? AND material_group=?)) ORDER BY valid_until DESC LIMIT 1",
                (w["id"], o["wps_code"], o["wps_process"], o["wps_group"])))
            welding.append({"assembly": f"{o['assembly_code']} {o['assembly_name']}", "operation": o["name"],
                            "centre": o["centre_code"], "wps": o["wps_code"], "welder": w["name"],
                            "start": w["start"], "end": w["end"], "qualification": q})
    inspections = [{"assembly": o["assembly_code"], "part": o["part_no"], "operation": o["name"],
                    "centre": o["centre_code"], **c} for o in ops for c in checks[o["id"]]]
    ncrs = ncr_mod.list_ncr(con, project_id=project_id)
    for n in ncrs:
        n["disposition_label"] = DISPOSITION_LABEL.get(n.get("disposition") or "", "")
        n["files"] = ncr_files(con, n["id"])
    open_checks = sum(1 for c in inspections if c["status"] in ("laukia", "nok"))
    gaps = []
    if traced(p["exc_class"]):
        for o in ops:
            if o["centre_kind"] == "pjovimas" and o["qty_good"] and not mats[o["id"]]:
                gaps.append(f"{o['assembly_code']} {o['part_no']} {o['centre_code']} · {o['name']}: nenurodytas lydinys")
            if o["centre_kind"] == "suvirinimas" and not o["wps_id"]:
                gaps.append(f"{o['assembly_code']} {o['centre_code']} · {o['name']}: nenurodytas WPS")
    gaps += [f"{c['assembly']} {c['centre']} · {c['name']}: patikra neužbaigta" for c in inspections
             if c["status"] in ("laukia", "nok")]
    gaps += [f"NCR-{n['id']}: neuždaryta" for n in ncrs if n["status"] != "uzdaryta"]
    return {"project": p, "generated": db.now(), "materials": material, "welding": welding,
            "inspections": inspections, "ncr": ncrs, "open_checks": open_checks, "gaps": gaps,
            "complete": not gaps}


def dossier_zip(con, files_dir: Path, project_id) -> bytes:
    """Dosjė priedai viename ZIP: sertifikatai, kvalifikacijos, WPS, NCR nuotraukos + turinys.csv."""
    d = dossier(con, project_id)
    buf = io.BytesIO()
    rows = ["skyrius;failas;aprasas"]
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        def add(folder, rel, name, desc):
            if not rel:
                return
            p = stored_path(files_dir, rel)
            if p.exists():
                arc = f"{folder}/{name}"
                z.write(p, arc)
                rows.append(f"{folder};{arc};{desc}")
        for lot_id in sorted({m["lot_id"] for m in d["materials"]}):
            lot = db.row(con.execute("SELECT * FROM material_lots WHERE id=?", (lot_id,)))
            add("sertifikatai", lot["cert_file"], f"{_safe(lot['heat_no'])}_{_safe(lot['cert_no'] or 'cert')}.pdf",
                f"{lot['material']} {lot['product']} lydinys {lot['heat_no']} EN 10204 {lot['cert_type']}")
        welders = {w["welder"] for w in d["welding"]}
        for q in list_qualifications(con):
            if q["user_name"] in welders:
                add("kvalifikacijos", q["file"], f"{_safe(q['user_name'])}_{_safe(q['cert_no'])}.pdf",
                    f"{q['standard']} {q['process']} {q['material_group']} iki {q['valid_until']}")
        for code in sorted({w["wps"] for w in d["welding"] if w["wps"]}):
            w = db.row(con.execute("SELECT * FROM wps WHERE code=?", (code,)))
            add("WPS", w["file"], f"{_safe(code)}.pdf", f"{w['process']} {w['material_group']} {w['description']}")
        for n in d["ncr"]:
            for f in n["files"]:
                add("neatitiktys", f["stored"], f"NCR-{n['id']}_{_safe(f['name'])}", n["description"][:80])
        z.writestr("turinys.csv", "﻿" + "\n".join(rows) + "\n")
        z.writestr("dosje.json", json.dumps(d, ensure_ascii=False, indent=1, default=str))
    return buf.getvalue()


def _safe(s):
    return re.sub(r"[^A-Za-z0-9._-]+", "_", str(s or ""))[:50]
