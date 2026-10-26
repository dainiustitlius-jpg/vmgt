"""Planavimo signalai: kas pasikeitė ir ką tai paveikė.

Vartotojo sprendimas (2026-10-26): kiekvienas pakeitimas turi signalizuoti
kitiems projektams. Signalą sukelia:

- planuotojo pakeitimai (etapo datos, prioritetas, centro eilė, projekto
  patvirtinimas) – `planner.apply`, su poveikio analize;
- vėlavimai ceche – operacija užtruko gerokai ilgiau nei norma arba ilga
  neplanuota pauzė: pasislenka kitų projektų darbai TAME centre;
- komponentų vėlavimai – tiekėjas nukėlė datą arba ji praėjo, o negauta:
  paliečia surinkimo etapą;
- projektas iš krepšelio tapo vykdomu – kurių vykdomų projektų departamentai
  dėl to persikrauna.

Kiekvienas signalas – vienas `plan_changes` įrašas (bendras žurnalas
planuotojo lange) ir pranešimai paveiktų projektų žmonėms (`notifications`):
projekto vadovui, neužbaigtų etapų atsakingiesiems ir planuotojams. Tas pats
signalas tam pačiam žmogui – vieną kartą (`key`).
"""

from __future__ import annotations

import json

from .. import db

SHOP_OVER = 1.25          # operacija užtruko > 125 % normos …
SHOP_MIN_EXTRA = 30       # … ir bent 30 min. daugiau
PAUSE_MIN = 60            # neplanuota pauzė nuo 60 min.
PLANNED_PAUSES = ("pertrauka", "pamaina")


def recipients(con, project_id) -> set[int]:
    """Kam rūpi projekto plano pokyčiai: vadovui, neužbaigtų etapų atsakingiesiems, planuotojams."""
    ids = {r[0] for r in con.execute("SELECT manager_id FROM projects WHERE id=? AND manager_id IS NOT NULL",
                                     (project_id,))}
    ids |= {r[0] for r in con.execute("SELECT DISTINCT owner_id FROM phases WHERE project_id=? AND status!='baigta' "
                                      "AND owner_id IS NOT NULL", (project_id,))}
    ids |= {r[0] for r in con.execute("SELECT id FROM users WHERE role='planuotojas' AND active=1")}
    return ids


def record(con, user_id, kind, project_id, summary, affected: list[dict], note="", own: list | None = None,
           key: str | None = None, link: str = "#/planas") -> int | None:
    """Įrašo signalą ir išsiunčia pranešimus paveiktiems projektams.
    `affected`: [{project_id, code, severity, reasons: [...]}]. Grąžina plan_changes id
    (None – toks signalas jau buvo)."""
    if key and con.execute("SELECT 1 FROM plan_changes WHERE key=?", (key,)).fetchone():
        return None
    cur = con.execute(
        "INSERT INTO plan_changes (at, user_id, kind, project_id, summary, note, impact, key) VALUES (?,?,?,?,?,?,?,?)",
        (db.now(), user_id, kind, project_id, summary, note or "",
         json.dumps({"affected": affected, "own": own or []}, ensure_ascii=False), key))
    cid = cur.lastrowid
    key = key or f"change:{cid}"
    for a in affected:
        body = "\n".join(a["reasons"]) + (f"\nPastaba: {note}" if note else "")
        for uid in recipients(con, a["project_id"]) - {user_id}:
            con.execute(
                "INSERT OR IGNORE INTO notifications (user_id, project_id, change_id, kind, severity, title, body, link, "
                "key, created) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (uid, a["project_id"], cid, kind, a.get("severity", "info"),
                 f"{a['code']}: {summary}" if a["project_id"] == project_id else f"{a['code']} paveiktas – {summary}", body,
                 link, f"{key}:{a['project_id']}", db.now()))
    return cid


# ---------- vėlavimai ceche ----------

def _queue_behind(con, t) -> list[dict]:
    """Kitų projektų darbai, laukiantys tame pačiame centre."""
    return db.rows(con.execute(
        "SELECT t.id, t.name, t.project_id, p.code, a.code AS assembly_code FROM tasks t "
        "JOIN projects p ON p.id=t.project_id JOIN assemblies a ON a.id=t.assembly_id "
        "WHERE t.centre_id=? AND t.status='laukia' AND t.approved=1 AND t.project_id!=? AND t.created<=? "
        "ORDER BY t.queue_pos, t.id", (t["centre_id"], t["project_id"], db.now())))


def shop_delay(con, user_id, t: dict, extra_min: float, why: str, key: str) -> None:
    behind = _queue_behind(con, t)
    if not behind:
        return
    by_project = {}
    for b in behind:
        by_project.setdefault(b["project_id"], {"project_id": b["project_id"], "code": b["code"],
                                                "severity": "yellow", "reasons": []})
        by_project[b["project_id"]]["reasons"].append(
            f"{t['centre_code']}: jūsų „{b['assembly_code']} · {b['name']}“ pradžia vėluos ~{_hm(extra_min)}")
    summary = f"{t['centre_code']} vėluoja {_hm(extra_min)} – {t['project_code']} {t['assembly_code']} · {t['name']} ({why})"
    record(con, user_id, "shop_delay", t["project_id"], summary, list(by_project.values()), key=key,
           link=f"#/planas/{t['centre_code']}")


def on_stop(con, user_id, t: dict, work_s: float, done_qty: int) -> None:
    """Baigta operacija užtruko gerokai ilgiau nei norma."""
    norm = (t["norm_min"] or 0) * done_qty
    extra = work_s / 60 - norm
    if norm and work_s / 60 > norm * SHOP_OVER and extra >= SHOP_MIN_EXTRA:
        shop_delay(con, user_id, t, extra, f"faktas {_hm(work_s / 60)}, norma {_hm(norm)}", f"shop:stop:{t['id']}")


def on_resume(con, user_id, t: dict, pause: dict) -> None:
    """Po ilgos neplanuotos pauzės (gedimas, medžiaga…)."""
    if pause["reason"] in PLANNED_PAUSES:
        return
    mins = (db.parse_ts(db.now()) - db.parse_ts(pause["start"])).total_seconds() / 60
    if mins >= PAUSE_MIN:
        from .tasks import PAUSE_LABEL
        shop_delay(con, user_id, t, mins, PAUSE_LABEL.get(pause["reason"], pause["reason"]).lower(),
                   f"shop:pause:{pause['id']}")


# ---------- komponentai ----------

def component_delay(con, user_id, c: dict, old_promised: str | None, late=False) -> int | None:
    """Tiekėjas nukėlė datą (arba ji praėjo, o negauta) – kurį etapą tai liečia."""
    if c["qty_received"] >= c["qty"] or c.get("cancelled"):
        return None
    p = db.row(con.execute("SELECT id, code FROM projects WHERE id=?", (c["project_id"],)))
    ph = db.row(con.execute(
        "SELECT kind, plan_start FROM phases WHERE project_id=? AND kind='surinkimas' AND status!='baigta' "
        "AND (assembly_id IS ? OR assembly_id IS NULL) ORDER BY plan_start LIMIT 1", (c["project_id"], c["assembly_id"])))
    reasons = []
    if late:
        reasons.append(f"Pažadėta {c['promised_date']}, bet dar negauta ({c['qty_received']:g} iš {c['qty']:g})")
    else:
        reasons.append(f"Tiekėjas nukėlė datą: {old_promised or '—'} → {c['promised_date']}")
    if c.get("need_date") and c["promised_date"] and c["promised_date"] > c["need_date"]:
        reasons.append(f"Reikia iki {c['need_date']} – atvyks per vėlai")
    severity = "yellow"
    if ph and ph["plan_start"] and (c["promised_date"] or "") > ph["plan_start"]:
        reasons.append(f"Paliečia surinkimo etapą (planuota pradžia {ph['plan_start']})")
        severity = "red"
    what = f"{c['item_no'] + ' ' if c.get('item_no') else ''}{c['name']}"
    summary = (f"komponentas vėluoja: {what}" if late else f"tiekėjas nukėlė datą: {what}")
    return record(con, user_id, "component_delay", c["project_id"], summary,
           [{"project_id": p["id"], "code": p["code"], "severity": severity, "reasons": reasons}],
           key=f"comp:{'late' if late else 'moved'}:{c['id']}:{c['promised_date']}",
           link=f"#/komponentai/{c['project_id']}")


def scan(con) -> int:
    """Pažadėta data praėjo, o komponentas negautas – signalas vieną kartą
    kiekvienai pažadėtai datai. Kviečiama skaitant pranešimus (be fono gijų)."""
    from .components import list_components
    n = 0
    for c in list_components(con, problems=True):
        if c.get("late") and component_delay(con, None, c, c["promised_date"], late=True):
            n += 1
    return n


# ---------- projektas iš krepšelio ----------

def project_activated(con, user_id, project_id) -> None:
    """Projektas ką tik tapo vykdomu: kurie KITI vykdomi projektai dėl jo
    gauna mažiau resurso (jų departamentai persikrauna)."""
    from .planner import impact_of_activation
    imp = impact_of_activation(con, project_id)
    p = db.row(con.execute("SELECT code, name FROM projects WHERE id=?", (project_id,)))
    record(con, user_id, "activate", project_id, f"patvirtintas projektas {p['code']} {p['name']}",
           imp["affected"], own=imp["own"], key=f"activate:{project_id}", link="#/apkrova")


# ---------- skaitymas ----------

def list_for(con, user_id, unread_only=False, limit=50) -> list[dict]:
    q = ("SELECT n.*, p.code AS project_code FROM notifications n LEFT JOIN projects p ON p.id=n.project_id "
         "WHERE n.user_id=?" + (" AND n.read_at IS NULL" if unread_only else "") + " ORDER BY n.created DESC, n.id DESC LIMIT ?")
    return db.rows(con.execute(q, (user_id, limit)))


def unread(con, user_id) -> int:
    return con.execute("SELECT COUNT(*) FROM notifications WHERE user_id=? AND read_at IS NULL", (user_id,)).fetchone()[0]


def mark_read(con, user_id, ids=None) -> int:
    q = "UPDATE notifications SET read_at=? WHERE user_id=? AND read_at IS NULL"
    args = [db.now(), user_id]
    if ids:
        q += f" AND id IN ({','.join('?' * len(ids))})"
        args += list(ids)
    return con.execute(q, args).rowcount


def changes(con, limit=40, project_id=None) -> list[dict]:
    q = ("SELECT c.*, u.name AS user_name, p.code AS project_code FROM plan_changes c "
         "LEFT JOIN users u ON u.id=c.user_id LEFT JOIN projects p ON p.id=c.project_id")
    args = []
    if project_id:
        q += " WHERE c.project_id=? OR c.impact LIKE ?"
        args = [project_id, f'%"project_id": {project_id},%']
    out = db.rows(con.execute(q + " ORDER BY c.at DESC, c.id DESC LIMIT ?", (*args, limit)))
    for c in out:
        c["impact"] = json.loads(c["impact"] or "{}")
    return out


def _hm(minutes: float) -> str:
    m = int(round(minutes))
    return f"{m // 60} val. {m % 60} min." if m >= 60 else f"{m} min."
