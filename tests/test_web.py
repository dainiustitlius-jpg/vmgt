"""API su pavyzdiniais duomenimis: prisijungimas, teisės, importas, analitika."""

from conftest import login

from vmgt.services import importer


def test_be_prisijungimo_401(sample_client):
    assert sample_client.get("/api/projects").status_code == 401


def test_neteisingas_slaptazodis_ir_pin(sample_client):
    assert sample_client.post("/api/login", json={"login": "admin", "password": "blogas"}).status_code == 409
    assert sample_client.post("/api/login", json={"pin": "0000"}).status_code == 409


def test_pavyzdiniai_duomenys(sample_client):
    login(sample_client, "admin")
    ps = sample_client.get("/api/projects").json()
    assert [p["code"] for p in ps] == ["P-24117", "P-24121", "P-24130"]
    assert all("PAVYZDYS" in p["name"] for p in ps)
    floor = {s["centre"]["code"]: s for s in sample_client.get("/api/floor").json()["centres"]}
    assert floor["SV-01"]["state"] == "dirba"
    assert floor["LNK-01"]["state"] == "pristabdyta"
    assert floor["SUR-01"]["lock"].startswith("Laukiama mazgų")


def test_operatorius_mato_tik_terminala(sample_client):
    u = login(sample_client, pin="3333")
    assert u["login"] == "op3"
    assert sample_client.get("/api/projects").status_code == 403
    assert sample_client.get("/api/terminal/LAZ-01").status_code == 403   # ne jo centras
    t = sample_client.get("/api/terminal/SV-01").json()
    assert t["running"]["name"] == "Rėmo suvirinimas"


def test_terminalo_ciklas_per_api(sample_client):
    login(sample_client, pin="3333")
    tid = sample_client.get("/api/terminal/SV-01").json()["running"]["id"]
    assert sample_client.post(f"/api/terminal/{tid}/pause", json={"reason": "gedimas"}).status_code == 200
    assert sample_client.post(f"/api/terminal/{tid}/resume").status_code == 200
    r = sample_client.post(f"/api/terminal/{tid}/stop", json={"good": 1}).json()
    assert r["status"] == "baigta"
    assert sample_client.post(f"/api/terminal/{tid}/stop", json={"good": 1}).status_code == 409


def test_dazymas_uzrakintas_revizijos(sample_client):
    login(sample_client, "admin")
    plan = sample_client.get("/api/plan/DAZ-01").json()["tasks"]
    remas = [t for t in plan if t["name"].startswith("Dažymas RAL 7035")][0]
    assert remas["drawing_rev"] == "A"
    # nepatvirtintos P-24121 užduotys planuotojui matomos
    assert any(not t["approved"] for t in plan)


def test_importas_viskas_arba_nieko(sample_client):
    login(sample_client, "technologas")
    bad = importer.template() + "P-9;Bandymas;10;Rėmas;10;NERA;Pjovimas;;1;5;;\n"
    r = sample_client.post("/api/import", files={"file": ("a.csv", bad.encode())}, data={"dry_run": "0"}).json()
    assert r["errors"] and r["tasks_new"] == 0
    ok = importer.template() + "P-9;Bandymas;10;Rėmas;10;LAZ-01;Pjovimas;;1;5,5;;\nP-9;Bandymas;10;Rėmas;20;SV-01;Suvirinimas;;1;30;;\n"
    r = sample_client.post("/api/import", files={"file": ("a.csv", ok.encode())}, data={"dry_run": "0"}).json()
    assert r == {"rows": 2, "errors": [], "projects_new": 1, "assemblies_new": 1, "tasks_new": 2}
    login(sample_client, "admin")
    p = [x for x in sample_client.get("/api/projects").json() if x["code"] == "P-9"][0]
    assert p["tasks_total"] == 2


def test_teises(sample_client):
    login(sample_client, "kokybe")
    assert sample_client.post("/api/projects", json={"code": "X", "name": "X"}).status_code == 403
    n = sample_client.get("/api/ncr").json()
    assert isinstance(n, list)
    login(sample_client, "planuotojas")
    assert sample_client.post("/api/plan/DAZ-01/approve").json()["approved"] == 1   # P-24121 dažymas


def test_analitika(sample_client):
    login(sample_client, "vadovas")
    a = sample_client.get("/api/analytics").json()
    assert a["totals"]["tasks_done"] == 3
    planned = {p["reason"]: p["planned"] for p in a["pauses"]}
    assert planned["pamaina"] is True and planned["medziaga"] is False
    lnk = [c for c in a["centres"] if c["code"] == "LNK-01"][0]
    assert lnk["pause_s"] > 0


def test_brezinio_failas(sample_client):
    login(sample_client, "op1", pin="1111")
    r = sample_client.get("/api/drawings/1023-100/file")
    assert r.status_code == 200 and r.content.startswith(b"%PDF")


def test_paskutinio_admino_neatimsi(sample_client):
    login(sample_client, "admin")
    me = sample_client.get("/api/me").json()["user"]
    r = sample_client.put(f"/api/users/{me['id']}", json={"role": "operatorius"})
    assert r.status_code == 409
