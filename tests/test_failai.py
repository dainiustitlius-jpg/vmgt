"""Technologo failai prie operacijų ir technologo darbo aplinka."""

import pytest
from conftest import login

from vmgt.services import RuleError, auth, ncfiles, projects, routing, tasks


@pytest.fixture
def tech(con, clock, tmp_path):
    admin = auth.create_user(con, "admin", "Admin", "admin", "x")
    techn = auth.create_user(con, "tech", "Tech", "technologas", "x")
    U = lambda i: dict(con.execute("SELECT * FROM users WHERE id=?", (i,)).fetchone())
    laz = projects.save_centre(con, admin, {"code": "LAZ", "name": "Lazeris", "kind": "pjovimas", "needs_files": 1})
    sv = projects.save_centre(con, admin, {"code": "SV", "name": "Suvirinimas", "kind": "suvirinimas"})
    pid = projects.save_project(con, admin, {"code": "P1", "name": "Projektas"})
    a = projects.save_assembly(con, admin, pid, {"code": "100", "name": "Rėmas", "qty": 2})
    projects.save_phase(con, admin, pid, {"assembly_id": a, "kind": "technologija", "owner_id": techn})
    cut = tasks.create_task(con, admin, {"project_id": pid, "assembly_id": a, "centre_id": laz, "seq": 10,
                                         "name": "Pjovimas", "part_no": "D-1", "qty_plan": 4, "norm_min": 5})
    weld = tasks.create_task(con, admin, {"project_id": pid, "assembly_id": a, "centre_id": sv, "seq": 20,
                                          "name": "Suvirinimas", "qty_plan": 2, "norm_min": 60})
    return {"nc": tmp_path / "nc", "u": U(techn), "admin": U(admin), "a": a, "pid": pid, "cut": cut, "weld": weld,
            "laz": laz, "sv": sv}


def test_katalogu_struktura_ir_versijos(con, tech):
    nc, u, cut = tech["nc"], tech["u"], tech["cut"]
    f1 = ncfiles.save(con, nc, u, cut, "D-1 išklotinė.dxf", b"0\nEOF\n")
    assert f1["path"] == "P1/100/LAZ/D-1_i_klotin_v1.dxf" and f1["kind"] == "cad" and f1["version"] == 1
    assert (nc / "P1" / "100" / "LAZ" / "D-1_i_klotin_v1.dxf").read_bytes() == b"0\nEOF\n"
    with pytest.raises(RuleError, match="jau toks pat"):
        ncfiles.save(con, nc, u, cut, "D-1 išklotinė.dxf", b"0\nEOF\n")
    f2 = ncfiles.save(con, nc, u, cut, "D-1 išklotinė.dxf", b"0\nEOF\n\n")
    assert f2["version"] == 2
    cur = ncfiles.list_for(con, [cut])[cut]
    assert [f["version"] for f in cur] == [2]                    # galioja tik naujausia
    assert len(ncfiles.list_for(con, [cut], history=True)[cut]) == 2
    assert (nc / "P1" / "100" / "LAZ" / "D-1_i_klotin_v1.dxf").exists()   # senoji lieka diske


def test_neleistinas_tipas_ir_kelias(con, tech):
    with pytest.raises(RuleError, match="neleidžiamas"):
        ncfiles.save(con, tech["nc"], tech["u"], tech["cut"], "virusas.exe", b"MZ")
    f = ncfiles.save(con, tech["nc"], tech["u"], tech["cut"], "..\\..\\..\\windows\\prog.nc", b"M30")
    assert f["path"] == "P1/100/LAZ/prog_v1.nc"                  # iš katalogo neišeina


def test_isleidimui_reikia_failo_stakliems(con, tech):
    errs = routing.check(con, tech["a"])["errors"]
    assert any("LAZ · Pjovimas (D-1): nepridėtas" in e for e in errs)
    ncfiles.save(con, tech["nc"], tech["u"], tech["cut"], "D-1.dxf", b"0")
    assert routing.check(con, tech["a"])["errors"] == []         # rankinei stočiai failo nereikia


def test_pakeistas_po_isleidimo_laukia_meistro(con, tech):
    s = tech
    ncfiles.save(con, s["nc"], s["u"], s["cut"], "D-1.dxf", b"0")
    routing.release(con, s["u"]["id"], s["a"])
    tasks.approve_queue(con, s["admin"]["id"], s["laz"])
    t = tasks._task(con, s["cut"])
    assert tasks.block_reason(con, t) is None
    ncfiles.save(con, s["nc"], s["u"], s["cut"], "D-1.dxf", b"01", "pakeista skylė")
    assert "D-1.dxf v2" in tasks.block_reason(con, t) and "meistro" in tasks.block_reason(con, t)
    with pytest.raises(RuleError, match="Keisti maršrutą"):     # pašalinti išleistame – tik grąžinus
        ncfiles.remove(con, s["u"], ncfiles.list_for(con, [s["cut"]])[s["cut"]][0]["id"])
    assert ncfiles.ack(con, s["admin"], s["cut"]) == 1
    assert tasks.block_reason(con, t) is None


def test_kopijuoti_marsruta_su_failais(con, tech):
    s = tech
    ncfiles.save(con, s["nc"], s["u"], s["cut"], "D-1.dxf", b"0")
    b = projects.save_assembly(con, s["admin"]["id"], s["pid"], {"code": "200", "name": "Rėmas 2", "qty": 6})
    r = routing.copy_route(con, s["nc"], s["u"], s["a"], b)
    assert r == {"ops": 2, "files": 1}
    ops = con.execute("SELECT part_no, qty_plan FROM tasks WHERE assembly_id=? ORDER BY seq", (b,)).fetchall()
    assert [tuple(o) for o in ops] == [("D-1", 12), ("", 6)]    # 4 vnt. 2 mazgams → 12 vnt. 6 mazgams
    assert (s["nc"] / "P1" / "200" / "LAZ" / "D-1_v1.dxf").exists()
    routing.release(con, s["u"]["id"], b)
    with pytest.raises(RuleError, match="Keisti maršrutą"):
        routing.copy_route(con, s["nc"], s["u"], s["a"], b)


def test_technologo_darbu_sarasas(con, tech):
    s = tech
    projects.save_assembly(con, s["admin"]["id"], s["pid"], {"code": "300", "name": "Tuščias"})
    w = {x["code"]: x for x in routing.worklist(con)}
    assert w["100"]["state"] == "juodrastis" and w["100"]["no_file"] == 1 and w["100"]["errors"] == 1
    assert w["300"]["state"] == "nera" and w["100"]["tech_owner"] == "Tech"
    assert [x["code"] for x in routing.worklist(con, s["u"]["id"])] == ["100"]   # mano – pagal technologijos etapą


def test_api(sample_client):
    c = sample_client
    login(c, "technologas")
    w = c.get("/api/tech/worklist").json()
    poz = next(x for x in w if x["project_code"] == "P-24121" and x["code"] == "200")
    assert poz["state"] == "juodrastis" and poz["no_file"] == 1
    r = c.get(f"/api/route/{poz['id']}").json()
    laz = r["branches"][1]["ops"][0]
    assert laz["files"][0]["name"] == "2210-202.dxf"
    fid = laz["files"][0]["id"]
    assert c.get(f"/api/files/{fid}").content.startswith(b"0\nSECTION")
    assert c.get("/api/me").json()["nc_share"]
    # operatorius: atsisiųsti gali, įkelti ir patvirtinti – ne
    login(c, pin="1111")
    assert c.get(f"/api/files/{fid}").status_code == 200
    assert c.post(f"/api/tasks/{laz['id']}/files", files={"file": ("x.nc", b"M30")}).status_code == 403
    # PLZ-01: plazmos programa pakeista po išleidimo – terminalas užrakintas, kol meistras patvirtins
    login(c, pin="9999")
    q = c.get("/api/terminal/PLZ-01").json()["queue"][0]
    assert q["files_pending"] and "meistro patvirtinimo" in q["lock"]
    assert c.post(f"/api/tasks/{q['id']}/ack_files").json() == {"acked": 1}
    assert c.get("/api/terminal/PLZ-01").json()["queue"][0]["lock"] is None
