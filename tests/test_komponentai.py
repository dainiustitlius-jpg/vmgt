"""Komponentų pirkimai: būsenos iš faktų, gavimai, importas, etapo eiga."""

import pytest
from conftest import login

from vmgt.services import RuleError, auth, components, projects, tasks


@pytest.fixture
def proj(con, clock):
    admin = auth.create_user(con, "admin", "Admin", "admin", "x")
    pid = projects.save_project(con, admin, {"code": "P1", "name": "Projektas"})
    a = projects.save_assembly(con, admin, pid, {"code": "300", "name": "Spinta"})
    ph = projects.save_phase(con, admin, pid, {"assembly_id": a, "kind": "komponentai"})
    return {"admin": admin, "pid": pid, "a": a, "ph": ph}


def C(con, cid):
    return components.decorate(components.get(con, cid), "2026-10-20")


def test_busena_isvedama_is_faktu(con, proj):
    cid = components.save(con, proj["admin"], {"project_id": proj["pid"], "assembly_id": proj["a"],
                                               "name": "PLC", "qty": 2, "need_date": "2026-10-24"})
    c = C(con, cid)
    assert c["status"] == "reikia" and c["risk"]            # reikia po 4 d., neužsakyta
    components.save(con, proj["admin"], {"po_no": "PO-1"}, cid)
    assert C(con, cid)["status"] == "uzsakyta"
    components.save(con, proj["admin"], {"promised_date": "2026-10-26"}, cid)
    c = C(con, cid)
    assert c["status"] == "patvirtinta" and c["risk"]        # atvyks vėliau nei reikia
    components.receive(con, proj["admin"], cid, 1)
    assert C(con, cid)["status"] == "dalinai"
    components.receive(con, proj["admin"], cid, 1)
    c = C(con, cid)
    assert c["status"] == "gauta" and not c["risk"] and not c["late"]


def test_veluoja_kai_pazadeta_data_praejo(con, proj):
    cid = components.save(con, proj["admin"], {"project_id": proj["pid"], "name": "Variklis", "po_no": "PO-2",
                                               "promised_date": "2026-10-18"})
    assert C(con, cid)["late"]


def test_daugiau_nei_uzsakyta_negaunama(con, proj):
    cid = components.save(con, proj["admin"], {"project_id": proj["pid"], "name": "Guolis", "qty": 4, "unit": "vnt"})
    components.receive(con, proj["admin"], cid, 3)
    with pytest.raises(RuleError, match="užsakyta tik 4"):
        components.receive(con, proj["admin"], cid, 2)
    assert [r["qty"] for r in components.receipts(con)] == [3]


def test_gauta_eilute_neatsaukiama(con, proj):
    cid = components.save(con, proj["admin"], {"project_id": proj["pid"], "name": "Guolis", "qty": 4})
    components.receive(con, proj["admin"], cid, 1)
    with pytest.raises(RuleError, match="atšaukti negalima"):
        components.cancel(con, proj["admin"], cid)


def test_etapas_seka_pirkimus(con, proj):
    st = lambda: con.execute("SELECT status FROM phases WHERE id=?", (proj["ph"],)).fetchone()[0]
    cid = components.save(con, proj["admin"], {"project_id": proj["pid"], "assembly_id": proj["a"], "name": "PLC"})
    assert st() == "planuota"                                 # dar neužsakyta
    components.save(con, proj["admin"], {"po_no": "PO-1"}, cid)
    assert st() == "vykdoma"
    components.receive(con, proj["admin"], cid, 1)
    assert st() == "baigta"
    # nauja negauta eilutė etapą vėl atidaro
    components.save(con, proj["admin"], {"project_id": proj["pid"], "assembly_id": proj["a"], "name": "HMI",
                                         "po_no": "PO-2"})
    assert st() == "vykdoma"


def test_terminalas_ispeja_apie_negautus(con, proj):
    c = projects.save_centre(con, proj["admin"], {"code": "EL", "name": "Elektra", "kind": "elektra"})
    t = tasks.create_task(con, proj["admin"], {"project_id": proj["pid"], "assembly_id": proj["a"],
                                               "centre_id": c, "name": "Montavimas"})
    tasks.approve_queue(con, proj["admin"], c)
    components.save(con, proj["admin"], {"project_id": proj["pid"], "assembly_id": proj["a"], "name": "PLC"})
    centre = dict(con.execute("SELECT * FROM work_centres WHERE id=?", (c,)).fetchone())
    q = tasks.terminal_view(con, centre)["queue"]
    assert q[0]["components_missing"] == 1 and q[0]["lock"] is None   # įspėja, bet neblokuoja


CSV = ("projektas;mazgas;prekes_kodas;pavadinimas;specifikacija;kiekis;vnt;tiekejas;uzsakymo_nr;eilute;uzsakyta;"
       "patvirtinta_data;reikia_iki;gauta_kiekis;gauta_data;vieta;pastaba\n")


def test_importas_atnaujina_ir_registruoja_tik_skirtuma(con, proj):
    u = {"id": proj["admin"]}
    line = "P1;300;EL-1;Kontaktorius;3RT2016;10;vnt;Tiekėjas;PO-9;1;2026-10-10;2026-10-22;2026-10-25;{got};{gd};A-3;\n"
    r = components.import_csv(con, u, CSV + line.format(got=0, gd=""))
    assert (r["created"], r["receipts"]) == (1, 0)
    r = components.import_csv(con, u, CSV + line.format(got=4, gd="2026-10-21"))
    assert (r["created"], r["updated"], r["receipts"]) == (0, 1, 1)
    r = components.import_csv(con, u, CSV + line.format(got=4, gd="2026-10-21"))   # tas pats failas dar kartą
    assert r["receipts"] == 0
    rec = components.receipts(con)
    assert [(x["qty"], x["at"][:10]) for x in rec] == [(4, "2026-10-21")]
    assert C(con, 1)["status"] == "dalinai"


def test_importas_viskas_arba_nieko(con, proj):
    bad = CSV + "P1;300;;Gerai;;1;vnt;;;;;;;;;;\nP1;999;;Blogas mazgas;;1;vnt;;;;;;;;;;\nNERA;;;X;;0;;;;;;;;;;;\n"
    r = components.import_csv(con, {"id": proj["admin"]}, bad)
    assert len(r["errors"]) == 3 and r["created"] == 0
    assert con.execute("SELECT COUNT(*) FROM components").fetchone()[0] == 0


def test_api_teises_ir_pavyzdziai(sample_client):
    login(sample_client, "sandelis")
    r = sample_client.get("/api/components").json()
    assert r["summary"]["total"] == 10 and r["summary"]["late"] >= 1
    open_ = [c for c in r["rows"] if c["status"] in ("uzsakyta", "patvirtinta", "dalinai")][0]
    assert sample_client.post(f"/api/components/{open_['id']}/receive", json={"qty": 1}).status_code == 200
    assert sample_client.post("/api/components", json={"project_id": 1, "name": "X"}).status_code == 403
    login(sample_client, "pirkimai")
    assert sample_client.post("/api/components", json={"project_id": 1, "name": "X"}).status_code == 200
    login(sample_client, "op1", pin="1111")
    assert sample_client.get("/api/components").status_code == 403
