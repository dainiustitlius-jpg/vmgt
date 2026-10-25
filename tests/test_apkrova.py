"""Resursų apkrova: valandų paskirstymas, pajėgumas, trūkumai, krepšelio projektai."""

from datetime import date

import pytest
from conftest import login

from vmgt.services import capacity, projects, tasks


def test_paskirstymas_darbo_dienomis():
    # pirmadienis–penktadienis, 50 val. – po 10 val. dienai, viena savaitė
    wh, note = capacity.spread(50, date(2026, 10, 26), date(2026, 10, 30), date(2026, 10, 20), "planuota")
    assert wh == {date(2026, 10, 26): 50} and note is None
    # dvi savaitės, savaitgalis neskaičiuojamas
    wh, _ = capacity.spread(100, date(2026, 10, 26), date(2026, 11, 6), date(2026, 10, 20), "planuota")
    assert wh == {date(2026, 10, 26): 50, date(2026, 11, 2): 50}


def test_nepradetas_etapas_pasislenka_vykdomo_praeitis_atlikta():
    today = date(2026, 10, 28)                                  # trečiadienis
    wh, note = capacity.spread(50, date(2026, 10, 26), date(2026, 10, 30), today, "planuota")
    assert note == "pradžia pasislinko" and sum(wh.values()) == pytest.approx(50)
    wh, _ = capacity.spread(50, date(2026, 10, 26), date(2026, 10, 30), today, "vykdoma")
    assert sum(wh.values()) == pytest.approx(30)                # pirm. ir antr. laikomos atliktomis
    wh, note = capacity.spread(50, date(2026, 10, 12), date(2026, 10, 16), today, "vykdoma")
    assert note.startswith("vėluoja") and sum(wh.values()) > 0  # vėlavimas nedingsta iš apkrovos


@pytest.fixture
def setup(con, clock):
    clock.set("2026-10-26T08:00:00+00:00")                      # pirmadienis
    proj = capacity.save_department(con, None, {"code": "PROJ", "name": "Projektavimas", "kind": "office",
                                                "phase_kinds": "projektavimas", "headcount": 2, "availability": 1})
    area = projects.save_area(con, None, {"code": "SVB", "name": "Suvirinimas"})
    capacity.save_department(con, None, {"code": "SVB", "name": "Suvirinimas", "kind": "production", "area_id": area,
                                         "headcount": 1, "availability": 1})
    sv = projects.save_centre(con, None, {"code": "SV-01", "name": "SV", "kind": "suvirinimas", "area_id": area})
    p1 = projects.save_project(con, None, {"code": "P1", "name": "Vykdomas", "status": "vykdomas"})
    p2 = projects.save_project(con, None, {"code": "P2", "name": "Krepšelis"})
    return {"proj": proj, "sv": sv, "p1": p1, "p2": p2}


def dep(r, code):
    return next(d for d in r["departments"] if d["code"] == code)


def test_trukumas_ir_krepselio_poveikis(con, setup):
    s = setup
    projects.save_phase(con, None, s["p1"], {"kind": "projektavimas", "plan_start": "2026-10-26",
                                             "plan_end": "2026-10-30", "hours": 60})
    projects.save_phase(con, None, s["p2"], {"kind": "projektavimas", "plan_start": "2026-10-26",
                                             "plan_end": "2026-10-30", "hours": 40})
    r = capacity.report(con, weeks=4)
    c = dep(r, "PROJ")["cells"][0]
    assert (c["capacity"], c["committed"], c["basket"], c["shortage"]) == (80, 60, 40, 20)
    sh = r["shortages"][0]
    assert sh["code"] == "PROJ" and sh["basket_only"] and sh["people"] == 0.5
    fit = r["basket_fit"][0]
    assert fit["code"] == "P2" and fit["fits"] is False and fit["needs"][0]["over"] == 20
    assert capacity.report(con, weeks=4, include_basket=False)["shortages"] == []


def test_gamybos_etapas_ivertis_pakeiciamas_normomis(con, setup):
    s = setup
    a = projects.save_assembly(con, None, s["p1"], {"code": "100", "name": "Rėmas"})
    projects.save_phase(con, None, s["p1"], {"assembly_id": a, "kind": "gamyba", "plan_start": "2026-10-26",
                                             "plan_end": "2026-10-30", "hours": 100,
                                             "department_id": dep(capacity.report(con), "SVB")["id"]})
    assert dep(capacity.report(con, weeks=4), "SVB")["cells"][0]["committed"] == 100     # įvertis
    t = tasks.create_task(con, None, {"project_id": s["p1"], "assembly_id": a, "centre_id": s["sv"], "name": "Suvirinti",
                                      "qty_plan": 4, "norm_min": 90})
    assert dep(capacity.report(con, weeks=4), "SVB")["cells"][0]["committed"] == 6        # 4 × 90 min
    con.execute("UPDATE tasks SET qty_good=2 WHERE id=?", (t,))
    assert dep(capacity.report(con, weeks=4), "SVB")["cells"][0]["committed"] == 3        # liko 2 vnt.


def test_truksta_duomenu_parodoma(con, setup):
    projects.save_phase(con, None, setup["p1"], {"kind": "projektavimas", "plan_start": "2026-10-26",
                                                 "plan_end": "2026-10-30"})
    projects.save_phase(con, None, setup["p1"], {"kind": "gamyba", "plan_start": "2026-10-26",
                                                 "plan_end": "2026-10-30", "hours": 10})
    why = {u["why"] for u in capacity.report(con)["unassigned"]}
    assert "nenurodytos planuojamos valandos" in why
    assert any("nenurodytas departamentas" in w for w in why)


def test_savaitgali_nuo_kitos_savaites(con, setup, clock):
    clock.set("2026-10-25T10:00:00+00:00")                      # sekmadienis
    assert capacity.report(con)["weeks"][0]["start"] == "2026-10-26"


def test_api(sample_client):
    login(sample_client, "vadovas")
    r = sample_client.get("/api/capacity?weeks=12").json()
    codes = [d["code"] for d in r["departments"]]
    assert codes[:5] == ["PROJ", "TECH", "PIRK", "PROG", "TEST"] and "SVB" in codes
    assert r["projects_active"] == 1 and r["projects_basket"] == 2
    assert any(s["code"] == "SVB" for s in r["shortages"])
    d = next(x for x in sample_client.get("/api/departments").json() if x["code"] == "SVB")
    assert sample_client.put(f"/api/departments/{d['id']}", json={"headcount": 20}).status_code == 200
    r2 = sample_client.get("/api/capacity?weeks=12").json()
    assert not any(s["code"] == "SVB" for s in r2["shortages"])
    login(sample_client, "kokybe")
    assert sample_client.put(f"/api/departments/{d['id']}", json={"headcount": 1}).status_code == 403
