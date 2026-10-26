"""Rolės ir teisės: redaguojamos rolės, individualios išimtys, veiksmai pagal
barą (meistras – savo baruose), paskutinis administratorius, žurnalas, pradžia."""

import pytest
from conftest import login

from vmgt.services import RuleError, auth, home, planner, projects, routing, tasks


def U(con, login_, role, centres=None):
    uid = auth.create_user(con, login_, login_.title(), role, "x", centres=centres)
    return auth.load_perms(con, dict(con.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()))


@pytest.fixture
def setup(con, clock):
    clock.set("2026-10-26T06:00:00+00:00")
    auth.ensure_roles(con)
    mab = projects.save_area(con, None, {"code": "MAB", "name": "Mechaninis"})
    dzb = projects.save_area(con, None, {"code": "DZB", "name": "Dažymas"})
    laz = projects.save_centre(con, None, {"code": "LAZ", "name": "Lazeris", "kind": "pjovimas", "area_id": mab})
    daz = projects.save_centre(con, None, {"code": "DAZ", "name": "Dažymas", "kind": "dazymas", "area_id": dzb})
    pid = projects.save_project(con, None, {"code": "P1", "name": "Rėmai", "status": "vykdomas"})
    a = projects.save_assembly(con, None, pid, {"code": "100", "name": "Rėmas"})
    t1 = tasks.create_task(con, None, {"project_id": pid, "assembly_id": a, "centre_id": laz, "name": "Pjovimas", "seq": 10})
    t2 = tasks.create_task(con, None, {"project_id": pid, "assembly_id": a, "centre_id": daz, "name": "Dažymas", "seq": 20})
    routing.release(con, None, a)
    admin = U(con, "adm", "admin")
    return {"admin": admin, "t1": t1, "t2": t2, "laz": laz, "daz": daz}


def test_rolės_teisės_keičiamos_ir_galioja(con, setup):
    adm = setup["admin"]["id"]
    s = U(con, "sand", "sandelis")
    assert "ncr_report" not in auth.perms_of(s)
    auth.save_role(con, adm, "sandelis", {"perms": ["view", "receive", "ncr_report"]})
    assert "ncr_report" in auth.perms_of(auth.load_perms(con, dict(s)))
    with pytest.raises(RuleError, match="visada turi visas"):
        auth.save_role(con, adm, "admin", {"perms": ["view"]})
    code = auth.save_role(con, adm, "", {"code": "meistras_dazymo", "name": "Dažymo meistras", "copy_from": "meistras"}, new=True)
    assert auth.list_roles(con)[-1]["code"] == code and "ack_rev" in auth.list_roles(con)[-1]["perms"]
    U(con, "dm", code)
    with pytest.raises(RuleError, match="turi 1 vartotojai"):
        auth.delete_role(con, adm, code)
    with pytest.raises(RuleError, match="Įprastos rolės"):
        auth.delete_role(con, adm, "sandelis")
    log = auth.access_log(con, "role")
    assert any("Rolė Sandėlininkas: + Registruoti neatitiktis" == x["summary"] for x in log)


def test_individualios_isimtys_ir_paskutinis_admin(con, setup):
    adm = setup["admin"]
    m = U(con, "mst", "meistras", ["MAB"])
    auth.update_user(con, m["id"], adm["id"], perm_add=["quality"], perm_remove=["receive"])
    m = auth.load_perms(con, dict(con.execute("SELECT * FROM users WHERE id=?", (m["id"],)).fetchone()))
    assert "quality" in auth.perms_of(m) and "receive" not in auth.perms_of(m)
    d = {x["perm"]: x for mod in auth.describe(con, m) for x in mod["items"]}
    assert d["quality"]["source"] == "papildomai" and d["receive"]["source"] == "atimta" and d["plan"]["where"] == "MAB"
    log = auth.access_log(con, "user", m["id"])
    assert "papildomai suteikta: Kokybės kontrolė" in log[0]["summary"] and "atimta: Gavimas" in log[0]["summary"]
    with pytest.raises(RuleError, match="paskutiniam administratoriui"):
        auth.update_user(con, adm["id"], adm["id"], role="perziura")
    with pytest.raises(RuleError, match="paskutiniam administratoriui"):
        auth.update_user(con, adm["id"], adm["id"], active=False)
    auth.update_user(con, m["id"], adm["id"], perm_add=["admin"])          # dabar du administratoriai
    auth.update_user(con, adm["id"], adm["id"], active=False)


def test_meistras_tik_savo_baruose(con, setup):
    s = setup
    m = U(con, "mst", "meistras", ["MAB"])
    tasks.approve_queue(con, None, s["laz"])
    tasks.approve_queue(con, None, s["daz"])
    planner.apply(con, m, {"kind": "queue", "task_id": s["t1"], "where": "top"})
    with pytest.raises(RuleError, match="ne jūsų baras"):
        planner.apply(con, m, {"kind": "queue", "task_id": s["t2"], "where": "top"})
    assert auth.can_at(m, "ack_rev", "LAZ", "MAB") and not auth.can_at(m, "ack_rev", "DAZ", "DZB")
    assert auth.can_at(m, "view", "DAZ", "DZB")                            # matyti – visur
    # rolė „visi barai“ – planuotojas, ir meistras, jei rolei pakeista apimtis
    auth.save_role(con, s["admin"]["id"], "meistras", {"scope": "all"})
    assert auth.can_at(auth.load_perms(con, dict(m)), "ack_rev", "DAZ", "DZB")
    # terminalas ribojamas visada
    op = U(con, "op", "operatorius", ["MAB"])
    assert auth.can_at(op, "execute", "LAZ", "MAB") and not auth.can_at(op, "execute", "DAZ", "DZB")


def test_pradzios_plyteles_pagal_role(con, setup):
    op = U(con, "op", "operatorius", ["MAB"])
    keys = [t["key"] for t in home.tiles(con, op)["tiles"]]
    assert "projektai" not in keys and "admin" not in keys and "gamyba" in keys
    m = U(con, "mst", "meistras", ["DZB"])
    tasks.approve_queue  # eilės dar nepatvirtintos: LAZ – ne jo baras, DAZ – jo
    pl = next(t for t in home.tiles(con, m)["tiles"] if t["key"] == "planavimas")
    assert pl["counters"][0]["n"] == 1 and pl["counters"][0]["label"] == "laukia patvirtinimo eilėse"
    adm = {t["key"] for t in home.tiles(con, setup["admin"])["tiles"]}
    assert {"projektai", "planavimas", "gamyba", "kokybe", "tiekimas", "analitika", "admin"} <= adm


def test_api(sample_client):
    c = sample_client
    login(c, "admin")
    roles = c.get("/api/roles").json()
    assert next(r for r in roles if r["code"] == "meistras")["scope"] == "own"
    uid = next(u["id"] for u in c.get("/api/users").json() if u["login"] == "planuotojas")
    assert c.put(f"/api/users/{uid}", json={"perm_add": ["ncr_manage"]}).status_code == 200
    card = c.get(f"/api/users/{uid}").json()
    assert card["perm_add"] == ["ncr_manage"] and card["log"][0]["summary"].startswith("Tomas Planas")
    assert c.get("/api/home").status_code == 200
    login(c, "planuotojas")
    assert "ncr_manage" in c.get("/api/me").json()["user"]["perms"]
    assert c.get("/api/roles").status_code == 403
    login(c, "meistras")
    assert c.post("/api/plan/DAZ-01/approve").status_code == 409          # ne jo baras
    assert c.post("/api/plan/LAZ-01/approve").status_code == 200
    assert c.post("/api/calendar/days", json={"scope": "factory", "from": "2026-12-01", "kind": "nedarbo"}).status_code == 409
    assert c.get("/api/home").status_code == 200
