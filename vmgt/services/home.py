"""Pradžios ekranas: modulių plytelės su tuo, kas laukia būtent šio žmogaus.

Vartotojo sprendimas (2026-10-26): pradžia – **modulių plytelės** su
skaičiais. Įrankiu naudojasi daug skirtingų rolių, tad plytelė rodoma tik
tam, kas turi bent vieną modulio teisę, o skaičiai – tie, dėl kurių JIS
gali ką nors padaryti (meistrui – tik jo barų eilės ir failai). Skaičiai –
paprastos užklausos, ne pilnos ataskaitos: pradžia turi atsidaryti iškart.
"""

from __future__ import annotations

from datetime import date, timedelta

from .. import db
from . import auth, capacity, components, quality


def _c(n, label, sev="", href=""):
    return {"n": n, "label": label, "sev": sev, "href": href}


def tiles(con, user) -> dict:
    perms = auth.perms_of(user)
    today = db.now()[:10]
    out = []

    def mine(code, area):
        return auth.scope_of(user) == "all" or auth.can_centre(user, code, area)

    # --- projektai ---
    if "view" in perms:
        st = dict(con.execute("SELECT status, COUNT(*) FROM projects GROUP BY status").fetchall())
        late = con.execute("SELECT COUNT(*) FROM projects WHERE status='vykdomas' AND due_date < ?", (today,)).fetchone()[0]
        out.append({"key": "projektai", "counters": [
            _c(st.get("vykdomas", 0), "vykdomi", "", "#/projektai"),
            _c(st.get("krepselis", 0), "krepšelyje", "", "#/projektai"),
            _c(late, "praleistas terminas", "red" if late else "", "#/projektai")]})

    # --- mano darbai: visiems ---
    my = con.execute("SELECT COUNT(*), SUM(due_date < ?) FROM actions WHERE owner_id=? "
                     "AND status NOT IN ('atlikta','atsaukta')", (today, user["id"])).fetchone()
    unread = con.execute("SELECT COUNT(*) FROM notifications WHERE user_id=? AND read_at IS NULL",
                         (user["id"],)).fetchone()[0]
    out.append({"key": "mano", "counters": [
        _c(my[0] or 0, "atviros užduotys", "", "#/mano"),
        _c(my[1] or 0, "vėluoja", "red" if my[1] else "", "#/uzduotys"),
        _c(unread, "neperskaityti pranešimai", "yellow" if unread else "", "#bell")]})

    # --- planavimas ---
    if perms & {"plan", "calendar"} or "view" in perms:
        cnt = []
        if "plan" in perms:
            rows = con.execute(
                "SELECT c.code, ar.code FROM tasks t JOIN work_centres c ON c.id=t.centre_id "
                "LEFT JOIN areas ar ON ar.id=c.area_id JOIN assemblies a ON a.id=t.assembly_id "
                "WHERE t.approved=0 AND t.status!='baigta' AND a.released_at IS NOT NULL").fetchall()
            n = sum(1 for r in rows if mine(r[0], r[1]))
            cnt.append(_c(n, "laukia patvirtinimo eilėse", "yellow" if n else "", "#/planas/eiles"))
        if "view" in perms:
            rep = capacity.report(con, weeks=4)
            short = len({s["code"] for s in rep["shortages"] if not s["basket_only"]})
            cnt.append(_c(short, "departamentams trūksta žmonių (4 sav.)", "red" if short else "", "#/apkrova"))
        soon = (date.fromisoformat(today) + timedelta(days=14)).isoformat()
        n = con.execute("SELECT COUNT(*) FROM calendar_days WHERE day BETWEEN ? AND ? AND kind IN ('nedarbo','remontas')",
                        (today, soon)).fetchone()[0]
        cnt.append(_c(n, "nedarbo / remonto dienų per 14 d.", "", "#/planas/kalendorius"))
        out.append({"key": "planavimas", "counters": cnt})

    # --- gamyba ---
    if perms & {"view", "execute", "tasks"}:
        cnt = []
        st = dict(con.execute("SELECT status, COUNT(*) FROM tasks WHERE status IN ('vykdoma','pristabdyta') "
                              "GROUP BY status").fetchall())
        if "view" in perms:
            cnt += [_c(st.get("vykdoma", 0), "operacijos vykdomos", "", "#/cechas"),
                    _c(st.get("pristabdyta", 0), "pristabdytos", "yellow" if st.get("pristabdyta") else "", "#/cechas")]
        if "ack_rev" in perms:
            rows = con.execute(
                "SELECT c.code, ar.code FROM task_files f JOIN tasks t ON t.id=f.task_id "
                "JOIN work_centres c ON c.id=t.centre_id LEFT JOIN areas ar ON ar.id=c.area_id "
                "WHERE f.current=1 AND f.needs_ack=1 AND t.status!='baigta'").fetchall()
            n = sum(1 for r in rows if mine(r[0], r[1]))
            cnt.append(_c(n, "failai laukia mano patvirtinimo", "yellow" if n else "", "#/cechas"))
        if "tasks" in perms:
            n = con.execute(
                "SELECT COUNT(DISTINCT a.id) FROM assemblies a JOIN tasks t ON t.assembly_id=a.id "
                "JOIN projects p ON p.id=a.project_id WHERE a.released_at IS NULL "
                "AND p.status IN ('vykdomas','krepselis')").fetchone()[0]
            cnt.append(_c(n, "maršrutai neišleisti", "yellow" if n else "", "#/technologija"))
        if "execute" in perms and "view" not in perms:
            n = sum(1 for r in con.execute("SELECT c.code, ar.code FROM work_centres c LEFT JOIN areas ar "
                                           "ON ar.id=c.area_id WHERE c.active=1").fetchall()
                    if auth.can_centre(user, r[0], r[1]))
            cnt.append(_c(n, "mano darbo centrai", "", "#/t"))
        out.append({"key": "gamyba", "counters": cnt})

    # --- kokybė ---
    if perms & {"view", "ncr_report", "quality"}:
        cnt = []
        if "view" in perms or "quality" in perms:
            q = quality.qc_queue(con)
            held = sum(1 for r in q if r["holding"])
            cnt.append(_c(len(q), "patikros laukia KK", "yellow" if q and "quality" in perms else "", "#/kokybe"))
            if held:
                cnt.append(_c(held, "iš jų sulaikytos detalės", "red", "#/kokybe"))
        old = (date.fromisoformat(today) - timedelta(days=7)).isoformat()
        r = con.execute("SELECT COUNT(*), SUM(reported_at < ?) FROM ncr WHERE status!='uzdaryta'", (old,)).fetchone()
        cnt.append(_c(r[0] or 0, "atviros neatitiktys", "", "#/ncr"))
        if r[1]:
            cnt.append(_c(r[1], "atviros > 7 d.", "red", "#/ncr"))
        out.append({"key": "kokybe", "counters": cnt})

    # --- tiekimas ---
    if "view" in perms or perms & {"purchase", "receive"}:
        rows = components.list_components(con, status="open")
        late = sum(c["late"] for c in rows)
        risk = sum(c["risk"] and not c["late"] for c in rows)
        nord = sum(c["status"] == "reikia" for c in rows)
        out.append({"key": "tiekimas", "counters": [
            _c(late, "tiekėjai vėluoja", "red" if late else "", "#/komponentai"),
            _c(risk, "rizika", "yellow" if risk else "", "#/komponentai"),
            _c(nord, "neužsakyta", "yellow" if nord and "purchase" in perms else "", "#/komponentai")]})

    if "view" in perms:
        out.append({"key": "analitika", "counters": []})

    if "admin" in perms:
        n = con.execute("SELECT COUNT(*) FROM users WHERE active=1").fetchone()[0]
        nopin = con.execute("SELECT COUNT(*) FROM users WHERE active=1 AND role='operatorius' AND pin_hash IS NULL"
                            ).fetchone()[0]
        last = con.execute("SELECT at FROM access_log ORDER BY at DESC LIMIT 1").fetchone()
        out.append({"key": "admin", "counters": [
            _c(n, "aktyvūs vartotojai", "", "#/admin/vartotojai"),
            _c(len(auth.list_roles(con)), "rolės", "", "#/admin/roles"),
            _c(nopin, "operatoriai be PIN", "yellow" if nopin else "", "#/admin/vartotojai")],
            "note": f"paskutinis teisių pakeitimas {last[0][:10]}" if last else ""})
    return {"tiles": out}
