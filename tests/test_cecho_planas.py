"""Cecho planas: automatinis išdėstymas, būsenos ir įspėjimai, detalių judėjimas,
projekto kelias, išdėstymo saugojimas."""

import pytest
from conftest import login

from vmgt.services import RuleError, auth, layout, ncr, projects, routing, tasks


@pytest.fixture
def plant(con, clock):
    clock.set("2026-10-26T06:00:00+00:00")
    U = lambda i: dict(con.execute("SELECT * FROM users WHERE id=?", (i,)).fetchone())
    op = U(auth.create_user(con, "op", "Op", "operatorius", "x"))
    mab = projects.save_area(con, None, {"code": "MAB", "name": "Mechaninis"})
    svb = projects.save_area(con, None, {"code": "SVB", "name": "Suvirinimas"})
    c = {"LAZ": projects.save_centre(con, None, {"code": "LAZ", "name": "Lazeris", "kind": "pjovimas", "area_id": mab}),
         "LNK": projects.save_centre(con, None, {"code": "LNK", "name": "Lenkimas", "kind": "lenkimas", "area_id": mab})}
    for i in range(1, 8):
        c[f"SV{i}"] = projects.save_centre(con, None, {"code": f"SV{i}", "name": f"SV {i}", "kind": "suvirinimas",
                                                       "area_id": svb})
    pid = projects.save_project(con, None, {"code": "P1", "name": "Projektas", "status": "vykdomas"})
    a = projects.save_assembly(con, None, pid, {"code": "100", "name": "Rėmas"})
    mk = lambda centre, seq, name, part="": tasks.create_task(con, None, {
        "project_id": pid, "assembly_id": a, "centre_id": c[centre], "seq": seq, "name": name, "part_no": part,
        "qty_plan": 2, "norm_min": 30})
    t = {"cut": mk("LAZ", 10, "Pjovimas", "D1"), "bend": mk("LNK", 20, "Lenkimas", "D1"), "weld": mk("SV1", 30, "Suvirinimas")}
    routing.release(con, None, a)
    for x in c.values():
        tasks.approve_queue(con, None, x)
    return {"op": op, "c": c, "t": t, "pid": pid, "mab": mab, "svb": svb}


def centre(p, code):
    return next(c for a in p["areas"] for c in a["centres"] if c["code"] == code)


def test_automatinis_isdestymas_be_persidengimu(con, plant):
    p = layout.plan(con)
    assert [a["code"] for a in p["areas"]] == ["MAB", "SVB"]
    boxes = [a["box"] for a in p["areas"]]
    over = lambda u, v: u["x"] < v["x"] + v["w"] and v["x"] < u["x"] + u["w"] and u["y"] < v["y"] + v["h"] and v["y"] < u["y"] + u["h"]
    assert not over(*boxes)
    for a in p["areas"]:
        cb = [c["box"] for c in a["centres"]]
        assert all(not over(x, y) for i, x in enumerate(cb) for y in cb[i + 1:])
        assert all(b["x"] + b["w"] <= a["box"]["w"] and b["y"] + b["h"] <= a["box"]["h"] for b in cb)   # telpa bare


def test_busenos_ispejimai_judejimas(con, plant, clock):
    s = plant
    tasks.start(con, s["op"], s["t"]["cut"])
    p = layout.plan(con)
    assert centre(p, "LAZ")["state"] == "dirba" and centre(p, "LAZ")["task"]["name"] == "Pjovimas"
    clock.set("2026-10-26T07:00:00+00:00")
    tasks.stop(con, s["op"], s["t"]["cut"], 1)                    # dalinis perdavimas: 1 detalė į LNK
    p = layout.plan(con)
    assert centre(p, "LNK")["waiting"] == 1
    assert p["flows"] == [{"from_id": s["c"]["LAZ"], "to_id": s["c"]["LNK"], "qty": 1, "n": 1}]
    tasks.start(con, s["op"], s["t"]["bend"])
    tasks.pause(con, s["op"], s["t"]["bend"], "gedimas")
    clock.set("2026-10-26T08:30:00+00:00")
    al = centre(layout.plan(con), "LNK")["alerts"]
    assert al[0]["severity"] == "red" and al[0]["text"].startswith("Įrangos gedimas jau 1 val. 30 min.")
    ncr.report(con, s["op"], {"task_id": s["t"]["bend"], "category": "lenkimas", "description": "Kampas"})
    assert any("neatitiktis" in x["text"] for x in centre(layout.plan(con), "LNK")["alerts"])


def test_planuota_pauze_nera_ispejimas(con, plant, clock):
    s = plant
    tasks.start(con, s["op"], s["t"]["cut"])
    tasks.pause(con, s["op"], s["t"]["cut"], "pamaina")
    clock.set("2026-10-26T20:00:00+00:00")
    assert centre(layout.plan(con), "LAZ")["alerts"] == []


def test_projekto_kelias(con, plant):
    p = layout.plan(con, plant["pid"])["project"]
    c = plant["c"]
    assert {(e["from_id"], e["to_id"]) for e in p["edges"]} == {(c["LAZ"], c["LNK"]), (c["LNK"], c["SV1"])}
    assert p["centres"][c["LAZ"]] == {"done": 0, "open": 1, "running": 0}


def test_isdestymo_saugojimas(con, plant):
    s = plant
    layout.save(con, None, {"areas": [{"id": s["svb"], "x": 0, "y": 40, "w": 60, "h": 20}],
                            "centres": [{"id": s["c"]["SV1"], "x": 30, "y": 5, "w": 10, "h": 8}]})
    p = layout.plan(con)
    sv = next(a for a in p["areas"] if a["code"] == "SVB")
    assert sv["box"] == {"x": 0, "y": 40, "w": 60, "h": 20} and centre(p, "SV1")["box"]["x"] == 30
    with pytest.raises(RuleError):
        layout.save(con, None, {"areas": [{"id": s["svb"], "x": -5, "y": 0, "w": 10, "h": 10}]})
    layout.save(con, None, {"reset": True})
    assert next(a for a in layout.plan(con)["areas"] if a["code"] == "SVB")["auto"]


def test_api(sample_client):
    c = sample_client
    login(c, "meistras")
    p = c.get("/api/floor/plan").json()
    assert len(p["areas"]) == 6 and sum(len(a["centres"]) for a in p["areas"]) == 25
    assert c.put("/api/floor/layout", json={"reset": True}).status_code == 403
    login(c, "admin")
    assert c.put("/api/floor/layout", json={"reset": True}).status_code == 200
