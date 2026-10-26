"""Planuotojo langas: Gantt pagal departamentus, pakeitimų poveikis kitiems
projektams ir signalai (pranešimai)."""

import pytest
from conftest import login

from vmgt.services import auth, capacity, components, planner, projects, routing, signals, tasks


@pytest.fixture
def plant(con, clock):
    clock.set("2026-10-26T08:00:00+00:00")                      # pirmadienis
    U = lambda i: dict(con.execute("SELECT * FROM users WHERE id=?", (i,)).fetchone())
    plan = U(auth.create_user(con, "plan", "Planuotojas", "planuotojas", "x"))
    va = U(auth.create_user(con, "va", "Vadovas A", "vadovas", "x"))
    vb = U(auth.create_user(con, "vb", "Vadovas B", "vadovas", "x"))
    op = U(auth.create_user(con, "op", "Op", "operatorius", "x"))
    capacity.save_department(con, None, {"code": "PROJ", "name": "Projektavimas", "kind": "office",
                                         "phase_kinds": "projektavimas", "headcount": 1, "availability": 1})
    area = projects.save_area(con, None, {"code": "SVB", "name": "Suvirinimas"})
    capacity.save_department(con, None, {"code": "SVB", "name": "Suvirinimas", "kind": "production", "area_id": area,
                                         "headcount": 1, "availability": 1})
    sv = projects.save_centre(con, None, {"code": "SV-01", "name": "SV", "kind": "suvirinimas", "area_id": area})
    a = projects.save_project(con, None, {"code": "A", "name": "Projektas A", "status": "vykdomas", "manager_id": va["id"],
                                          "due_date": "2026-11-20"})
    b = projects.save_project(con, None, {"code": "B", "name": "Projektas B", "status": "vykdomas", "manager_id": vb["id"]})
    pa = projects.save_phase(con, None, a, {"kind": "projektavimas", "plan_start": "2026-10-26",
                                            "plan_end": "2026-10-30", "hours": 30})
    pb = projects.save_phase(con, None, b, {"kind": "projektavimas", "plan_start": "2026-11-02",
                                            "plan_end": "2026-11-06", "hours": 30})
    asm = {}
    for pid, code in ((a, "A"), (b, "B")):
        asm[code] = projects.save_assembly(con, None, pid, {"code": "100", "name": "Rėmas"})
    ta = tasks.create_task(con, None, {"project_id": a, "assembly_id": asm["A"], "centre_id": sv, "name": "Suvirinti A",
                                       "norm_min": 60, "qty_plan": 2})
    tb = tasks.create_task(con, None, {"project_id": b, "assembly_id": asm["B"], "centre_id": sv, "name": "Suvirinti B",
                                       "norm_min": 120, "qty_plan": 1})
    for x in asm.values():
        routing.release(con, None, x)
    tasks.approve_queue(con, None, sv)
    return {"plan": plan, "va": va, "vb": vb, "op": op, "a": a, "b": b, "pa": pa, "pb": pb, "ta": ta, "tb": tb,
            "sv": sv, "asm": asm}


def test_gantt_departamentai_ir_juostos(con, plant):
    r = planner.board(con, weeks=6)
    proj = next(d for d in r["departments"] if d["code"] == "PROJ")
    assert {b["phase_id"] for b in proj["bars"]} == {plant["pa"], plant["pb"]}
    assert proj["load"][1]["hours"] == 30                       # S44: tik A (pirmoji – praėjusi savaitė)


def test_perkelimo_poveikis_neirasomas(con, plant):
    s = plant
    ch = {"kind": "phase", "phase_id": s["pb"], "plan_start": "2026-10-26", "plan_end": "2026-10-30"}
    imp = planner.impact(con, s["plan"], ch)
    a = next(x for x in imp["affected"] if x["code"] == "A")
    assert a["severity"] == "red" and "75 % → 150 %" in a["reasons"][0] and "trūksta 20 val." in a["reasons"][0]
    assert con.execute("SELECT plan_start FROM phases WHERE id=?", (s["pb"],)).fetchone()[0] == "2026-11-02"
    assert con.execute("SELECT COUNT(*) FROM plan_changes").fetchone()[0] == 0


def test_irasymas_praneša_paveiktiems(con, plant):
    s = plant
    ch = {"kind": "phase", "phase_id": s["pb"], "plan_start": "2026-10-26", "plan_end": "2026-10-30"}
    planner.apply(con, s["plan"], ch, "Užsakovas paprašė greičiau")
    assert con.execute("SELECT plan_start FROM phases WHERE id=?", (s["pb"],)).fetchone()[0] == "2026-10-26"
    n = signals.list_for(con, s["va"]["id"])
    assert len(n) == 1 and n[0]["severity"] == "red" and "Užsakovas paprašė" in n[0]["body"]
    assert signals.list_for(con, s["plan"]["id"]) == []           # pats sau nepraneša
    assert signals.unread(con, s["va"]["id"]) == 1
    signals.mark_read(con, s["va"]["id"])
    assert signals.unread(con, s["va"]["id"]) == 0
    # paties projekto nuoseklumas: etapas po termino
    imp = planner.impact(con, s["plan"], {"kind": "phase", "phase_id": s["pa"], "plan_start": "2026-11-23",
                                          "plan_end": "2026-11-27"})
    assert any("po projekto termino" in w for w in imp["own"])


def test_eiles_perkelimas(con, plant):
    s = plant
    imp = planner.impact(con, s["plan"], {"kind": "queue", "task_id": s["tb"], "where": "top"})
    a = next(x for x in imp["affected"] if x["code"] == "A")
    assert "1 → 2 vieta" in a["reasons"][0] and "~2.0 val. vėliau" in a["reasons"][0]


def test_veluojantis_darbas_ceche(con, plant, clock):
    s = plant
    tasks.start(con, s["op"], s["ta"])
    clock.set("2026-10-26T09:00:00+00:00")
    tasks.pause(con, s["op"], s["ta"], "gedimas", "")
    clock.set("2026-10-26T10:30:00+00:00")
    tasks.resume(con, s["op"], s["ta"])                          # 90 min. gedimas → B eilėje vėluoja
    n = signals.list_for(con, s["vb"]["id"])
    assert len(n) == 1 and "SV-01 vėluoja 1 val. 30 min." in n[0]["title"] and "įrangos gedimas" in n[0]["title"]
    clock.set("2026-10-26T13:30:00+00:00")
    tasks.stop(con, s["op"], s["ta"], 2)                          # 4 val. darbo vietoj 2
    assert len(signals.list_for(con, s["vb"]["id"])) == 2


def test_planuota_pauze_be_signalo(con, plant, clock):
    s = plant
    tasks.start(con, s["op"], s["ta"])
    tasks.pause(con, s["op"], s["ta"], "pamaina")
    clock.set("2026-10-27T05:00:00+00:00")
    tasks.resume(con, s["op"], s["ta"])
    assert signals.list_for(con, s["vb"]["id"]) == []


def test_komponento_data_nukelta(con, plant, clock):
    s = plant
    projects.save_phase(con, None, s["a"], {"kind": "surinkimas", "plan_start": "2026-11-09", "plan_end": "2026-11-13",
                                            "owner_id": s["plan"]["id"]})
    c = components.save(con, None, {"project_id": s["a"], "name": "Pavara", "qty": 1, "po_no": "PO-1",
                                    "promised_date": "2026-11-02", "need_date": "2026-11-06"})
    components.save(con, None, {"promised_date": "2026-11-12"}, c)
    n = signals.list_for(con, s["va"]["id"])
    assert len(n) == 1 and n[0]["severity"] == "red" and "Paliečia surinkimo etapą" in n[0]["body"]
    # pažadėta data praėjo – signalas vieną kartą
    clock.set("2026-11-13T08:00:00+00:00")
    assert signals.scan(con) == 1 and signals.scan(con) == 0


def test_projektas_is_krepselio(con, plant, clock):
    s = plant
    c = projects.save_project(con, None, {"code": "C", "name": "Naujas", "manager_id": s["vb"]["id"]})
    projects.save_phase(con, None, c, {"kind": "projektavimas", "plan_start": "2026-10-26",
                                       "plan_end": "2026-10-30", "hours": 25})
    imp = planner.impact(con, s["plan"], {"kind": "activate", "project_id": c})
    assert [x["code"] for x in imp["affected"]] == ["A"]
    ph = con.execute("SELECT id FROM phases WHERE project_id=?", (c,)).fetchone()[0]
    projects.set_phase_status(con, s["vb"]["id"], ph, "vykdoma")    # pradėtas darbas – projektas vykdomas
    n = signals.list_for(con, s["va"]["id"])
    assert len(n) == 1 and "patvirtintas projektas C" in n[0]["title"]


def test_api(sample_client):
    c = sample_client
    login(c, "planuotojas")
    r = c.get("/api/planner?weeks=8").json()
    assert any(d["bars"] for d in r["departments"])
    bar = next(b for d in r["departments"] for b in d["bars"] if b["status"] != "baigta")
    ch = {"kind": "phase", "phase_id": bar["phase_id"], "plan_start": bar["plan_start"], "plan_end": "2027-01-29"}
    assert c.post("/api/planner/impact", json=ch).status_code == 200
    assert c.post("/api/planner/apply", json={**ch, "note": "testas"}).status_code == 200
    assert c.get("/api/planner/changes").json()[0]["note"] == "testas"
    login(c, "vadovas")
    n = c.get("/api/notifications").json()
    assert "unread" in n and isinstance(n["items"], list)
    login(c, pin="1111")
    assert c.post("/api/planner/apply", json=ch).status_code == 403
