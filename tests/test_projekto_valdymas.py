"""Projekto valdymas: užduočių statusai, protokolai, projekto sveikata."""

import pytest
from conftest import login

from vmgt import db
from vmgt.services import RuleError, actions, auth, components, health, meetings, projects


@pytest.fixture
def team(con, clock):
    U = lambda login, role: dict(con.execute("SELECT * FROM users WHERE id=?", (
        auth.create_user(con, login, login.title(), role, "x"),)).fetchone())
    vad, tech, op = U("vad", "vadovas"), U("tech", "technologas"), U("op", "operatorius")
    pid = projects.save_project(con, vad["id"], {"code": "P1", "name": "Projektas", "due_date": "2026-11-10"})
    return {"vad": vad, "tech": tech, "op": op, "pid": pid}


def A(con, aid):
    return actions.get(con, aid)


def test_statusu_perejimai_ir_istorija(con, team, clock):
    vad = team["vad"]
    aid = actions.create(con, vad["id"], {"project_id": team["pid"], "title": "Išleisti brėžinius", "owner_id": team["tech"]["id"]})
    with pytest.raises(RuleError, match="pereiti negalima"):
        actions.set_status(con, vad, aid, "atlikta")              # nauja → atlikta neleidžiama
    clock.set("2026-10-20T09:00:00+00:00")
    actions.set_status(con, vad, aid, "vykdoma")
    with pytest.raises(RuleError, match="priežastį"):
        actions.set_status(con, vad, aid, "laukia")
    actions.set_status(con, vad, aid, "laukia", "Laukiama užsakovo")
    assert A(con, aid)["wait_reason"] == "Laukiama užsakovo"
    clock.set("2026-10-21T09:00:00+00:00")
    actions.set_status(con, vad, aid, "vykdoma")
    assert actions.wait_seconds(con, aid) == 24 * 3600         # laukė 10-20 09:00 – 10-21 09:00
    actions.set_status(con, vad, aid, "perziura")
    actions.set_status(con, vad, aid, "atlikta")
    assert A(con, aid)["done_at"] == "2026-10-21T09:00:00+00:00"
    actions.set_status(con, vad, aid, "vykdoma")                  # atidaryta iš naujo
    assert A(con, aid)["done_at"] is None
    h = actions.history(con, aid)
    assert [x["to_status"] for x in h if x["kind"] == "status"] == \
        ["nauja", "vykdoma", "laukia", "vykdoma", "perziura", "atlikta", "vykdoma"]


def test_atsakingasis_keicia_savo_statusa_kiti_ne(con, team):
    aid = actions.create(con, team["vad"]["id"], {"project_id": team["pid"], "title": "X", "owner_id": team["op"]["id"]})
    actions.set_status(con, team["op"], aid, "vykdoma")           # operatorius – savo užduotis
    other = dict(con.execute("SELECT * FROM users WHERE id=?", (auth.create_user(con, "op2", "Op2", "operatorius", "x"),)).fetchone())
    with pytest.raises(RuleError, match="atsakingasis"):
        actions.set_status(con, other, aid, "laukia", "x")
    with pytest.raises(RuleError, match="atsakingasis"):
        actions.update(con, other, aid, {"title": "Kita"})


def test_veluojanti_uzduotis(con, team):
    aid = actions.create(con, team["vad"]["id"], {"project_id": team["pid"], "title": "X", "due_date": "2026-10-19"})
    assert A(con, aid)["overdue"]
    actions.set_status(con, team["vad"], aid, "atsaukta", "Nebeaktualu")
    assert not A(con, aid)["overdue"]


def test_protokolo_veiksmai_tampa_uzduotimis_ir_uzrakinimas(con, team, clock):
    vad = team["vad"]
    m1 = meetings.save(con, vad, {"project_id": team["pid"], "title": "Pradžia", "held_at": "2026-10-10T09:00",
                                  "attendees": [vad["id"]], "decisions": "Pirmas\n\nAntras",
                                  "new_actions": [{"title": "Užsakyti PLC", "owner_id": team["tech"]["id"], "due_date": "2026-10-15"},
                                                  {"title": "  "}]})
    m = meetings.get(con, m1)
    assert [x["title"] for x in m["actions"]] == ["Užsakyti PLC"] and m["decision_list"] == ["Pirmas", "Antras"]
    meetings.approve(con, vad, m1)
    with pytest.raises(RuleError, match="Patvirtinto"):
        meetings.save(con, vad, {"notes": "pakeista"}, m1)
    m2 = meetings.save(con, vad, {"project_id": team["pid"], "title": "Savaitinis", "held_at": "2026-10-17T09:00"})
    assert [x["title"] for x in meetings.get(con, m2)["review"]] == ["Užsakyti PLC"]    # neuždarytas ankstesnis
    with pytest.raises(RuleError, match="dalyviai"):
        meetings.approve(con, vad, m2)
    txt = meetings.as_text(meetings.get(con, m1))
    assert "SPRENDIMAI" in txt and "Užsakyti PLC" in txt


def test_sveikata_terminai(con, team, clock):
    pid = team["pid"]
    projects.save_phase(con, None, pid, {"kind": "projektavimas", "plan_start": "2026-10-01", "plan_end": "2026-10-10"})
    projects.save_phase(con, None, pid, {"kind": "gamyba", "plan_start": "2026-10-11", "plan_end": "2026-11-08"})
    h = health.project_health(con, pid)
    sch = h["dimensions"][0]
    # projektavimas vėluoja 10 d. → raudona, prognozė 11-08 + 10 d. > terminas 11-10
    assert sch["level"] == "red" and sch["metrics"]["forecast_end"] == "2026-11-18"
    assert any("vėlesnė už terminą" in r["text"] for r in sch["reasons"])
    assert h["level"] == "red"


def test_sveikata_komponentai_ir_kokybe(con, team, clock):
    pid = team["pid"]
    components.save(con, team["vad"]["id"], {"project_id": pid, "name": "PLC", "po_no": "PO-1", "need_date": "2026-10-18"})
    db_ = con
    db_.execute("INSERT INTO ncr (project_id, reported_at, category, description) VALUES (?,?,?,?)",
                (pid, "2026-10-05T10:00:00+00:00", "kita", "x"))
    h = {d["key"]: d for d in health.project_health(con, pid)["dimensions"]}
    assert h["components"]["level"] == "red" and "reikėjo iki" in h["components"]["reasons"][0]["text"]
    assert h["quality"]["level"] == "red"            # atvira 15 d. > 7


def test_sveikata_gera_kai_viskas_pagal_plana(con, team, clock):
    pid = team["pid"]
    projects.save_phase(con, None, pid, {"kind": "projektavimas", "plan_start": "2026-10-15", "plan_end": "2026-10-30"})
    con.execute("UPDATE phases SET status='vykdoma'")
    h = health.project_health(con, pid)
    assert h["level"] == "green" and h["score"] == 100


def test_api_ir_teises(sample_client):
    login(sample_client, "vadovas")
    ps = {p["code"]: p for p in sample_client.get("/api/projects").json()}
    assert ps["P-24117"]["health"]["level"] == "red"           # vėluojantys komponentai
    assert ps["P-24130"]["health"]["level"] == "green"
    ms = sample_client.get(f"/api/meetings?project_id={ps['P-24117']['id']}").json()
    assert len(ms) == 2
    m = sample_client.get(f"/api/meetings/{ms[0]['id']}").json()
    assert m["review"] and "VEIKSMAI" in m["text"]
    login(sample_client, "kokybe")
    assert sample_client.post("/api/meetings", json={"project_id": 1, "title": "X", "held_at": "2026-10-25T10:00"}).status_code == 403
    mine = sample_client.get("/api/actions?owner=me").json()
    assert mine and all(x["owner_name"] == "Laura Kokybė" for x in mine)
    login(sample_client, pin="1111")                              # operatorius be view
    assert sample_client.get("/api/actions").status_code == 403
    assert sample_client.get("/api/actions?owner=me").status_code == 200
