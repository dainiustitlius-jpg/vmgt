"""Darbo kalendorius: šventės, pamainos gamykla → baras → centras, išimtys,
darbo laiko skaičiavimas, operacijų prognozė, apkrova, pranešimai."""

from datetime import date, datetime, timezone

import pytest
from conftest import login

from vmgt.services import RuleError, auth, capacity, planner, projects, routing, tasks, workcal
from vmgt.services.forecast import forecast

UTC = timezone.utc


def test_sventes_ir_laiko_zona():
    assert workcal.easter(2026) == date(2026, 4, 5) and workcal.easter(2027) == date(2027, 3, 28)
    h = workcal.holidays(2026)
    assert h[date(2026, 4, 6)] == "Velykų antroji diena" and h[date(2026, 11, 2)] == "Vėlinės"
    # vasaros laikas baigiasi paskutinį spalio sekmadienį
    assert workcal.utc_offset(date(2026, 10, 24)) == 3 and workcal.utc_offset(date(2026, 10, 26)) == 2
    assert workcal.parse_hours("11:30-15:30, 07:00-11:00") == [(420, 660), (690, 930)]
    assert workcal.parse_hours("07:00-11:00, 10:00-12:00") == [(420, 720)]          # persidengia – sujungiama
    with pytest.raises(RuleError, match="dviem dalimis"):
        workcal.parse_hours("22:00-06:00")


@pytest.fixture
def plant(con, clock):
    clock.set("2026-10-26T06:00:00+00:00")                  # pirmadienis, 08:00 vietos laiku
    mab = projects.save_area(con, None, {"code": "MAB", "name": "Mechaninis"})
    svb = projects.save_area(con, None, {"code": "SVB", "name": "Suvirinimas"})
    c = {"LAZ": projects.save_centre(con, None, {"code": "LAZ", "name": "Lazeris", "kind": "pjovimas", "area_id": mab}),
         "SV1": projects.save_centre(con, None, {"code": "SV1", "name": "SV 1", "kind": "suvirinimas", "area_id": svb}),
         "SV2": projects.save_centre(con, None, {"code": "SV2", "name": "SV 2", "kind": "suvirinimas", "area_id": svb})}
    return {"c": c, "mab": mab, "svb": svb}


def test_pamainos_ir_isimtys(con, plant):
    s = plant
    cal = workcal.Calendar(con)
    mon, sat = date(2026, 10, 26), date(2026, 10, 31)
    assert cal.day("centre", s["c"]["LAZ"], mon)["minutes"] == 8 * 60                 # gamyklos 1 pamaina
    assert cal.day("centre", s["c"]["LAZ"], date(2026, 11, 2))["kind"] == "svente"     # Vėlinės
    two = con.execute("SELECT id FROM shift_patterns WHERE name='2 pamainos'").fetchone()[0]
    workcal.set_pattern(con, None, "area", s["mab"], two)
    workcal.set_days(con, None, {"scope": "centre", "scope_id": s["c"]["LAZ"], "from": "2026-10-26", "kind": "remontas",
                                 "hours": "06:00-10:00", "note": "Servisas"})
    workcal.set_days(con, None, {"scope": "area", "scope_id": s["svb"], "from": "2026-10-31", "kind": "papildomas",
                                 "hours": "07:00-13:00", "note": "Viršvalandžiai"})
    workcal.set_days(con, None, {"scope": "factory", "from": "2026-11-02", "kind": "kitas", "hours": "08:00-12:00",
                                 "note": "Dirbama per Vėlines"})
    cal = workcal.Calendar(con)
    laz = cal.day("centre", s["c"]["LAZ"], mon)
    assert laz["kind"] == "remontas" and laz["minutes"] == 12 * 60 and laz["own"]
    assert cal.day("area", s["mab"], mon)["minutes"] == 16 * 60                         # kitų baro centrų nepaliečia
    assert cal.day("centre", s["c"]["SV1"], sat)["hours"] == "07:00-13:00"             # baro išimtis paveldima
    assert cal.day("centre", s["c"]["SV1"], date(2026, 11, 2))["minutes"] == 240        # šventė → darbo diena
    # paveldėjimas: centras be savo šablono – baro, baras be savo – gamyklos
    assert cal.pattern_of("centre", s["c"]["LAZ"])[1] == "area" and cal.pattern_of("centre", s["c"]["SV1"])[1] == "factory"
    with pytest.raises(RuleError, match="nurodykite, kas daroma"):
        workcal.set_days(con, None, {"scope": "centre", "scope_id": s["c"]["LAZ"], "from": "2026-10-27", "kind": "remontas"})
    workcal.set_days(con, None, {"scope": "centre", "scope_id": s["c"]["LAZ"], "from": "2026-10-26", "kind": "iprasta"})
    assert workcal.Calendar(con).day("centre", s["c"]["LAZ"], mon)["kind"] == "darbo"


def test_darbo_laikas_per_savaitgali_ir_svente(con, plant):
    cal = workcal.Calendar(con)
    lid = plant["c"]["LAZ"]
    # penktadienį 13:00 UTC (15:00 vietos) + 2 val.: 30 min. penktadienį, tada pirmadienis – Vėlinės (11-02), antradienis
    end = cal.add_work("centre", lid, datetime(2026, 10, 30, 13, 0, tzinfo=UTC), 2 * 3600)
    assert end == datetime(2026, 11, 3, 6, 30, tzinfo=UTC)
    # pertrauka 11:00–11:30 vietos laiku (09:00–09:30 UTC) – neskaičiuojama
    assert cal.add_work("centre", lid, datetime(2026, 10, 26, 8, 30, tzinfo=UTC), 3600) == datetime(2026, 10, 26, 10, 0, tzinfo=UTC)
    st = cal.status("centre", lid, datetime(2026, 10, 26, 18, 0, tzinfo=UTC))
    assert not st["working"] and st["why"].startswith("Ne darbo laikas") and st["next"] == "2026-10-27T05:00+00:00"


def route(con, s, phase_end="2026-10-26"):
    pid = projects.save_project(con, None, {"code": "P1", "name": "Rėmai", "status": "vykdomas"})
    a = projects.save_assembly(con, None, pid, {"code": "100", "name": "Rėmas"})
    projects.save_phase(con, None, pid, {"kind": "gamyba", "plan_start": "2026-10-20", "plan_end": phase_end})
    cut = tasks.create_task(con, None, {"project_id": pid, "assembly_id": a, "centre_id": s["c"]["LAZ"], "seq": 10,
                                        "name": "Pjovimas", "part_no": "D1", "qty_plan": 2, "norm_min": 120})
    weld = tasks.create_task(con, None, {"project_id": pid, "assembly_id": a, "centre_id": s["c"]["SV1"], "seq": 20,
                                         "name": "Suvirinimas", "qty_plan": 1, "norm_min": 240})
    routing.release(con, None, a)
    for c in s["c"].values():
        tasks.approve_queue(con, None, c)
    return pid, cut, weld


def test_prognoze_pagal_eile_srauta_ir_kalendoriu(con, plant):
    s = plant
    pid, cut, weld = route(con, s)
    fc = forecast(con)
    # pjovimas 4 val. nuo 06:00 UTC: 3 val. iki pertraukos + 1 val. po jos
    assert fc[cut]["start"] == "2026-10-26T06:00+00:00" and fc[cut]["end"] == "2026-10-26T10:30+00:00"
    # suvirinimas laukia pjovimo, 3 val. šiandien, 1 val. rytoj
    assert fc[weld]["wait"] == "LAZ · Pjovimas" and fc[weld]["end"] == "2026-10-27T06:00+00:00"
    assert fc[weld]["late"] and fc[weld]["due"] == "2026-10-26"
    # lazerio remontas po pietų – viskas pasislenka
    workcal.set_days(con, None, {"scope": "centre", "scope_id": s["c"]["LAZ"], "from": "2026-10-26", "kind": "remontas",
                                 "hours": "11:30-15:30", "note": "Servisas"})
    fc = forecast(con)
    assert fc[cut]["end"] == "2026-10-27T06:00+00:00" and fc[weld]["end"] == "2026-10-27T10:30+00:00"
    # dalinis perdavimas – suvirinti galima pradėti nelaukiant visko
    op = dict(con.execute("SELECT * FROM users WHERE id=?", (auth.create_user(con, "op", "Op", "operatorius", "x"),)).fetchone())
    tasks.start(con, op, cut)
    tasks.stop(con, op, cut, 1)
    assert forecast(con)[weld]["wait"] is None


def test_apkrova_pagal_kalendoriu(con, plant):
    s = plant
    d = capacity.save_department(con, None, {"code": "SVB", "name": "Suvirinimas", "kind": "production",
                                             "area_id": s["svb"], "headcount": 2, "hours_per_week": 40, "availability": 1})
    capacity.save_department(con, None, {"code": "PROJ", "name": "Projektavimas", "kind": "office",
                                         "phase_kinds": "projektavimas", "headcount": 1, "hours_per_week": 40, "availability": 1})
    r = capacity.report(con, weeks=3)
    sv = next(x for x in r["departments"] if x["id"] == d)
    pr = next(x for x in r["departments"] if x["code"] == "PROJ")
    assert [c["capacity"] for c in sv["cells"]] == [80, 64, 80]                     # 11-02 Vėlinės: 4/5
    assert pr["cells"][1]["capacity"] == 32 and "Vėlinės" in pr["cells"][1]["calendar"][0]
    # vieno iš dviejų postų remontas visą savaitę – baro pajėgumas perpus
    workcal.set_days(con, None, {"scope": "centre", "scope_id": s["c"]["SV2"], "from": "2026-11-09", "to": "2026-11-15",
                                 "kind": "remontas", "note": "Suvirinimo šaltinio remontas"})
    sv = next(x for x in capacity.report(con, weeks=3)["departments"] if x["id"] == d)
    assert sv["cells"][2]["capacity"] == 40 and sv["cells"][2]["factor"] == 0.5
    assert any("SV2: remontas" in n for n in sv["cells"][2]["calendar"])


def test_kalendoriaus_pakeitimas_praneša(con, plant):
    s = plant
    pid, cut, weld = route(con, s, phase_end="2026-10-30")
    mgr = auth.create_user(con, "vad", "Vadovas", "vadovas", "x")
    projects.save_project(con, None, {"manager_id": mgr}, pid)
    pl = dict(con.execute("SELECT * FROM users WHERE id=?", (auth.create_user(con, "pl", "Pl", "planuotojas", "x"),)).fetchone())
    r = planner.calendar_change(con, pl, lambda: workcal.set_days(con, pl["id"], {
        "scope": "area", "scope_id": s["mab"], "from": "2026-10-26", "to": "2026-10-30", "kind": "nedarbo",
        "note": "Lazerio perkėlimas"}))
    a = next(x for x in r["affected"] if x["code"] == "P1")
    assert a["severity"] == "red" and any("nespės iki 2026-10-30" in x for x in a["reasons"])
    n = con.execute("SELECT kind, title, link FROM notifications WHERE user_id=?", (mgr,)).fetchone()
    assert n["kind"] == "calendar" and "P1 paveiktas" in n["title"] and n["link"] == "#/kalendorius"
    assert r["summary"].startswith("MAB Mechaninis: 2026-10-26…2026-10-30 – nedarbo diena")


def test_api(sample_client):
    c = sample_client
    login(c, "planuotojas")
    r = c.get("/api/calendar?year=2026").json()
    assert r["name"] == "Gamykla" and r["pattern"]["name"] == "1 pamaina" and len(r["days"]) == 365
    assert r["totals"]["work_days"] < 253                                        # be švenčių ir uždarymo
    laz = c.get("/api/centres").json()
    lid = next(x["id"] for x in laz if x["code"] == "LAZ-01")
    v = c.get(f"/api/calendar?scope=centre&id={lid}").json()
    assert v["pattern"]["name"] == "2 pamainos" and v["pattern_src"] == "area"
    assert any(e["kind"] == "remontas" and e["own"] for e in v["exceptions"])
    assert c.post("/api/calendar/days", json={"scope": "centre", "scope_id": lid, "from": "2026-12-01",
                                              "kind": "papildomas", "hours": "25:00-26:00"}).status_code == 409
    ok = c.post("/api/calendar/days", json={"scope": "centre", "scope_id": lid, "from": "2026-12-05",
                                            "kind": "papildomas", "hours": "07:00-12:00", "note": "Skubus užsakymas"})
    assert ok.status_code == 200 and ok.json()["days"] == 1 and "summary" in ok.json()
    assert c.put("/api/calendar/patterns/1", json={"name": "1 pamaina", "week": ["x"] * 7}).status_code == 409
    q = c.get("/api/plan/LAZ-01").json()
    assert all("forecast" in t for t in q["tasks"])
    login(c, pin="1111")
    assert c.post("/api/calendar/days", json={"scope": "factory", "from": "2026-12-01", "kind": "nedarbo"}).status_code == 403
    assert "working" in c.get("/api/terminal/LAZ-01").json()["calendar"]
