"""Pavyzdiniai duomenys testinei aplinkai.

Projektai pažymėti `sample=1` ir pavadinimuose turi žymę PAVYZDYS – kad niekas
jų nepalaikytų tikrais. Dalis darbų „atlikta“ praeityje (laikrodis
perstatomas), kad cecho būsena ir analitika iškart turėtų ką rodyti.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from .. import db
from . import actions, auth, capacity, components, demo, drawings, meetings, ncfiles, projects, quality, routing, tasks

TEST_PASSWORD = "vmgt2026"

USERS = [
    # login, vardas, rolė, PIN, centrai
    ("admin", "Administratorius", "admin", None, []),
    ("vadovas", "Rasa Vadovienė", "vadovas", None, []),
    ("planuotojas", "Tomas Planas", "planuotojas", None, []),
    ("technologas", "Ieva Technologė", "technologas", None, []),
    ("meistras", "Andrius Meistras", "meistras", "9999", ["MAB", "TKB", "SVB"]),
    ("meistras2", "Vytautas Meistras", "meistras", "8888", ["DZB", "ATB", "TIS"]),
    ("kokybe", "Laura Kokybė", "kokybe", None, []),
    ("pirkimai", "Eglė Pirkėja", "pirkimai", None, []),
    ("sandelis", "Paulius Sandėlis", "sandelis", "5555", []),
    ("op1", "Jonas Petraitis", "operatorius", "1111", []),
    ("op2", "Marius Kazlauskas", "operatorius", "2222", []),
    ("op3", "Darius Suvirintojas", "operatorius", "3333", ["SVB"]),
]

# Gamybos barai ir jų darbo centrai (vartotojo aprašymas 2026-10-25). Stočių
# pavadinimai – pavyzdiniai, tikrus įveda administratorius.
AREAS = [
    ("MAB", "Mechaninio apdirbimo baras", "meistras", [
        ("PJV-01", "Juostinis pjūklas", "pjovimas", 0),
        ("LAZ-01", "Lazeris", "pjovimas", 0),
        ("PLZ-01", "Plazma", "pjovimas", 0),
        ("LNK-01", "Lenkimo presas", "lenkimas", 0)]),
    ("TKB", "Tekinimo baras", "meistras", [
        ("TEK-01", "Universalios tekinimo staklės 1", "tekinimas", 0),
        ("TEK-02", "Universalios tekinimo staklės 2", "tekinimas", 0),
        ("CNC-01", "CNC tekinimo staklės", "tekinimas", 0),
        ("MECH-01", "CNC frezavimo centras", "mechaninis", 0)]),
    ("SVB", "Suvirinimo baras", "meistras", [
        (f"SV-{i:02d}", f"Surinkimo ir suvirinimo stotis {i}", "suvirinimas", 1) for i in range(1, 11)]),
    ("DZB", "Dažymo baras", "meistras2", [
        ("SML-01", "Smėliavimas", "pavirsius", 1),
        ("DAZ-01", "Šlapias dažymas", "dazymas", 1),
        ("DAZ-02", "Miltelinis dažymas", "dazymas", 1)]),
    ("ATB", "Automatikos baras", "meistras2", [
        ("EL-01", "Elektros spintų surinkimas", "elektra", 1),
        ("PRG-01", "Programavimas ir derinimas", "programavimas", 1)]),
    ("TIS", "Technologinių įrenginių surinkimo baras", "meistras2", [
        ("SUR-01", "Mechaninis surinkimas", "surinkimas", 1),
        ("TST-01", "Testavimas", "testavimas", 1)]),
]


def is_empty(con) -> bool:
    return con.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0


# staklės, kurioms technologas turi pridėti programą / DXF (`needs_files`)
NC_CENTRES = {"LAZ-01", "PLZ-01", "LNK-01", "CNC-01", "MECH-01", "PRG-01"}


def _dxf(title: str, w: int, h: int) -> bytes:
    """Mažiausias galiojantis DXF: stačiakampė išklotinė su skyle – pavyzdžiui."""
    pts = [(0, 0), (w, 0), (w, h), (0, h)]
    ents = ["0", "LWPOLYLINE", "8", "KONTURAS", "90", "4", "70", "1"]
    for x, y in pts:
        ents += ["10", str(x), "20", str(y)]
    ents += ["0", "CIRCLE", "8", "SKYLES", "10", str(w // 2), "20", str(h // 2), "40", "11",
             "0", "TEXT", "8", "ZYMES", "10", "5", "20", str(h + 5), "40", "5", "1", title]
    return ("\n".join(["0", "SECTION", "2", "ENTITIES", *ents, "0", "ENDSEC", "0", "EOF"]) + "\n").encode()


def _text(*lines: str) -> bytes:
    return ("\n".join(lines) + "\n").encode()


def seed(con, files_dir: Path, today: datetime | None = None, nc_dir: Path | None = None, demo_projects=True) -> None:
    nc_dir = nc_dir or files_dir.parent / "nc"
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
        # biuro skyriai: kurių etapų darbą dirba ir kiek žmonių (pavyzdiniai skaičiai)
        for code, name, kinds, people in [("PROJ", "Projektavimo skyrius", "projektavimas", 3),
                                          ("TECH", "Technologijų skyrius", "technologija", 2),
                                          ("PIRK", "Pirkimų skyrius", "komponentai", 1),
                                          ("PROG", "Automatikos ir programavimo skyrius", "programavimas", 2),
                                          ("TEST", "Testavimo grupė", "testavimas", 1)]:
            capacity.save_department(con, None, {"code": code, "name": name, "kind": "office",
                                                 "phase_kinds": kinds, "headcount": people})
        area_people = {"MAB": 4, "TKB": 3, "SVB": 8, "DZB": 3, "ATB": 3, "TIS": 4}
        for acode, aname, master, centres in AREAS:
            aid = projects.save_area(con, None, {"code": acode, "name": aname, "master_id": uid[master]})
            capacity.save_department(con, None, {"code": acode, "name": aname, "kind": "production", "area_id": aid,
                                                 "headcount": area_people[acode]})
            for code, name, kind, manual in centres:
                cid[code] = projects.save_centre(con, None, {"code": code, "name": name, "kind": kind,
                                                             "manual": manual, "area_id": aid,
                                                             "needs_files": int(code in NC_CENTRES)})
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

        dept = {r["code"]: r["id"] for r in capacity.list_departments(con)}

        def phase(pid, asm, kind, owner, s, e, hours=None, dep=None):
            return projects.save_phase(con, uid["admin"], pid, {"assembly_id": asm, "kind": kind, "owner_id": uid[owner],
                                                                "plan_start": d(s), "plan_end": d(e), "hours": hours,
                                                                "department_id": dept[dep] if dep else None})

        def task(pid, asm, centre, seq, name, qty=1, norm=0, drw="", rev="", part=""):
            # part – detalės atšaka; be jos – mazgo operacija (detalės čia susilieja)
            return tasks.create_task(con, uid["admin"], {
                "project_id": pid, "assembly_id": asm, "centre_id": cid[centre], "seq": seq, "name": name,
                "qty_plan": qty, "norm_min": norm, "drawing_no": drw, "drawing_rev": rev, "part_no": part})

        # --- P-24117: vykdomas, dalis darbų atlikta ---
        p1, a1 = project("P-24117", "Konvejerio linija K-12", "UAB Pavyzdinė gamyba", d(30), 1, "vadovas",
                         [("100", "Rėmas", 1), ("200", "Konvejeris", 2), ("300", "Elektros spinta", 1),
                          ("900", "Galutinis surinkimas", 1, "100,200,300")])
        ph = {}
        ph["p100"] = phase(p1, a1["100"], "projektavimas", "vadovas", -18, -12, 80)
        ph["t100"] = phase(p1, a1["100"], "technologija", "technologas", -12, -9, 24)
        phase(p1, a1["100"], "gamyba", "meistras", -6, 4)
        ph["p200"] = phase(p1, a1["200"], "projektavimas", "vadovas", -16, -8, 120)
        phase(p1, a1["200"], "komponentai", "planuotojas", -8, 6, 30)
        phase(p1, a1["200"], "gamyba", "meistras", -3, 8)
        ph["p300"] = phase(p1, a1["300"], "projektavimas", "vadovas", -15, -6, 90)
        phase(p1, a1["300"], "komponentai", "planuotojas", -6, 10, 24)
        phase(p1, None, "surinkimas", "meistras", 9, 18)
        phase(p1, None, "programavimas", "vadovas", 6, 20, 160)
        phase(p1, None, "testavimas", "kokybe", 20, 26, 60)

        r10 = task(p1, a1["100"], "LAZ-01", 10, "Lakštų detalių pjovimas", 1, 45, "1023-100", "A", "1023-101")
        r20 = task(p1, a1["100"], "LNK-01", 20, "Lenkimas", 1, 60, "1023-100", "A", "1023-101")
        r30 = task(p1, a1["100"], "SV-01", 30, "Rėmo suvirinimas", 1, 240, "1023-100", "A")
        task(p1, a1["100"], "SML-01", 35, "Smėliavimas Sa 2,5", 1, 40, "1023-100", "A")
        task(p1, a1["100"], "DAZ-01", 40, "Dažymas RAL 7035", 1, 90, "1023-100", "A")
        k10 = task(p1, a1["200"], "LAZ-01", 10, "Šoninių plokščių pjovimas", 2, 20, "1023-200", "C", "1023-201")
        k20 = task(p1, a1["200"], "LNK-01", 20, "Šonų lenkimas", 2, 25, "1023-200", "C", "1023-201")
        k30 = task(p1, a1["200"], "CNC-01", 30, "Velenų tekinimas", 4, 35, "1023-200", "C", "1023-210")
        task(p1, a1["200"], "SV-02", 40, "Konvejerio rėmo suvirinimas", 2, 150, "1023-200", "C")
        task(p1, a1["200"], "DAZ-02", 50, "Miltelinis dažymas RAL 5010", 2, 60, "1023-200", "C")
        task(p1, a1["300"], "EL-01", 10, "Spintos montavimas", 1, 480)
        task(p1, a1["900"], "SUR-01", 10, "Linijos mechaninis surinkimas", 1, 960, "1023-900", "A")
        task(p1, a1["900"], "EL-01", 20, "Elektros sujungimai", 1, 480, "1023-900", "A")
        prg = task(p1, a1["900"], "PRG-01", 25, "PLC ir robotų programų derinimas", 1, 600, "1023-900", "A")
        task(p1, a1["900"], "TST-01", 30, "Funkcinis testas, FAT", 1, 240, "1023-900", "A")

        # --- P-24121: dar neprasidėjęs gamyboje, eilė DAZ-01 nepatvirtinta ---
        p2, a2 = project("P-24121", "Suvirinimo robotų celė RC-3", "AB Pavyzdys LT", d(55), 2, "vadovas",
                         [("100", "Apsauginė tvora", 6), ("200", "Pozicionierius", 1)])
        phase(p2, a2["100"], "projektavimas", "vadovas", -10, -2, 60)
        phase(p2, a2["100"], "gamyba", "meistras", 2, 14)
        phase(p2, a2["200"], "projektavimas", "vadovas", -6, 5, 220)
        phase(p2, a2["200"], "komponentai", "planuotojas", 5, 25, 40)
        phase(p2, a2["200"], "gamyba", "meistras", 18, 32, 320, "SVB")
        phase(p2, None, "surinkimas", "meistras", 30, 40, 260, "TIS")
        phase(p2, None, "programavimas", "vadovas", 20, 40, 300)
        phase(p2, None, "testavimas", "kokybe", 40, 48, 80)
        plz = task(p2, a2["100"], "PLZ-01", 10, "Tvoros stulpų pjovimas", 6, 15, "2210-100", "B")
        task(p2, a2["100"], "SV-02", 20, "Tvoros sekcijų suvirinimas", 6, 70, "2210-100", "B")
        task(p2, a2["100"], "DAZ-01", 30, "Dažymas RAL 1023", 6, 30, "2210-100", "B")
        # pozicionieriaus maršrutas – technologo juodraštis, dar neišleistas
        task(p2, a2["200"], "TEK-01", 10, "Ašies tekinimas", 1, 120, "2210-200", "A", "2210-201")
        poz_laz = task(p2, a2["200"], "LAZ-01", 10, "Plokščių pjovimas", 4, 12, "2210-200", "A", "2210-202")
        task(p2, a2["200"], "LNK-01", 20, "Plokščių lenkimas", 4, 15, "2210-200", "A", "2210-202")
        task(p2, a2["200"], "SV-03", 30, "Pozicionieriaus suvirinimas", 1, 360, "2210-200", "A")
        task(p2, a2["200"], "DAZ-02", 40, "Miltelinis dažymas RAL 9005", 1, 60, "2210-200", "A")

        # --- P-24130: tik krepšelyje ---
        p3, a3 = project("P-24130", "Talpų stovai TS-8", "UAB Pavyzdys", d(80), 3, "vadovas",
                         [("100", "Stovas", 8)])
        phase(p3, a3["100"], "projektavimas", "vadovas", 3, 15, 180)
        phase(p3, a3["100"], "technologija", "technologas", 14, 20, 60)
        phase(p3, a3["100"], "gamyba", "meistras", 20, 35, 700, "SVB")
        phase(p3, a3["100"], "gamyba", "meistras", 33, 40, 160, "DZB")

        # technologo failai – prieš išleidimą: staklėms be programos maršruto
        # išleisti negalima. P-24121 200 lenkimui failo sąmoningai nėra
        tech = {"id": uid["technologas"]}
        for t_id, name, content in [
                (r10, "1023-101.dxf", _dxf("1023-101 S355 t6", 1200, 400)),
                (r10, "1023-101_lakstas.nc", _text("%", "O1023 (LAKSTAS 3000x1500 S355 t6)", "G90 G21", "M30", "%")),
                (r20, "1023-101_lenkimas.nc", _text("; LENKIMAS 1023-101", "; 4 lenkimai, V16", "M30")),
                (k10, "1023-201.dxf", _dxf("1023-201 S235 t3", 900, 300)),
                (k20, "1023-201_lenkimas.nc", _text("; LENKIMAS 1023-201", "; 2 lenkimai, V12", "M30")),
                (k30, "1023-210_velenas.mpf", _text("; VELENAS D40 L860", "G54", "M30")),
                (prg, "K12_linija.scl", _text("FUNCTION_BLOCK FB_Konvejeris", "END_FUNCTION_BLOCK")),
                (prg, "K12_paletes.mod", _text("MODULE Paletes", "ENDMODULE")),
                (plz, "2210-101_stulpas.dxf", _dxf("2210-101 stulpas", 60, 1800)),
                (poz_laz, "2210-202.dxf", _dxf("2210-202 plokste", 400, 400))]:
            ncfiles.save(con, nc_dir, tech, t_id, name, content)
        for a in (a1["100"], a1["200"], a1["300"], a1["900"], a2["100"]):
            routing.release(con, uid["technologas"], a)
        for code, c in cid.items():
            if code != "DAZ-01":
                tasks.approve_queue(con, uid["planuotojas"], c)
        # DAZ-01: patvirtinamos tik P-24117 užduotys
        con.execute("UPDATE tasks SET approved=1 WHERE centre_id=? AND project_id=?", (cid["DAZ-01"], p1))

        # penki pavyzdiniai projektai su visu technologiniu keliu ir istorija
        # (`demo.py`) – prieš pagrindinių pavyzdžių paskutines dienas, nes šie
        # užima LAZ-01, LNK-01 ir SV-01 iki dabar
        if demo_projects:
            demo.run(con, uid, cid, today, files_dir, nc_dir)

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

        # --- projekto valdymas: susitikimai, iš jų kilę veiksmai, užduočių eiga ---
        U = lambda login: db.row(con.execute("SELECT * FROM users WHERE login=?", (login,)))
        vad = U("vadovas")
        mt = lambda days, h: (today + timedelta(days=days)).replace(hour=h, minute=0, second=0)
        at(mt(-14, 9))
        m1 = meetings.save(con, vad, {
            "project_id": p1, "title": "Projekto pradžios susitikimas", "held_at": mt(-14, 9).isoformat(timespec="minutes"),
            "location": "Pasitarimų kambarys 2", "chair_id": uid["vadovas"],
            "attendees": [uid["vadovas"], uid["technologas"], uid["pirkimai"], uid["meistras"], uid["meistras2"]],
            "guests": "J. Užsakovas (UAB Pavyzdinė gamyba)",
            "agenda": "1. Projekto apimtis ir terminai\n2. Ilgo pristatymo komponentai\n3. Gamybos pradžia",
            "notes": "Užsakovas patvirtino linijos išdėstymą. Motoreduktorių pristatymas – 10–14 d.",
            "decisions": "Galutinis terminas – pagal sutartį, be pakeitimų\nPLC ir HMI užsakyti iš UAB Automatika\n"
                         "Mazgo 100 gamyba pradedama, kai išleisti brėžiniai rev. A",
            "new_actions": [
                {"title": "Užsakyti ilgo pristatymo komponentus (motoreduktoriai, PLC, HMI)", "owner_id": uid["pirkimai"],
                 "due_date": d(-12), "priority": 1},
                {"title": "Išleisti mazgo 100 brėžinius gamybai", "owner_id": uid["technologas"], "due_date": d(-11), "priority": 1},
                {"title": "Suderinti elektros schemą su užsakovu", "owner_id": uid["vadovas"], "due_date": d(-4), "priority": 2},
                {"title": "Parengti FAT programą", "owner_id": uid["kokybe"], "due_date": d(12), "priority": 2},
            ]}, )
        meetings.approve(con, vad, m1)
        acts = {x["title"]: x["id"] for x in actions.list_actions(con, meeting_id=m1)}
        A = lambda key: next(v for k, v in acts.items() if k.startswith(key))
        def st(key, status, who, days, h, reason=""):
            at(mt(days, h)); actions.set_status(con, U(who), A(key), status, reason)
        st("Užsakyti ilgo pristat", "vykdoma", "pirkimai", -14, 13); st("Užsakyti ilgo pristat", "atlikta", "pirkimai", -12, 15)
        st("Išleisti mazgo 100 br", "vykdoma", "technologas", -13, 8); st("Išleisti mazgo 100 br", "perziura", "technologas", -11, 16)
        st("Išleisti mazgo 100 br", "atlikta", "vadovas", -10, 9)
        st("Suderinti elektros sc", "vykdoma", "vadovas", -9, 10)
        st("Suderinti elektros sc", "laukia", "vadovas", -6, 11, "Laukiama užsakovo atsakymo dėl avarinio stabdymo grandinės")
        at(mt(-5, 14)); actions.comment(con, vad, A("Suderinti elektros"), "Priminta užsakovui el. paštu")

        at(mt(-3, 9))
        m2 = meetings.save(con, vad, {
            "project_id": p1, "title": "Savaitinis projekto susitikimas", "held_at": mt(-3, 9).isoformat(timespec="minutes"),
            "location": "Cechas, DC biuras", "chair_id": uid["vadovas"],
            "attendees": [uid["vadovas"], uid["meistras"], uid["meistras2"], uid["pirkimai"], uid["kokybe"]],
            "agenda": "1. Ankstesnių veiksmų peržiūra\n2. Gamybos eiga\n3. Komponentų vėlavimai",
            "notes": "Lenkimui trūksta 3 mm lakšto. Juostos tiekėjas vėluoja. HMI pristatymas vėlesnis nei reikia.",
            "decisions": "Lakštą pirkti iš atsarginio tiekėjo\nHMI – ieškoti alternatyvos su greitesniu pristatymu",
            "new_actions": [
                {"title": "Nupirkti 3 mm lakštą iš atsarginio tiekėjo", "owner_id": uid["pirkimai"], "due_date": d(-1), "priority": 1},
                {"title": "Rasti HMI alternatyvą su pristatymu iki termino", "owner_id": uid["pirkimai"], "due_date": d(2), "priority": 1},
                {"title": "Patikrinti suvirinimo siūles mazge 100", "owner_id": uid["kokybe"], "due_date": d(1), "priority": 2},
            ]})
        acts.update({x["title"]: x["id"] for x in actions.list_actions(con, meeting_id=m2)})
        st("Rasti HMI alternatyv", "vykdoma", "pirkimai", -2, 10)
        at(mt(-2, 9))
        actions.create(con, uid["vadovas"], {"project_id": p1, "title": "Atnaujinti projekto planą užsakovui",
                                             "owner_id": uid["vadovas"], "due_date": d(3), "priority": 3})
        at(mt(-1, 9))
        meetings.save(con, vad, {"project_id": p2, "title": "Robotų celės techninis susitikimas",
                                 "held_at": mt(-1, 9).isoformat(timespec="minutes"), "chair_id": uid["vadovas"],
                                 "attendees": [uid["vadovas"], uid["technologas"]],
                                 "agenda": "Roboto modelio pasirinkimas, apsaugų išdėstymas",
                                 "new_actions": [{"title": "Parengti apsauginės tvoros brėžinius", "owner_id": uid["technologas"],
                                                  "due_date": d(4), "priority": 2}]})

        # asmeninis darbų planas: užduotys sau (matomos tik savininkui) ir
        # suplanuotos projektų užduotys; vakar neatlikta rodoma šiandien
        for who, title, day, h in [("vadovas", "Paruošti pasiūlymą UAB Pavyzdys (talpų stovai)", 0, 3),
                                   ("vadovas", "Peržiūrėti savaitės ataskaitą direktoriui", -1, 1),
                                   ("vadovas", "Atnaujinti rizikų sąrašą", None, 2),
                                   ("technologas", "Susitvarkyti Lantek lakštų bibliotekas", 1, 4),
                                   ("technologas", "Perskaityti naujų suvirinimo vielų specifikacijas", None, None)]:
            actions.create(con, uid[who], {"title": title, "plan_date": d(day) if day is not None else None,
                                           "estimate_h": h})
        by_title = lambda t: con.execute("SELECT id FROM actions WHERE title LIKE ?", (t + "%",)).fetchone()[0]
        actions.update(con, U("technologas"), by_title("Parengti apsauginės tvoros"), {"plan_date": d(0), "estimate_h": 5})
        actions.update(con, U("vadovas"), by_title("Atnaujinti projekto planą"), {"plan_date": d(2), "estimate_h": 2})

        # nauja brėžinio revizija po užduočių sukūrimo – dažymo užduotis bus užrakinta
        at(today - timedelta(hours=5))
        drawings.save(con, files_dir, admin, "1023-100", "B", "1023-100_B.pdf",
                      drawings.sample_pdf(["PAVYZDYS  1023-100  rev. B", "Rėmas R-1200",
                                           "Pakeista: tvirtinimo skyles"]), "Rėmas R-1200")
        con.execute("UPDATE tasks SET drawing_rev='B' WHERE id IN (?,?,?)", (r10, r20, r30))
        # technologas pataisė plazmos programą jau išleidus – PLZ-01 laukia meistro patvirtinimo
        at(today - timedelta(hours=3))
        ncfiles.save(con, nc_dir, tech, plz, "2210-101_stulpas.dxf", _dxf("2210-101 stulpas, skyles D13", 60, 1800),
                     "Pakeistas tvirtinimo skylių skersmuo")
        _quality(con, uid, files_dir, today, at)
    finally:
        db.set_clock(real_clock)
    con.commit()


def _quality(con, uid, files_dir, today, at) -> None:
    """Kokybė (EN 1090): šablonai, WPS, kvalifikacijos, lydiniai su sertifikatais,
    vykdymo klasės ir patikros. Kuriama PO istorijos: praeities darbai buvo
    atlikti be šių taisyklių, o jų medžiagos ir WPS įrašomi atgaline data –
    kaip įvedus duomenis iš popierinių žurnalų."""
    U = lambda login: db.row(con.execute("SELECT * FROM users WHERE login=?", (login,)))
    kok, tech = U("kokybe"), uid["technologas"]
    pdf = lambda *lines: drawings.sample_pdf(["PAVYZDYS", *lines])
    at(today - timedelta(days=120))
    tpl = {}
    for code, name, kind, nom, lo, hi, unit, perf, instr in [
            ("VT-SIUL", "Suvirinimo siūlių vizuali kontrolė (EN ISO 5817 C)", "check", None, None, None, "", "qc",
             "100 % siūlių, EN ISO 17637; porų, įtrūkimų, nepravirinimų nėra"),
            ("PJV-KOK", "Pjūvio kokybė (EN ISO 9013)", "check", None, None, None, "", "operator",
             "Šlakas, kraštų nuožula, oksidacija – lyginti su pavyzdžiu"),
            ("LNK-KAMP", "Lenkimo kampas", "measure", 90, 1, 1, "°", "operator", "Kampamačiu, pirma ir paskutinė detalė"),
            ("MAT-ISTR", "Įstrižainių skirtumas", "measure", 0, 0, 3, "mm", "operator", "Matuoti ruletė, po suvirinimo"),
            ("TEK-D40", "Veleno skersmuo Ø40 h7", "measure", 40, 0.025, 0, "mm", "operator", "Mikrometru, prieš nuimant detalę"),
            ("DAZ-STOR", "Dangos storis", "measure", 80, 0, 40, "µm", "qc", "Storio matuokliu, 5 vietos, mažiausia reikšmė"),
            ("FAT", "Funkcinis bandymas pagal FAT programą", "check", None, None, None, "", "qc", "Užsakovo dalyvavimas")]:
        tpl[code] = quality.save_template(con, tech, {"code": code, "name": name, "kind": kind, "nominal": nom,
                                                      "tol_minus": lo, "tol_plus": hi, "unit": unit, "performer": perf,
                                                      "instruction": instr})
    wps = {}
    for code, proc, grp, desc in [("WPS-135-01", "135", "1.1", "MAG, S235–S355 lakštai ir profiliai, t 3–20"),
                                  ("WPS-135-02", "135", "1.2", "MAG, S355 storasieniai t 20–60, pašildymas 100 °C"),
                                  ("WPS-141-01", "141", "8.1", "TIG, AISI 304/316, maisto pramonė, apsauga iš vidaus")]:
        wps[code] = quality.save_wps(con, files_dir, tech, {"code": code, "process": proc, "material_group": grp,
                                                            "description": desc}, pdf(code, desc))
    plus = lambda n: (today + timedelta(days=n)).date().isoformat()
    for login, proc, grp, valid, cert in [("suv1", "135", "1.1", 300, "LT-9606-1123"), ("suv1", "135", "1.2", 300, "LT-9606-1124"),
                                          ("suv1", "141", "8.1", 20, "LT-9606-1187"), ("op3", "135", "1.1", -15, "LT-9606-0871"),
                                          ("op3", "135", "1.2", -15, "LT-9606-0872")]:
        if login not in uid:                     # demo operatoriai kuriami tik su demo projektais
            continue
        quality.save_qualification(con, files_dir, uid["admin"], {
            "user_id": uid[login], "process": proc, "material_group": grp, "valid_until": plus(valid),
            "standard": "ISO 9606-1", "cert_no": cert}, pdf("ISO 9606-1", cert, f"{proc} {grp}"))
    lots = {}
    for heat, mat, prod, sup, cert in [("H-48213", "S355J2+N", "lakštas t10 3000×1500", "UAB Metalo prekyba", "MP-26-3311"),
                                       ("H-55190", "S355J2+N", "lakštas t6 3000×1500", "UAB Metalo prekyba", "MP-26-3312"),
                                       ("H-77102", "S235JR", "lakštas t3 2500×1250", "UAB Metalo prekyba", "MP-26-3290"),
                                       ("H-31877", "S235JR", "vamzdis 100×100×5", "UAB Profiliai", "PR-8812"),
                                       ("H-62440", "S355J2+N", "lakštas t40 2000×1000", "UAB Metalo prekyba", "MP-26-3420"),
                                       ("H-90311", "AISI 304", "lakštas t4 2000×1000", "UAB Nerūdijantis", "NR-5521"),
                                       ("H-60014", "S235JR", "lakštas t40 2000×1000", "UAB Metalo prekyba", "MP-26-3401")]:
        lots[heat] = quality.save_lot(con, files_dir, kok, {"heat_no": heat, "material": mat, "product": prod,
                                                            "supplier": f"{sup} (PAVYZDYS)", "cert_no": cert, "cert_type": "3.1",
                                                            "qty": 10, "unit": "vnt"}, pdf("EN 10204 3.1", cert, heat, mat, prod))
    # P-24108 istorija: sertifikatas neatitiko užsakymo (S235 vietoj S355)
    quality.set_lot_status(con, kok, lots["H-60014"], "blokuota", "Sertifikate S235JR, užsakyta S355J2 – grąžinta tiekėjui")

    exc = {"P-24117": "EXC2", "P-24121": "EXC2", "P-24095": "EXC2", "P-24102": "EXC2", "P-24108": "EXC3",
           "P-24113": "EXC1", "P-24126": "EXC2"}
    for code, cls in exc.items():
        con.execute("UPDATE projects SET exc_class=? WHERE code=?", (cls, code))
    task = lambda code, name: con.execute(
        "SELECT t.id FROM tasks t JOIN projects p ON p.id=t.project_id WHERE p.code=? AND t.name=?", (code, name)).fetchone()
    # praeities pjovimas ir suvirinimas – atgaline data, kaip įvesta iš žurnalų
    for t in db.rows(con.execute(
            "SELECT t.id, p.code, p.exc_class, c.kind, t.name, (SELECT MAX(end) FROM intervals i WHERE i.task_id=t.id) AS ended "
            "FROM tasks t JOIN projects p ON p.id=t.project_id JOIN work_centres c ON c.id=t.centre_id "
            "WHERE t.qty_good > 0")):
        if not quality.traced(t["exc_class"]):
            continue
        if t["kind"] == "pjovimas":
            heat = ("H-90311" if t["code"] == "P-24126" else "H-31877" if "Profil" in t["name"] or "Bėgių" in t["name"]
                    else "H-62440" if "t40" in t["name"] or "t30" in t["name"] or "t60" in t["name"]
                    else "H-77102" if "S235" in t["name"] else "H-48213" if "t10" in t["name"] else "H-55190")
            con.execute("INSERT INTO task_materials (task_id, lot_id, qty, user_id, at) VALUES (?,?,1,?,?)",
                        (t["id"], lots[heat], uid["op1"], t["ended"] or db.now()))
        if t["kind"] == "suvirinimas":
            w = "WPS-141-01" if t["code"] == "P-24126" else "WPS-135-02" if t["code"] == "P-24108" else "WPS-135-01"
            con.execute("UPDATE tasks SET wps_id=? WHERE id=?", (wps[w], t["id"]))
    # dabartiniai darbai: WPS ir patikros, kurias matys terminalas ir kokybės eilė
    at(today - timedelta(hours=6))
    for code, name, wps_code, checks in [
            ("P-24117", "Konvejerio rėmo suvirinimas", "WPS-135-01", ["VT-SIUL", "MAT-ISTR"]),
            ("P-24117", "Šonų lenkimas", None, ["LNK-KAMP"]),
            ("P-24117", "Velenų tekinimas", None, ["TEK-D40"]),
            ("P-24117", "Miltelinis dažymas RAL 5010", None, ["DAZ-STOR"]),
            ("P-24117", "Funkcinis testas, FAT", None, ["FAT"]),
            ("P-24121", "Tvoros sekcijų suvirinimas", "WPS-135-01", ["VT-SIUL"]),
            ("P-24126", "Korpuso suvirinimas (TIG)", "WPS-141-01", ["VT-SIUL"])]:
        t = task(code, name)
        if not t:
            continue
        if wps_code:
            con.execute("UPDATE tasks SET wps_id=? WHERE id=?", (wps[wps_code], t[0]))
        for c in checks:
            if con.execute("SELECT status FROM tasks WHERE id=?", (t[0],)).fetchone()[0] != "baigta":
                quality.add_check(con, tech, t[0], {"template_id": tpl[c]})
    # P-24108 dažyta, bet dangos storis dar neišmatuotas – rėmas sulaikytas kokybės eilėje
    t = task("P-24108", "Dažymas RAL 5010")
    if t:
        con.execute("INSERT INTO task_checks (task_id, template_id, name, kind, unit, nominal, tol_minus, tol_plus, performer, "
                    "instruction, sort) SELECT ?, id, name, kind, unit, nominal, tol_minus, tol_plus, performer, instruction, 1 "
                    "FROM check_templates WHERE code='DAZ-STOR'", (t[0],))
