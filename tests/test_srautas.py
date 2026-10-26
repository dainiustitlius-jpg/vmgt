"""Technologinis srautas: detalių atšakos susilieja į mazgą, išleidimas į
gamybą, kur detalės keliauja po Stop, atsekamumas."""

import pytest
from conftest import login

from vmgt.services import RuleError, auth, importer, projects, routing, tasks


@pytest.fixture
def flow(con, clock):
    """Mazgas 100: detalė A (LAZ → LNK), detalė B (TEK), mazgo operacijos
    SV → DAZ; mazgas 900 laukia 100 (SUR)."""
    admin = auth.create_user(con, "admin", "Admin", "admin", "x")
    op = dict(con.execute("SELECT * FROM users WHERE id=?",
                          (auth.create_user(con, "op", "Op", "operatorius", "x"),)).fetchone())
    c = {k: projects.save_centre(con, admin, {"code": k, "name": k, "kind": kind})
         for k, kind in [("LAZ", "pjovimas"), ("LNK", "lenkimas"), ("TEK", "tekinimas"), ("SV", "suvirinimas"),
                         ("DAZ", "dazymas"), ("SUR", "surinkimas")]}
    pid = projects.save_project(con, admin, {"code": "P1", "name": "Projektas"})
    a = projects.save_assembly(con, admin, pid, {"code": "100", "name": "Rėmas"})
    fin = projects.save_assembly(con, admin, pid, {"code": "900", "name": "Galutinis", "requires": "100"})
    mk = lambda asm, centre, seq, name, part="", qty=1: tasks.create_task(con, admin, {
        "project_id": pid, "assembly_id": asm, "centre_id": c[centre], "seq": seq, "name": name, "part_no": part,
        "qty_plan": qty, "norm_min": 10, "drawing_no": "D-1"})
    ids = {"laz": mk(a, "LAZ", 10, "Pjovimas", "A", 2), "lnk": mk(a, "LNK", 20, "Lenkimas", "A", 2),
           "tek": mk(a, "TEK", 10, "Tekinimas", "B"), "sv": mk(a, "SV", 30, "Suvirinimas"),
           "daz": mk(a, "DAZ", 40, "Dažymas"), "sur": mk(fin, "SUR", 10, "Surinkimas")}
    approve = lambda: sum(tasks.approve_queue(con, admin, x) for x in c.values())
    return {"admin": admin, "op": op, "a": a, "fin": fin, "ids": ids, "c": c, "approve": approve, "pid": pid}


def test_neisleistas_marsrutas_netvirtinamas_ir_nepradedamas(con, flow):
    assert flow["approve"]() == 0
    with pytest.raises(RuleError, match="neišleistas"):
        tasks.start(con, flow["op"], flow["ids"]["laz"])


def test_isleidimas_tikrina_srauta(con, flow):
    tasks.update_task(con, flow["admin"], flow["ids"]["sv"], {"seq": 15})   # suvirinimas prieš lenkimą
    with pytest.raises(RuleError, match="eina prieš detalių"):
        routing.release(con, flow["admin"], flow["a"])
    tasks.update_task(con, flow["admin"], flow["ids"]["sv"], {"seq": 30})
    res = routing.release(con, flow["admin"], flow["a"])
    assert res == {"errors": [], "warnings": []}
    # 900 laukia 100 – jau išleistas, tad įspėjimo nėra
    assert routing.release(con, flow["admin"], flow["fin"])["warnings"] == []


def test_detales_susilieja_ir_perduodamos(con, flow, clock):
    s, op, ids = flow, flow["op"], flow["ids"]
    for a in (s["a"], s["fin"]):
        routing.release(con, s["admin"], a)
    s["approve"]()
    T = lambda i: dict(con.execute("SELECT * FROM tasks WHERE id=?", (i,)).fetchone())
    with pytest.raises(RuleError, match=r"Laukiama detalių: A \(LNK\), B \(TEK\)"):
        tasks.start(con, op, ids["sv"])
    # detalės gaminamos lygiagrečiai
    tasks.start(con, op, ids["laz"])
    tasks.start(con, op, ids["tek"])
    r = tasks.stop(con, op, ids["laz"], 1)                       # dalinis perdavimas
    assert r["status"] == "laukia" and [d["centre_code"] for d in r["next"]] == ["LNK"]
    assert routing.arrived(T(ids["lnk"]), [T(ids["laz"])]) == 1
    r = tasks.stop(con, op, ids["tek"], 1)
    assert r["next"][0]["centre_code"] == "SV" and r["next"][0]["joins"] == 2
    with pytest.raises(RuleError, match=r"Laukiama detalių: A \(LNK\)"):
        tasks.start(con, op, ids["sv"])
    tasks.start(con, op, ids["lnk"])
    tasks.stop(con, op, ids["lnk"], 1)
    tasks.start(con, op, ids["sv"])                              # visos detalės bent dalimi atkeliavo
    tasks.stop(con, op, ids["sv"], 1)
    tasks.start(con, op, ids["daz"])
    r = tasks.stop(con, op, ids["daz"], 1)
    assert r["next"][0]["centre_code"] == "SUR" and r["next"][0]["assembly"] == "900 Galutinis"
    # 900 laukia, kol VISOS 100 operacijos baigtos (laz, lnk dar ne)
    with pytest.raises(RuleError, match="Laukiama mazgų: 100"):
        tasks.start(con, op, ids["sur"])
    for i in ("laz", "lnk"):
        tasks.start(con, op, ids[i])
        tasks.stop(con, op, ids[i], 1)
    tasks.start(con, op, ids["sur"])
    assert tasks.stop(con, op, ids["sur"], 1)["next"] == [{"task_id": None, "label": routing.STORE}]

    tr = routing.trace(con, s["a"])
    assert [b["part"] for b in tr["branches"]] == ["A", "B"] and tr["main"]["done"]
    assert len(tr["transfers"]) == 7                             # kiekvienas Stop su gerais vienetais
    assert any(m["to_label"] == "SUR · Surinkimas" for m in tr["transfers"])
    assert routing.trace(con, s["fin"])["transfers"][0]["to_label"] == routing.STORE


def test_kur_dabar_detale(con, flow):
    s, op, ids = flow, flow["op"], flow["ids"]
    routing.release(con, s["admin"], s["a"])
    s["approve"]()
    tasks.start(con, op, ids["laz"])
    tasks.stop(con, op, ids["laz"], 1)
    tr = routing.trace(con, s["a"])
    a_ops = tr["branches"][0]["ops"]
    assert a_ops[0]["here"] == "liko 1 vnt."
    assert a_ops[1]["here"] == "laukia 1 vnt."
    assert tr["main"]["ops"][0]["lock"].startswith("Laukiama detalių")


def test_isleistas_marsrutas_uzrakintas(con, flow):
    s = flow
    routing.release(con, s["admin"], s["a"])
    with pytest.raises(RuleError, match="Keisti maršrutą"):
        tasks.create_task(con, s["admin"], {"project_id": s["pid"], "assembly_id": s["a"],
                                            "centre_id": s["c"]["SV"], "name": "Papildoma"})
    with pytest.raises(RuleError, match="Keisti maršrutą"):
        tasks.update_task(con, s["admin"], s["ids"]["sv"], {"qty_plan": 3})
    with pytest.raises(RuleError, match="Keisti maršrutą"):
        tasks.delete_task(con, s["admin"], s["ids"]["daz"])
    tasks.update_task(con, s["admin"], s["ids"]["sv"], {"name": "Rėmo suvirinimas", "norm_min": 90})  # srauto nekeičia
    with pytest.raises(RuleError, match="kodėl"):
        routing.unrelease(con, s["admin"], s["a"], " ")
    routing.unrelease(con, s["admin"], s["a"], "Pridedamas smėliavimas")
    tasks.create_task(con, s["admin"], {"project_id": s["pid"], "assembly_id": s["a"], "centre_id": s["c"]["SV"],
                                        "seq": 35, "name": "Smėliavimas"})
    log = [r[0] for r in con.execute("SELECT action FROM events WHERE entity='assembly' AND entity_id=? ORDER BY id",
                                     (s["a"],))]
    assert log[-2:] == ["release", "unrelease"]


def test_importas_neliecia_isleisto(con, flow):
    routing.release(con, flow["admin"], flow["a"])
    csv = ("projektas;mazgas;seka;centras;operacija;detale\n"
           "P1;100;50;SV;Papildoma;\n"
           "P1;200;10;LAZ;Pjovimas;C-1\n")
    r = importer.run(con, {"id": flow["admin"]}, csv)
    assert len(r["errors"]) == 1 and "išleistas" in r["errors"][0] and r["tasks_new"] == 0


def test_api(sample_client):
    c = sample_client
    login(c, "technologas")
    p = next(x for x in c.get("/api/projects").json() if x["code"] == "P-24121")
    a = next(x for x in c.get(f"/api/projects/{p['id']}").json()["assemblies"] if x["code"] == "200")
    r = c.get(f"/api/route/{a['id']}").json()
    assert not r["released"] and [b["part"] for b in r["branches"]] == ["2210-201", "2210-202"]
    assert [o["centre_code"] for o in r["main"]["ops"]] == ["SV-03", "DAZ-02"]
    # lenkimo presui (LNK-01) programos dar nėra – išleisti negalima
    rel = c.post(f"/api/route/{a['id']}/release")
    assert rel.status_code == 409 and "nepridėtas programos" in rel.json()["detail"]
    lnk = next(o for o in r["branches"][1]["ops"] if o["centre_code"] == "LNK-01")
    assert c.post(f"/api/tasks/{lnk['id']}/files", files={"file": ("2210-202.nc", b"M30\n")}).status_code == 200
    # P-24121 – EXC2: suvirinimui reikia WPS
    rel = c.post(f"/api/route/{a['id']}/release")
    assert rel.status_code == 409 and "nenurodytas WPS" in rel.json()["detail"]
    wps = c.get("/api/quality/wps").json()[0]["id"]
    sv = next(o for o in r["main"]["ops"] if o["centre_code"] == "SV-03")
    assert c.put(f"/api/tasks/{sv['id']}", json={"wps_id": wps}).status_code == 200
    assert c.post(f"/api/route/{a['id']}/release").status_code == 200
    assert c.get(f"/api/route/{a['id']}").json()["released"]
    assert c.get("/api/qr", params={"data": "http://x/#/r/1"}).text.startswith("<svg")
    login(c, "meistras")
    assert c.post(f"/api/route/{a['id']}/unrelease", json={"reason": "x"}).status_code == 403
    # operatorius nuskenuoja maršruto lapą – mato srautą, nors projektų ne
    login(c, pin="1111")
    assert c.get(f"/api/route/{a['id']}").status_code == 200


def test_terminalas_rodo_is_kur_ir_kur(con, flow):
    s = flow
    routing.release(con, s["admin"], s["a"])
    s["approve"]()
    centre = dict(con.execute("SELECT * FROM work_centres WHERE id=?", (s["c"]["SV"],)).fetchone())
    t = tasks.terminal_view(con, centre)["queue"][0]
    assert [f["part_no"] for f in t["from"]] == ["A", "B"] and t["next"][0]["centre_code"] == "DAZ"
