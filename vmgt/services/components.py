"""Standartinių komponentų pirkimai ir jų gavimas.

Viena eilutė – vienas perkamas komponentas projektui ar jo mazgui (variklis,
PLC, guoliai). Būsena **neįrašoma ranka, o išvedama iš faktų**: ar yra
užsakymo nr., ar tiekėjas patvirtino datą, kiek gauta. Taip ji visada
atitinka duomenis – ir kai juos įveda žmogus, ir kai ateis iš D365.

Gavimai saugomi kiekvienas atskirai (`component_receipts`): iš jų matoma,
kas ir kada atkeliavo, o pakartotinis importas, padidinęs gautą kiekį,
užregistruoja tik skirtumą.

Komponentų būsena valdo projekto etapą „Komponentų užsakymas“: pirmas
užsakymas jį pažymi „vykdoma“, viskas gauta – „baigta“ (`_sync_phase`).
"""

from __future__ import annotations

import csv
import io

from .. import db
from . import NotFound, RuleError

STATUSES = [
    ("reikia", "Neužsakyta"),
    ("uzsakyta", "Užsakyta"),
    ("patvirtinta", "Patvirtinta data"),
    ("dalinai", "Gauta dalinai"),
    ("gauta", "Gauta"),
    ("atsaukta", "Atšaukta"),
]
STATUS_LABEL = dict(STATUSES)

FIELDS = ("project_id", "assembly_id", "item_no", "name", "spec", "qty", "unit", "supplier", "po_no",
          "po_line", "ordered_date", "promised_date", "need_date", "location", "note")


def status_of(c: dict) -> str:
    if c["cancelled"]:
        return "atsaukta"
    if c["qty_received"] >= c["qty"] > 0:
        return "gauta"
    if c["qty_received"] > 0:
        return "dalinai"
    if c["promised_date"]:
        return "patvirtinta"
    if c["po_no"]:
        return "uzsakyta"
    return "reikia"


def decorate(c: dict, today: str) -> dict:
    """Prideda išvestinius laukus: būseną ir rizikas."""
    st = status_of(c)
    c["status"] = st
    c["status_label"] = STATUS_LABEL[st]
    open_ = st not in ("gauta", "atsaukta")
    # vėluoja – tiekėjo pažadėta data praėjo, o dar ne viskas gauta
    c["late"] = bool(open_ and c["promised_date"] and c["promised_date"] < today)
    # rizika – patvirtinta data vėlesnė nei reikia gamybai, arba reikia jau
    # greitai (7 d.), o tiekėjas datos dar nepatvirtino ar net neužsakyta
    c["risk"] = bool(open_ and c["need_date"] and (
        (c["promised_date"] and c["promised_date"] > c["need_date"])
        or (st in ("reikia", "uzsakyta") and c["need_date"] <= _plus_days(today, 7))))
    c["overdue_need"] = bool(open_ and c["need_date"] and c["need_date"] < today)
    return c


def _plus_days(day: str, n: int) -> str:
    from datetime import date, timedelta
    return (date.fromisoformat(day) + timedelta(days=n)).isoformat()


def _today() -> str:
    return db.now()[:10]


def list_components(con, project_id=None, status=None, problems=False, supplier=None) -> list[dict]:
    q = ("SELECT c.*, p.code AS project_code, p.name AS project_name, a.code AS assembly_code, "
         "a.name AS assembly_name FROM components c JOIN projects p ON p.id=c.project_id "
         "LEFT JOIN assemblies a ON a.id=c.assembly_id WHERE 1=1")
    args = []
    if project_id:
        q += " AND c.project_id=?"; args.append(project_id)
    if supplier:
        q += " AND c.supplier=?"; args.append(supplier)
    q += " ORDER BY p.code, COALESCE(a.sort, 9999), c.need_date IS NULL, c.need_date, c.id"
    today = _today()
    out = [decorate(c, today) for c in db.rows(con.execute(q, args))]
    if status == "open":
        out = [c for c in out if c["status"] not in ("gauta", "atsaukta")]
    elif status:
        out = [c for c in out if c["status"] == status]
    if problems:
        out = [c for c in out if c["late"] or c["risk"] or c["overdue_need"]]
    return out


def summary(rows: list[dict]) -> dict:
    s = {k: 0 for k, _ in STATUSES}
    for c in rows:
        s[c["status"]] += 1
    active = [c for c in rows if c["status"] != "atsaukta"]
    return {"by_status": s, "total": len(active),
            "late": sum(c["late"] for c in rows), "risk": sum(c["risk"] for c in rows),
            "received_pct": round(100 * s["gauta"] / len(active)) if active else 0}


def get(con, cid) -> dict:
    c = db.row(con.execute("SELECT * FROM components WHERE id=?", (cid,)))
    if not c:
        raise NotFound("Komponento eilutės nėra")
    return c


def save(con, user_id, data: dict, cid=None, source="rankinis") -> int:
    vals = {k: (data[k] if data[k] != "" else None) if k.endswith("_date") or k == "assembly_id" else data[k]
            for k in FIELDS if k in data}
    if "qty" in vals:
        vals["qty"] = float(vals["qty"] or 0)
        if vals["qty"] <= 0:
            raise RuleError("Kiekis turi būti didesnis už nulį")
    now = db.now()
    if cid is None:
        if not vals.get("project_id") or not (vals.get("name") or "").strip():
            raise RuleError("Reikia projekto ir komponento pavadinimo")
        vals.setdefault("qty", 1.0)
        cols = list(vals) + ["source", "updated", "created"]
        cur = con.execute(f"INSERT INTO components ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})",
                          (*vals.values(), source, now, now))
        cid = cur.lastrowid
        db.log_event(con, user_id, "component", cid, "create", vals)
    else:
        old = get(con, cid)
        if vals:
            con.execute(f"UPDATE components SET {', '.join(k + '=?' for k in vals)}, updated=? WHERE id=?",
                        (*vals.values(), now, cid))
            db.log_event(con, user_id, "component", cid, "update", vals)
        c = get(con, cid)
        # tiekėjas nukėlė datą – signalas (paliečia surinkimą?); importas eina tuo pačiu keliu
        if old["promised_date"] and c["promised_date"] and c["promised_date"] > old["promised_date"]:
            from .signals import component_delay
            component_delay(con, user_id, c, old["promised_date"])
    c = get(con, cid)
    _sync_phase(con, user_id, c["project_id"], c["assembly_id"])
    return cid


def receive(con, user_id, cid, qty: float, note="", source="rankinis", when: str | None = None) -> dict:
    """Užregistruoja gavimą. Daugiau, nei užsakyta, priimti negalima – tai
    beveik visada įvedimo klaida, o ne tikras perteklius."""
    c = get(con, cid)
    qty = float(qty or 0)
    if c["cancelled"]:
        raise RuleError("Atšaukta eilutė negaunama")
    if qty <= 0:
        raise RuleError("Gautas kiekis turi būti didesnis už nulį")
    if c["qty_received"] + qty > c["qty"] + 1e-9:
        raise RuleError(f"Gauta būtų {c['qty_received'] + qty:g}, o užsakyta tik {c['qty']:g} {c['unit']}")
    at = when or db.now()
    con.execute("INSERT INTO component_receipts (component_id, qty, at, user_id, source, note) VALUES (?,?,?,?,?,?)",
                (cid, qty, at, user_id, source, note or ""))
    con.execute("UPDATE components SET qty_received=qty_received+?, received_date=?, updated=? WHERE id=?",
                (qty, at[:10], db.now(), cid))
    db.log_event(con, user_id, "component", cid, "receive", {"qty": qty, "source": source})
    _sync_phase(con, user_id, c["project_id"], c["assembly_id"])
    return decorate(get(con, cid), _today())


def cancel(con, user_id, cid, on=True) -> None:
    c = get(con, cid)
    if on and c["qty_received"] > 0:
        raise RuleError("Jau gautos eilutės atšaukti negalima")
    con.execute("UPDATE components SET cancelled=?, updated=? WHERE id=?", (1 if on else 0, db.now(), cid))
    db.log_event(con, user_id, "component", cid, "cancel" if on else "restore")
    _sync_phase(con, user_id, c["project_id"], c["assembly_id"])


def receipts(con, limit=30, project_id=None) -> list[dict]:
    q = ("SELECT r.*, c.name, c.item_no, c.unit, c.qty AS qty_total, c.qty_received, c.supplier, c.po_no, "
         "p.code AS project_code, a.code AS assembly_code, u.name AS user_name "
         "FROM component_receipts r JOIN components c ON c.id=r.component_id JOIN projects p ON p.id=c.project_id "
         "LEFT JOIN assemblies a ON a.id=c.assembly_id LEFT JOIN users u ON u.id=r.user_id")
    args = []
    if project_id:
        q += " WHERE c.project_id=?"; args.append(project_id)
    return db.rows(con.execute(q + " ORDER BY r.at DESC, r.id DESC LIMIT ?", (*args, limit)))


def missing_for_assembly(con, assembly_id) -> int:
    """Kiek komponentų eilučių šiam mazgui (ir visam projektui) dar negauta."""
    a = con.execute("SELECT project_id FROM assemblies WHERE id=?", (assembly_id,)).fetchone()
    if not a:
        return 0
    return con.execute(
        "SELECT COUNT(*) FROM components WHERE project_id=? AND (assembly_id=? OR assembly_id IS NULL) "
        "AND cancelled=0 AND qty_received < qty", (a[0], assembly_id)).fetchone()[0]


def _sync_phase(con, user_id, project_id, assembly_id) -> None:
    """Etapą „komponentai“ pažymi pagal tikrą pirkimų būseną: ką nors užsakius
    – vykdoma, viską gavus – baigta. Ranka baigto etapo neatidaro atgal, nebent
    atsirado naujų negautų eilučių."""
    phases = db.rows(con.execute(
        "SELECT * FROM phases WHERE project_id=? AND kind='komponentai' AND (assembly_id IS ? OR assembly_id IS NULL)",
        (project_id, assembly_id)))
    for ph in phases:
        scope = "assembly_id=?" if ph["assembly_id"] else "1=1"
        args = (project_id, ph["assembly_id"]) if ph["assembly_id"] else (project_id,)
        rows = db.rows(con.execute(
            f"SELECT po_no, qty, qty_received FROM components WHERE project_id=? AND {scope} AND cancelled=0", args))
        if not rows:
            continue
        all_in = all(r["qty_received"] >= r["qty"] for r in rows)
        any_ordered = any(r["po_no"] or r["qty_received"] > 0 for r in rows)
        now = db.now()
        if all_in and ph["status"] != "baigta":
            con.execute("UPDATE phases SET status='baigta', actual_start=COALESCE(actual_start, ?), actual_end=? "
                        "WHERE id=?", (now, now, ph["id"]))
            db.log_event(con, user_id, "phase", ph["id"], "status", {"status": "baigta", "auto": "components"})
        elif not all_in and any_ordered and ph["status"] != "vykdoma":
            con.execute("UPDATE phases SET status='vykdoma', actual_start=COALESCE(actual_start, ?), actual_end=NULL "
                        "WHERE id=?", (now, ph["id"]))
            db.log_event(con, user_id, "phase", ph["id"], "status", {"status": "vykdoma", "auto": "components"})


# ---------- importas iš ERP eksporto ----------

COLUMNS = ["projektas", "mazgas", "prekes_kodas", "pavadinimas", "specifikacija", "kiekis", "vnt", "tiekejas",
           "uzsakymo_nr", "eilute", "uzsakyta", "patvirtinta_data", "reikia_iki", "gauta_kiekis", "gauta_data",
           "vieta", "pastaba"]
REQUIRED = ["projektas", "pavadinimas", "kiekis"]


def template() -> str:
    return ";".join(COLUMNS) + "\n"


def _num(s: str) -> float:
    return float((s or "0").replace(",", ".").replace(" ", ""))


def import_csv(con, user, text: str, dry_run=False) -> dict:
    """Importas iš ERP eksporto (kol nėra tiesioginės D365 integracijos).

    Eilutė atpažįstama pagal užsakymo nr. + eilutę, o jų nesant – pagal
    projektą, mazgą ir prekės kodą; rasta atnaujinama, nerasta – sukuriama.
    Padidėjęs gautas kiekis užregistruojamas kaip gavimas (tik skirtumas),
    tad pakartotinis to paties failo importas nieko nedubliuoja.
    Klaida bent vienoje eilutėje – neįrašoma niekas.
    """
    text = text.lstrip("﻿")
    first = text.splitlines()[0] if text else ""
    delim = ";" if first.count(";") >= first.count(",") else ","
    reader = csv.DictReader(io.StringIO(text), delimiter=delim)
    missing = [c for c in REQUIRED if c not in (reader.fieldnames or [])]
    if missing:
        raise RuleError(f"Trūksta stulpelių: {', '.join(missing)}. Reikalingi: {';'.join(COLUMNS)}")
    rows = [{k: (v or "").strip() for k, v in r.items() if k} for r in reader]

    projects = {r["code"]: r["id"] for r in con.execute("SELECT id, code FROM projects")}
    asms = {(r["project_id"], r["code"]): r["id"] for r in con.execute("SELECT id, project_id, code FROM assemblies")}
    errors, plan = [], []
    for i, r in enumerate(rows, start=2):
        for c in REQUIRED:
            if not r.get(c):
                errors.append(f"{i} eil.: tuščias „{c}“")
        pid = projects.get(r.get("projektas"))
        if r.get("projektas") and not pid:
            errors.append(f"{i} eil.: nežinomas projektas „{r['projektas']}“")
        aid = None
        if pid and r.get("mazgas"):
            aid = asms.get((pid, r["mazgas"]))
            if not aid:
                errors.append(f"{i} eil.: projekte {r['projektas']} nėra mazgo „{r['mazgas']}“")
        try:
            qty, got = _num(r.get("kiekis")), _num(r.get("gauta_kiekis"))
            if qty <= 0:
                errors.append(f"{i} eil.: kiekis turi būti didesnis už nulį")
            elif got > qty:
                errors.append(f"{i} eil.: gauta {got:g} daugiau nei užsakyta {qty:g}")
        except ValueError:
            errors.append(f"{i} eil.: kiekis turi būti skaičius")
            continue
        for c in ("uzsakyta", "patvirtinta_data", "reikia_iki", "gauta_data"):
            v = r.get(c)
            if v and not _is_date(v):
                errors.append(f"{i} eil.: „{c}“ turi būti data YYYY-MM-DD")
        plan.append((pid, aid, qty, got, r))

    res = {"rows": len(rows), "errors": errors, "created": 0, "updated": 0, "receipts": 0}
    if errors or dry_run:
        return res
    for pid, aid, qty, got, r in plan:
        if r.get("uzsakymo_nr"):
            ex = db.row(con.execute("SELECT * FROM components WHERE po_no=? AND po_line=?",
                                    (r["uzsakymo_nr"], r.get("eilute", ""))))
        else:
            ex = db.row(con.execute(
                "SELECT * FROM components WHERE project_id=? AND assembly_id IS ? AND item_no=? AND item_no!='' "
                "AND po_no=''", (pid, aid, r.get("prekes_kodas", ""))))
        data = {"project_id": pid, "assembly_id": aid, "item_no": r.get("prekes_kodas", ""), "name": r["pavadinimas"],
                "spec": r.get("specifikacija", ""), "qty": qty, "unit": r.get("vnt") or "vnt",
                "supplier": r.get("tiekejas", ""), "po_no": r.get("uzsakymo_nr", ""), "po_line": r.get("eilute", ""),
                "ordered_date": r.get("uzsakyta") or None, "promised_date": r.get("patvirtinta_data") or None,
                "need_date": r.get("reikia_iki") or None, "location": r.get("vieta", ""), "note": r.get("pastaba", "")}
        if ex:
            cid = save(con, user["id"], data, ex["id"])
            res["updated"] += 1
            before = ex["qty_received"]
        else:
            cid = save(con, user["id"], data, source="importas")
            res["created"] += 1
            before = 0
        if got > before + 1e-9:
            when = f"{r['gauta_data']}T12:00:00+00:00" if r.get("gauta_data") else None
            receive(con, user["id"], cid, got - before, "importas iš ERP", source="importas", when=when)
            res["receipts"] += 1
    db.log_event(con, user["id"], "import", None, "components", {k: v for k, v in res.items() if k != "errors"})
    return res


def _is_date(s: str) -> bool:
    from datetime import date
    try:
        date.fromisoformat(s)
        return True
    except ValueError:
        return False


def supplier_report(con, a=None, b=None) -> list[dict]:
    """Tiekėjų patikimumas: kiek eilučių gauta vėliau nei pažadėta."""
    from datetime import date
    rows = db.rows(con.execute(
        "SELECT supplier, promised_date, received_date, qty, qty_received, cancelled FROM components "
        "WHERE supplier!='' AND cancelled=0"))
    today = _today()
    out = {}
    for r in rows:
        s = out.setdefault(r["supplier"], {"supplier": r["supplier"], "lines": 0, "received": 0,
                                           "late": 0, "delay_days": 0, "open_late": 0})
        done = r["qty_received"] >= r["qty"]
        if done and a and (r["received_date"] or "") < a[:10]:
            continue
        if done and b and (r["received_date"] or "") > b[:10]:
            continue
        s["lines"] += 1
        if done:
            s["received"] += 1
            if r["promised_date"] and r["received_date"] and r["received_date"] > r["promised_date"]:
                s["late"] += 1
                s["delay_days"] += (date.fromisoformat(r["received_date"]) - date.fromisoformat(r["promised_date"])).days
        elif r["promised_date"] and r["promised_date"] < today:
            s["open_late"] += 1
    res = []
    for s in out.values():
        s["avg_delay_d"] = round(s["delay_days"] / s["late"], 1) if s["late"] else 0
        s["on_time_pct"] = round(100 * (s["received"] - s["late"]) / s["received"]) if s["received"] else None
        res.append(s)
    return sorted(res, key=lambda x: (-(x["late"] + x["open_late"]), x["supplier"]))
