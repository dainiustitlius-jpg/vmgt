"""Pavyzdiniai duomenys testinei aplinkai.

Projektai pažymėti `sample=1` ir pavadinimuose turi žymę PAVYZDYS – kad niekas
jų nepalaikytų tikrais. Dalis darbų „atlikta“ praeityje (laikrodis
perstatomas), kad cecho būsena ir analitika iškart turėtų ką rodyti.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from .. import db
from . import auth, components, drawings, projects, tasks

TEST_PASSWORD = "vmgt2026"

USERS = [
    # login, vardas, rolė, PIN, centrai
    ("admin", "Administratorius", "admin", None, []),
    ("vadovas", "Rasa Vadovienė", "vadovas", None, []),
    ("planuotojas", "Tomas Planas", "planuotojas", None, []),
    ("technologas", "Ieva Technologė", "technologas", None, []),
    ("meistras", "Andrius Meistras", "meistras", "9999", []),
    ("kokybe", "Laura Kokybė", "kokybe", None, []),
    ("pirkimai", "Eglė Pirkėja", "pirkimai", None, []),
    ("sandelis", "Paulius Sandėlis", "sandelis", "5555", []),
    ("op1", "Jonas Petraitis", "operatorius", "1111", []),
    ("op2", "Marius Kazlauskas", "operatorius", "2222", []),
    ("op3", "Darius Suvirintojas", "operatorius", "3333", ["SV-01", "SV-02"]),
]

CENTRES = [
    ("LAZ-01", "Lazeris", "pjovimas", 0),
    ("PLZ-01", "Plazma", "pjovimas", 0),
    ("LNK-01", "Lenkimo presas", "lenkimas", 0),
    ("MECH-01", "Frezavimas, tekinimas", "mechaninis", 0),
    ("SV-01", "Suvirinimas 1", "suvirinimas", 1),
    ("SV-02", "Suvirinimas 2", "suvirinimas", 1),
    ("DAZ-01", "Dažymas", "dazymas", 1),
    ("SUR-01", "Mechaninis surinkimas", "surinkimas", 1),
    ("EL-01", "Elektros surinkimas", "elektra", 1),
    ("TST-01", "Testavimas", "testavimas", 1),
]


def is_empty(con) -> bool:
    return con.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0


def seed(con, files_dir: Path, today: datetime | None = None) -> None:
    today = today or datetime.now(timezone.utc).replace(microsecond=0)
    real_clock = db._clock

    def at(dt: datetime):
        db.set_clock(lambda: dt.isoformat(timespec="seconds"))

    def d(days: int) -> str:
        return (today.date() + timedelta(days=days)).isoformat()

    try:
        at(today - timedelta(days=20))
        uid = {}
        for login, name, role, pin, centres in USERS:
            uid[login] = auth.create_user(con, login, name, role, TEST_PASSWORD, pin=pin, centres=centres)
        cid = {}
        for code, name, kind, manual in CENTRES:
            cid[code] = projects.save_centre(con, None, {"code": code, "name": name, "kind": kind, "manual": manual})
        admin = {"id": uid["admin"], "centres": "[]"}

        # brėžiniai: 1023-100 turi dvi revizijas – dažymo užduotis sukurta su A
        for no, rev, title in [("1023-100", "A", "Rėmas R-1200"), ("1023-200", "C", "Konvejerio šonas"),
                               ("1023-900", "A", "Linijos K-12 surinkimas"), ("2210-100", "B", "Apsauginė tvora"),
                               ("2210-200", "A", "Pozicionierius")]:
            drawings.save(con, files_dir, admin, no, rev, f"{no}_{rev}.pdf",
                          drawings.sample_pdf([f"PAVYZDYS  {no}  rev. {rev}", title,
                                               "Pavyzdinis brezinys testinei aplinkai"]), title)

        def project(code, name, customer, due, prio, manager, asms):
            pid = projects.save_project(con, uid["admin"], {
                "code": code, "name": f"{name} (PAVYZDYS)", "customer": customer, "due_date": due,
                "priority": prio, "manager_id": uid[manager]})
            con.execute("UPDATE projects SET sample=1 WHERE id=?", (pid,))
            ids = {}
            for acode, aname, qty, *req in asms:
                ids[acode] = projects.save_assembly(con, uid["admin"], pid, {"code": acode, "name": aname, "qty": qty,
                                                                             "requires": req[0] if req else ""})
            return pid, ids

        def phase(pid, asm, kind, owner, s, e):
            return projects.save_phase(con, uid["admin"], pid, {"assembly_id": asm, "kind": kind,
                                                                "owner_id": uid[owner], "plan_start": d(s), "plan_end": d(e)})

        def task(pid, asm, centre, seq, name, qty=1, norm=0, drw="", rev=""):
            return tasks.create_task(con, uid["admin"], {
                "project_id": pid, "assembly_id": asm, "centre_id": cid[centre], "seq": seq, "name": name,
                "qty_plan": qty, "norm_min": norm, "drawing_no": drw, "drawing_rev": rev})

        # --- P-24117: vykdomas, dalis darbų atlikta ---
        p1, a1 = project("P-24117", "Konvejerio linija K-12", "UAB Pavyzdinė gamyba", d(30), 1, "vadovas",
                         [("100", "Rėmas", 1), ("200", "Konvejeris", 2), ("300", "Elektros spinta", 1),
                          ("900", "Galutinis surinkimas", 1, "100,200,300")])
        ph = {}
        ph["p100"] = phase(p1, a1["100"], "projektavimas", "vadovas", -18, -12)
        ph["t100"] = phase(p1, a1["100"], "technologija", "technologas", -12, -9)
        phase(p1, a1["100"], "gamyba", "meistras", -6, 4)
        ph["p200"] = phase(p1, a1["200"], "projektavimas", "vadovas", -16, -8)
        phase(p1, a1["200"], "komponentai", "planuotojas", -8, 6)
        phase(p1, a1["200"], "gamyba", "meistras", -3, 8)
        ph["p300"] = phase(p1, a1["300"], "projektavimas", "vadovas", -15, -6)
        phase(p1, a1["300"], "komponentai", "planuotojas", -6, 10)
        phase(p1, None, "surinkimas", "meistras", 9, 18)
        phase(p1, None, "programavimas", "vadovas", 6, 20)
        phase(p1, None, "testavimas", "kokybe", 20, 26)

        r10 = task(p1, a1["100"], "LAZ-01", 10, "Lakštų detalių pjovimas", 1, 45, "1023-100", "A")
        r20 = task(p1, a1["100"], "LNK-01", 20, "Lenkimas", 1, 60, "1023-100", "A")
        r30 = task(p1, a1["100"], "SV-01", 30, "Rėmo suvirinimas", 1, 240, "1023-100", "A")
        task(p1, a1["100"], "DAZ-01", 40, "Dažymas RAL 7035", 1, 90, "1023-100", "A")
        k10 = task(p1, a1["200"], "LAZ-01", 10, "Šoninių plokščių pjovimas", 2, 20, "1023-200", "C")
        k20 = task(p1, a1["200"], "LNK-01", 20, "Šonų lenkimas", 2, 25, "1023-200", "C")
        task(p1, a1["200"], "MECH-01", 30, "Velenų tekinimas", 4, 35, "1023-200", "C")
        task(p1, a1["200"], "SV-02", 40, "Konvejerio rėmo suvirinimas", 2, 150, "1023-200", "C")
        task(p1, a1["200"], "DAZ-01", 50, "Dažymas RAL 5010", 2, 60, "1023-200", "C")
        task(p1, a1["300"], "EL-01", 10, "Spintos montavimas", 1, 480)
        task(p1, a1["900"], "SUR-01", 10, "Linijos mechaninis surinkimas", 1, 960, "1023-900", "A")
        task(p1, a1["900"], "EL-01", 20, "Elektros sujungimai", 1, 480, "1023-900", "A")
        task(p1, a1["900"], "TST-01", 30, "Funkcinis testas, FAT", 1, 240, "1023-900", "A")

        # --- P-24121: dar neprasidėjęs gamyboje, eilė DAZ-01 nepatvirtinta ---
        p2, a2 = project("P-24121", "Suvirinimo robotų celė RC-3", "AB Pavyzdys LT", d(55), 2, "vadovas",
                         [("100", "Apsauginė tvora", 6), ("200", "Pozicionierius", 1)])
        phase(p2, a2["100"], "projektavimas", "vadovas", -10, -2)
        phase(p2, a2["100"], "gamyba", "meistras", 2, 14)
        phase(p2, a2["200"], "projektavimas", "vadovas", -6, 5)
        phase(p2, a2["200"], "komponentai", "planuotojas", 5, 25)
        phase(p2, None, "programavimas", "vadovas", 20, 40)
        phase(p2, None, "testavimas", "kokybe", 40, 48)
        task(p2, a2["100"], "PLZ-01", 10, "Tvoros stulpų pjovimas", 6, 15, "2210-100", "B")
        task(p2, a2["100"], "SV-02", 20, "Tvoros sekcijų suvirinimas", 6, 70, "2210-100", "B")
        task(p2, a2["100"], "DAZ-01", 30, "Dažymas RAL 1023", 6, 30, "2210-100", "B")

        # --- P-24130: tik krepšelyje ---
        p3, a3 = project("P-24130", "Talpų stovai TS-8", "UAB Pavyzdys", d(80), 3, "vadovas",
                         [("100", "Stovas", 8)])
        phase(p3, a3["100"], "projektavimas", "vadovas", 3, 15)
        phase(p3, a3["100"], "gamyba", "meistras", 20, 35)

        for code, c in cid.items():
            if code != "DAZ-01":
                tasks.approve_queue(con, uid["planuotojas"], c)
        # DAZ-01: patvirtinamos tik P-24117 užduotys
        con.execute("UPDATE tasks SET approved=1 WHERE centre_id=? AND project_id=?", (cid["DAZ-01"], p1))

        # --- istorija: atlikti etapai ir darbai ---
        for key, s, e in [("p100", -18, -12), ("t100", -12, -9), ("p200", -16, -9), ("p300", -15, -5)]:
            at(today + timedelta(days=s, hours=-3)); projects.set_phase_status(con, uid["vadovas"], ph[key], "vykdoma")
            at(today + timedelta(days=e, hours=-2)); projects.set_phase_status(con, uid["vadovas"], ph[key], "baigta")

        op1 = db.row(con.execute("SELECT * FROM users WHERE login='op1'"))
        op2 = db.row(con.execute("SELECT * FROM users WHERE login='op2'"))
        op3 = db.row(con.execute("SELECT * FROM users WHERE login='op3'"))
        day2 = (today - timedelta(days=2)).replace(hour=6, minute=0, second=0)
        at(day2); tasks.start(con, op1, r10)
        at(day2 + timedelta(minutes=52)); tasks.stop(con, op1, r10, 1)
        at(day2 + timedelta(minutes=60)); tasks.start(con, op1, k10)
        at(day2 + timedelta(minutes=105)); tasks.stop(con, op1, k10, 2)
        at(day2 + timedelta(hours=3)); tasks.start(con, op2, r20)
        at(day2 + timedelta(hours=3, minutes=40)); tasks.pause(con, op2, r20, "irankiai", "Matricos keitimas")
        at(day2 + timedelta(hours=4, minutes=10)); tasks.resume(con, op2, r20)
        at(day2 + timedelta(hours=4, minutes=55)); tasks.stop(con, op2, r20, 1)
        day1 = (today - timedelta(days=1)).replace(hour=6, minute=30, second=0)
        at(day1); tasks.start(con, op3, r30)
        at(day1 + timedelta(hours=4)); tasks.pause(con, op3, r30, "pamaina")
        at(today - timedelta(hours=2)); tasks.resume(con, op3, r30)
        at(today - timedelta(hours=1, minutes=10)); tasks.start(con, op2, k20)
        at(today - timedelta(minutes=35)); tasks.pause(con, op2, k20, "medziaga", "Trūksta 3 mm lakšto")

        # --- komponentų pirkimai: gauta, dalinai, vėluoja, neužsakyta ---
        at(today - timedelta(days=14))
        P = uid["pirkimai"]

        def comp(pid, asm, item, name, spec, qty, unit, sup, po, line, ordered, promised, need):
            return components.save(con, P, {
                "project_id": pid, "assembly_id": asm, "item_no": item, "name": name, "spec": spec, "qty": qty,
                "unit": unit, "supplier": sup, "po_no": po, "po_line": line,
                "ordered_date": d(ordered) if ordered is not None else None,
                "promised_date": d(promised) if promised is not None else None,
                "need_date": d(need) if need is not None else None})

        c_mot = comp(p1, a1["200"], "EL-MOT-075", "Motoreduktorius 0,75 kW", "SEW KA37 DRN80, i=28", 2, "vnt",
                     "UAB Pavaros (PAVYZDYS)", "PO-26-0412", "1", -14, -3, 4)
        c_brg = comp(p1, a1["200"], "MECH-UCF205", "Guolių mazgas UCF205", "SKF arba analogas", 8, "vnt",
                     "UAB Guoliai (PAVYZDYS)", "PO-26-0413", "1", -14, -6, 2)
        comp(p1, a1["200"], "MECH-BELT-500", "Konvejerio juosta 500 mm", "PVC, žalia, 2 sl., 11,4 m", 2, "vnt",
             "UAB Juostos (PAVYZDYS)", "PO-26-0414", "1", -12, -1, 5)
        c_plc = comp(p1, a1["300"], "EL-PLC-1512", "PLC Siemens S7-1500", "CPU 1512C-1 PN", 1, "vnt",
                     "UAB Automatika (PAVYZDYS)", "PO-26-0420", "1", -13, -4, 3)
        comp(p1, a1["300"], "EL-HMI-07", "Operatoriaus pultas HMI 7\"", "Siemens TP700 Comfort", 1, "vnt",
             "UAB Automatika (PAVYZDYS)", "PO-26-0420", "2", -13, 12, 5)
        c_cnt = comp(p1, a1["300"], "EL-CONT-9A", "Kontaktorius 9 A", "3RT2016, 24 V DC", 12, "vnt",
                     "UAB Automatika (PAVYZDYS)", "PO-26-0420", "3", -13, -6, 3)
        comp(p1, a1["300"], "EL-ENC-1000", "Elektros spinta 1000×800×300", "Rittal AX", 1, "vnt",
             "UAB Spintos (PAVYZDYS)", "PO-26-0425", "1", -10, None, 2)
        comp(p1, a1["900"], "SNS-IND-M18", "Induktyvus jutiklis M18", "PNP, 8 mm", 10, "vnt",
             "", "", "", None, None, 6)
        comp(p2, a2["200"], "ROB-6AX-20", "Pramoninis robotas, 6 ašių", "20 kg, 1800 mm sieksnis", 1, "vnt",
             "UAB Robotai (PAVYZDYS)", "PO-26-0431", "1", -6, 28, 25)
        comp(p2, a2["100"], "SAF-DOOR-SW", "Apsauginių durų jungiklis", "su užraktu, PL d", 2, "vnt",
             "", "", "", None, None, 10)
        for cid_, q, days in [(c_brg, 8, -6), (c_cnt, 12, -5), (c_mot, 1, -3), (c_plc, 1, -2)]:
            when = (today + timedelta(days=days)).replace(hour=10, minute=0, second=0)
            at(when)
            components.receive(con, uid["sandelis"], cid_, q, when=when.isoformat(timespec="seconds"))

        # nauja brėžinio revizija po užduočių sukūrimo – dažymo užduotis bus užrakinta
        at(today - timedelta(hours=5))
        drawings.save(con, files_dir, admin, "1023-100", "B", "1023-100_B.pdf",
                      drawings.sample_pdf(["PAVYZDYS  1023-100  rev. B", "Rėmas R-1200",
                                           "Pakeista: tvirtinimo skyles"]), "Rėmas R-1200")
        con.execute("UPDATE tasks SET drawing_rev='B' WHERE id IN (?,?,?)", (r10, r20, r30))
    finally:
        db.set_clock(real_clock)
    con.commit()
