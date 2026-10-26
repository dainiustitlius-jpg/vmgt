"""Kokybė (EN 1090 / ISO 3834): patikros maršrute, medžiagų lydiniai,
suvirintojų kvalifikacijos ir WPS, dosjė, NCR 8D."""

import io
import zipfile

import pytest
from conftest import login

from vmgt.services import RuleError, auth, drawings, projects, quality, routing, tasks


@pytest.fixture
def q(con, clock, tmp_path):
    clock.set("2026-10-26T06:00:00+00:00")
    U = lambda login, role, centres=None: dict(con.execute("SELECT * FROM users WHERE id=?", (
        auth.create_user(con, login, login.title(), role, "x", centres=centres),)).fetchone())
    users = {"op": U("op", "operatorius"), "suv": U("suv", "operatorius"), "kok": U("kok", "kokybe"),
             "m": U("m", "meistras"), "tech": U("tech", "technologas")}
    laz = projects.save_centre(con, None, {"code": "LAZ", "name": "Lazeris", "kind": "pjovimas"})
    sv = projects.save_centre(con, None, {"code": "SV", "name": "Suvirinimas", "kind": "suvirinimas"})
    pid = projects.save_project(con, None, {"code": "P1", "name": "Rėmai", "status": "vykdomas", "exc_class": "EXC2"})
    a = projects.save_assembly(con, None, pid, {"code": "100", "name": "Rėmas"})
    cut = tasks.create_task(con, None, {"project_id": pid, "assembly_id": a, "centre_id": laz, "seq": 10,
                                        "name": "Pjovimas", "part_no": "D1", "qty_plan": 2, "norm_min": 5})
    weld = tasks.create_task(con, None, {"project_id": pid, "assembly_id": a, "centre_id": sv, "seq": 20,
                                         "name": "Suvirinimas", "qty_plan": 1, "norm_min": 60})
    wps = quality.save_wps(con, tmp_path, None, {"code": "WPS-135-01", "process": "135", "material_group": "1.1"})
    return {**users, "pid": pid, "a": a, "cut": cut, "weld": weld, "wps": wps, "laz": laz, "sv": sv,
            "files": tmp_path / "files"}


def ready(con, s):
    tasks.update_task(con, None, s["weld"], {"wps_id": s["wps"]})
    routing.release(con, None, s["a"])
    tasks.approve_queue(con, None, s["laz"])
    tasks.approve_queue(con, None, s["sv"])


def lot(con, s, **kw):
    return quality.save_lot(con, s["files"], s["kok"], {"heat_no": "H-123", "material": "S355J2+N",
                                                       "product": "lakštas t10", "cert_no": "C-1", **kw},
                            drawings.sample_pdf(["3.1"]), "c.pdf")


def test_exc2_suvirinimui_reikia_wps(con, q):
    with pytest.raises(RuleError, match="nenurodytas WPS"):
        routing.release(con, None, q["a"])
    assert any("suvirinimo patikros" in w for w in routing.check(con, q["a"])["warnings"])
    tasks.update_task(con, None, q["weld"], {"wps_id": q["wps"]})
    routing.release(con, None, q["a"])


def test_suvirintojo_kvalifikacija(con, q, clock):
    s = q
    ready(con, s)
    lot_id = lot(con, s)
    tasks.start(con, s["op"], s["cut"])
    quality.use_lot(con, s["op"], s["cut"], lot_id)
    tasks.stop(con, s["op"], s["cut"], 2)
    with pytest.raises(RuleError, match="nėra kvalifikacijos"):
        tasks.start(con, s["suv"], s["weld"])
    quality.save_qualification(con, s["files"], None, {"user_id": s["suv"]["id"], "process": "135",
                                                       "material_group": "1.1", "valid_until": "2026-10-01"})
    with pytest.raises(RuleError, match="baigė galioti 2026-10-01"):
        tasks.start(con, s["suv"], s["weld"])
    quality.save_qualification(con, s["files"], None, {"user_id": s["suv"]["id"], "process": "135",
                                                       "material_group": "1.1", "valid_until": "2027-10-01"})
    tasks.start(con, s["suv"], s["weld"])
    # terminale užraktas rodomas tam, kas prisijungęs
    centre = dict(con.execute("SELECT * FROM work_centres WHERE id=?", (s["sv"],)).fetchone())
    assert tasks.terminal_view(con, centre, s["suv"])["running"]["wps"]["code"] == "WPS-135-01"


def test_lydinys_privalomas_exc2_pjovimui(con, q):
    s = q
    ready(con, s)
    tasks.start(con, s["op"], s["cut"])
    with pytest.raises(RuleError, match="iš kurio lydinio"):
        tasks.stop(con, s["op"], s["cut"], 2)
    bad = lot(con, s, heat_no="H-BAD")
    quality.set_lot_status(con, s["kok"], bad, "blokuota", "Sertifikate S235 vietoj S355")
    with pytest.raises(RuleError, match="blokuotas"):
        quality.use_lot(con, s["op"], s["cut"], bad)
    quality.use_lot(con, s["op"], s["cut"], lot(con, s))
    assert tasks.stop(con, s["op"], s["cut"], 2)["moved"] == 2


def test_savikontrole_ir_nok(con, q):
    s = q
    c = quality.add_check(con, None, s["cut"], {"name": "Ilgis", "kind": "measure", "nominal": 1200, "tol_minus": 1,
                                                "tol_plus": 1, "unit": "mm", "performer": "operator"})
    ready(con, s)
    quality.use_lot(con, s["op"], s["cut"], lot(con, s))
    tasks.start(con, s["op"], s["cut"])
    with pytest.raises(RuleError, match="patikrų rezultatus: Ilgis"):
        tasks.stop(con, s["op"], s["cut"], 2)
    r = quality.record(con, s["op"], c, value="1202,5")
    assert not r["ok"] and r["ncr_id"]
    n = con.execute("SELECT category, description, check_id FROM ncr WHERE id=?", (r["ncr_id"],)).fetchone()
    assert n[0] == "matmenys" and "1202,5 mm (reikia 1200 ±1 mm)" in n[1] and n[2] == c
    with pytest.raises(RuleError, match="patikrų rezultatus"):
        tasks.stop(con, s["op"], s["cut"], 2)                      # NOK – vis dar neužbaigta
    assert quality.record(con, s["op"], c, value=1200.4)["ok"]     # pataisyta ir pakartota
    tasks.stop(con, s["op"], s["cut"], 2)
    assert len(con.execute("SELECT * FROM check_results WHERE check_id=?", (c,)).fetchall()) == 2


def test_kokybes_kontrole_sulaiko_detales(con, q):
    s = q
    c = quality.add_check(con, None, s["cut"], {"name": "Pjūvio kokybė (EN ISO 9013)", "performer": "qc"})
    ready(con, s)
    quality.save_qualification(con, s["files"], None, {"user_id": s["suv"]["id"], "process": "135",
                                                       "material_group": "1.1", "valid_until": "2027-01-01"})
    quality.use_lot(con, s["op"], s["cut"], lot(con, s))
    tasks.start(con, s["op"], s["cut"])
    with pytest.raises(RuleError, match="kokybės inžinierius"):
        quality.record(con, s["op"], c, ok=True)
    r = tasks.stop(con, s["op"], s["cut"], 2)                      # operatorius baigia – detalės sulaikomos
    assert r["moved"] == 0 and r["held"] == ["Pjūvio kokybė (EN ISO 9013)"]
    with pytest.raises(RuleError, match="Laukiama kokybės kontrolės: LAZ · Pjovimas"):
        tasks.start(con, s["suv"], s["weld"])
    assert [x["name"] for x in quality.qc_queue(con)] == ["Pjūvio kokybė (EN ISO 9013)"]
    assert quality.record(con, s["kok"], c, ok=True)["released"] == 2
    assert con.execute("SELECT SUM(qty) FROM transfers WHERE from_task_id=?", (s["cut"],)).fetchone()[0] == 2
    tasks.start(con, s["suv"], s["weld"])
    assert quality.release_transfers(con, None, s["cut"]) == 0     # pakartotinai nedubliuoja


def test_isimtis_ir_patikros_salinimas(con, q):
    s = q
    c = quality.add_check(con, None, s["weld"], {"name": "Siūlių VT", "performer": "qc"})
    ready(con, s)
    with pytest.raises(RuleError, match="Keisti maršrutą"):
        quality.remove_check(con, None, c)
    with pytest.raises(RuleError, match="meistras arba kokybės"):
        quality.waive(con, s["op"], c, "x")
    with pytest.raises(RuleError, match="priežastį"):
        quality.waive(con, s["m"], c, " ")
    quality.waive(con, s["m"], c, "Užsakovas sutiko – patikra gamykloje pas užsakovą")
    assert con.execute("SELECT status FROM task_checks WHERE id=?", (c,)).fetchone()[0] == "isimtis"


def test_dosje(con, q, tmp_path):
    s = q
    quality.add_check(con, None, s["weld"], {"name": "Siūlių VT", "performer": "qc"})
    ready(con, s)
    quality.save_qualification(con, s["files"], None, {"user_id": s["suv"]["id"], "process": "135",
                                                       "material_group": "1.1", "valid_until": "2027-01-01",
                                                       "cert_no": "Q-77"}, drawings.sample_pdf(["Q"]))
    quality.use_lot(con, s["op"], s["cut"], lot(con, s))
    tasks.start(con, s["op"], s["cut"])
    tasks.stop(con, s["op"], s["cut"], 2)
    tasks.start(con, s["suv"], s["weld"])
    tasks.stop(con, s["suv"], s["weld"], 1)
    d = quality.dossier(con, s["pid"])
    assert d["materials"][0]["heat_no"] == "H-123" and d["materials"][0]["part"] == "D1"
    assert d["welding"][0]["welder"] == "Suv" and d["welding"][0]["qualification"]["cert_no"] == "Q-77"
    assert not d["complete"] and any("Siūlių VT: patikra neužbaigta" in g for g in d["gaps"])
    z = zipfile.ZipFile(io.BytesIO(quality.dossier_zip(con, s["files"], s["pid"])))
    names = z.namelist()
    assert "turinys.csv" in names and any(n.startswith("sertifikatai/H-123") for n in names)
    assert any(n.startswith("kvalifikacijos/") for n in names)


def test_api_ncr_8d(sample_client):
    c = sample_client
    login(c, pin="1111")
    nid = c.post("/api/ncr", json={"project_id": 1, "category": "suvirinimas", "description": "Pora"}).json()["id"]
    assert c.post(f"/api/ncr/{nid}/files", files={"file": ("foto.jpg", b"\xff\xd8jpeg")}).status_code == 200
    login(c, "kokybe")
    assert c.post(f"/api/ncr/{nid}/close", json={"resolution": "Ok"}).status_code == 409
    r = c.post(f"/api/ncr/{nid}/close", json={"resolution": "Siūlė perdaryta", "root_cause": "Per didelė srovė",
                                              "disposition": "remontuoti", "corrective": "WPS parametrų patikra"})
    assert r.status_code == 200
    n = c.get(f"/api/ncr/{nid}").json()
    assert n["status"] == "uzdaryta" and n["disposition_label"] == "Remontuoti" and len(n["files"]) == 1
    assert c.get(f"/api/ncr_files/{n['files'][0]['id']}").content == b"\xff\xd8jpeg"
