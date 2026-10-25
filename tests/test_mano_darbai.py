"""Asmeninis darbų planas: užduotys sau, privatumas, savaitės planas dienomis."""

import sqlite3
from datetime import date

import pytest
from conftest import login

from vmgt import db
from vmgt.services import NotFound, RuleError, actions, auth, projects


@pytest.fixture
def people(con, clock):
    clock.set("2026-10-28T09:00:00+00:00")                      # trečiadienis
    u = lambda login, role: dict(con.execute("SELECT * FROM users WHERE id=?", (
        auth.create_user(con, login, login.title(), role, "x"),)).fetchone())
    pid = projects.save_project(con, None, {"code": "P1", "name": "Projektas"})
    return {"jonas": u("jonas", "technologas"), "ona": u("ona", "vadovas"), "pid": pid}


def test_asmenine_matoma_tik_savininkui(con, people):
    j, o = people["jonas"], people["ona"]
    a = actions.create(con, j["id"], {"title": "Sau", "owner_id": o["id"]})
    assert actions.get(con, a)["owner_id"] == j["id"]           # asmeninė – visada kūrėjo
    assert [x["id"] for x in actions.list_actions(con, viewer_id=o["id"])] == []
    assert [x["id"] for x in actions.list_actions(con, owner_id=j["id"], viewer_id=j["id"])] == [a]
    assert not actions.can_see(o, actions.get(con, a))
    with pytest.raises(NotFound):                               # vadovas – ir tas nemato
        actions.update(con, o, a, {"title": "x"})
    with pytest.raises(NotFound):
        actions.comment(con, o, a, "labas")


def test_priskirti_kitam_tik_susiejus_su_projektu(con, people):
    j, o = people["jonas"], people["ona"]
    a = actions.create(con, j["id"], {"title": "Brėžiniai", "plan_date": "2026-10-29"})
    with pytest.raises(RuleError, match="pirma pasirinkite projektą"):
        actions.update(con, j, a, {"owner_id": o["id"]})
    actions.update(con, j, a, {"project_id": people["pid"], "owner_id": o["id"]})
    x = actions.get(con, a)
    assert x["project_id"] == people["pid"] and x["owner_id"] == o["id"] and x["plan_date"] is None
    assert actions.can_see(o, x)
    with pytest.raises(RuleError, match="paversti asmenine"):
        actions.update(con, o, a, {"project_id": None})
    with pytest.raises(RuleError, match="pats atsakingasis"):  # Jono planas – ne Onos reikalas
        actions.update(con, j, a, {"plan_date": "2026-10-30"})


def test_asmenine_galima_iskart_atlikti(con, people):
    j = people["jonas"]
    a = actions.create(con, j["id"], {"title": "Sau"})
    assert actions.set_status(con, j, a, "atlikta")["status"] == "atlikta"
    p = actions.create(con, j["id"], {"title": "Projektui", "project_id": people["pid"], "owner_id": j["id"]})
    with pytest.raises(RuleError, match="pereiti negalima"):
        actions.set_status(con, j, p, "atlikta")


def test_savaites_planas(con, people, clock):
    j = people["jonas"]
    mk = lambda t, **kw: actions.create(con, j["id"], {"title": t, **kw})
    mk("Neplanuota")
    mk("Vakar", plan_date="2026-10-27", estimate_h=2)
    mk("Šiandien", plan_date="2026-10-28", estimate_h="7,5")
    mk("Penktadienį", plan_date="2026-10-30")
    mk("Kitą savaitę", plan_date="2026-11-03")
    p = mk("Projekto", project_id=people["pid"], owner_id=j["id"], plan_date="2026-10-29", due_date="2026-10-28")
    done = mk("Atlikta", plan_date="2026-10-26")
    actions.set_status(con, j, done, "atlikta")
    actions.create(con, people["ona"]["id"], {"title": "Onos"})   # kito žmogaus – nerodoma

    w = actions.week(con, j["id"])
    day = {d["date"]: d for d in w["days"]}
    titles = lambda items: [x["title"] for x in items]
    assert w["start"] == "2026-10-26" and titles(w["unplanned"]) == ["Neplanuota"]
    assert titles(day["2026-10-26"]["items"]) == ["Atlikta"]
    assert titles(day["2026-10-27"]["items"]) == []             # neatlikta vakar → šiandien
    today = day["2026-10-28"]
    assert sorted(titles(today["items"])) == ["Vakar", "Šiandien"] and today["hours"] == 9.5 and today["over"]
    assert next(x for x in today["items"] if x["title"] == "Vakar")["rolled_from"] == "2026-10-27"
    assert day["2026-10-29"]["items"][0]["late_plan"]           # suplanuota po termino
    assert titles(w["later"]) == ["Kitą savaitę"] and w["open"] == 6
    # kitos savaitės vaizde – kitos savaitės dienos
    w2 = actions.week(con, j["id"], date(2026, 11, 4))
    assert w2["start"] == "2026-11-02" and titles(w2["days"][1]["items"]) == ["Kitą savaitę"]
    assert p in [x["id"] for x in day["2026-10-29"]["items"]]
    with pytest.raises(RuleError, match="praeitį"):
        actions.update(con, j, p, {"plan_date": "2026-10-27"})


def test_savaitgali_planas_nuo_pirmadienio(con, people, clock):
    clock.set("2026-10-25T10:00:00+00:00")                      # sekmadienis
    j = people["jonas"]
    actions.create(con, j["id"], {"title": "Penktadienio", "plan_date": "2026-10-23"})
    w = actions.week(con, j["id"])
    assert w["start"] == "2026-10-26" and w["days"][0]["items"][0]["rolled_from"] == "2026-10-23"
    # sekmadienį pažymėta atlikta pirmadienio užduotis lieka pirmadienyje
    a = actions.create(con, j["id"], {"title": "Pirmadienio", "plan_date": "2026-10-26"})
    actions.set_status(con, j, a, "atlikta")
    assert "Pirmadienio" in [x["title"] for x in actions.week(con, j["id"])["days"][0]["items"]]


def test_migracija_islaiko_uzduotis(tmp_path):
    """7 versijos bazė su užduotimis ir istorija → 8: niekas nedingsta."""
    path = tmp_path / "v7.db"
    c = db.connect(path)
    ver = 0
    for i, sql in enumerate(db.MIGRATIONS[:7], start=1):
        c.executescript(sql)
        c.execute(f"PRAGMA user_version = {i}")
        ver = i
    assert ver == 7
    c.execute("INSERT INTO projects (code, name, created) VALUES ('P', 'P', '2026-10-01')")
    c.execute("INSERT INTO actions (project_id, title, created, updated) VALUES (1, 'Sena', 'x', 'x')")
    c.execute("INSERT INTO action_log (action_id, at, kind) VALUES (1, 'x', 'comment')")
    c.commit()
    assert db.migrate(c) == len(db.MIGRATIONS)
    assert [tuple(r) for r in c.execute("SELECT title, plan_date FROM actions")] == [("Sena", None)]
    assert c.execute("PRAGMA foreign_key_check").fetchall() == []
    with pytest.raises(sqlite3.IntegrityError):                 # nuoroda į actions veikia ir po perkūrimo
        c.execute("INSERT INTO action_log (action_id, at, kind) VALUES (99, 'x', 'comment')")


def test_api(sample_client):
    c = sample_client
    login(c, "op1")
    r = c.post("/api/actions", json={"title": "Pasiruošti įrankius", "plan_date": None})
    assert r.status_code == 200                                 # operatorius irgi planuojasi sau
    assert c.post("/api/actions", json={"title": "x", "project_id": 1}).status_code == 403
    w = c.get("/api/my/week").json()
    assert [x["title"] for x in w["unplanned"]] == ["Pasiruošti įrankius"]
    aid = r.json()["id"]
    login(c, "vadovas")
    assert c.get(f"/api/actions/{aid}").status_code == 404
    assert all(x["id"] != aid for x in c.get("/api/actions").json())
    w = c.get("/api/my/week").json()
    every = [x["title"] for d in w["days"] for x in d["items"]] + [x["title"] for x in w["unplanned"] + w["later"]]
    assert "Paruošti pasiūlymą UAB Pavyzdys (talpų stovai)" in every
    assert "Susitvarkyti Lantek lakštų bibliotekas" not in every  # technologo – nerodoma
