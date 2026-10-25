"""Gamybos barai: centrų grupavimas, priskyrimas baru, cecho ir analitikos grupės."""

import pytest
from conftest import login

from vmgt.services import RuleError, auth, projects


def test_baro_kodas_suteikia_visus_jo_centrus():
    u = {"centres": '["SVB"]'}
    assert auth.can_centre(u, "SV-07", "SVB")
    assert not auth.can_centre(u, "LAZ-01", "MAB")
    assert auth.can_centre({"centres": '["LAZ-01"]'}, "LAZ-01", "MAB")
    assert auth.can_centre({"centres": "[]"}, "LAZ-01", "MAB")       # tuščias – visi


def test_kodas_neturi_sutapti_su_centru(con, clock):
    projects.save_centre(con, None, {"code": "X1", "name": "Centras"})
    with pytest.raises(RuleError, match="darbo centrui"):
        projects.save_area(con, None, {"code": "X1", "name": "Baras"})
    projects.save_area(con, None, {"code": "B1", "name": "Baras"})
    with pytest.raises(RuleError, match="barui"):
        projects.save_centre(con, None, {"code": "B1", "name": "Centras"})


def test_centrai_rikiuojami_pagal_barus(con, clock):
    b2 = projects.save_area(con, None, {"code": "B2", "name": "Antras"})
    b1 = projects.save_area(con, None, {"code": "B1", "name": "Pirmas"})
    con.execute("UPDATE areas SET sort=1 WHERE id=?", (b2,)); con.execute("UPDATE areas SET sort=2 WHERE id=?", (b1,))
    projects.save_centre(con, None, {"code": "C-B1", "name": "x", "area_id": b1})
    projects.save_centre(con, None, {"code": "C-B2", "name": "x", "area_id": b2})
    projects.save_centre(con, None, {"code": "C-0", "name": "be baro"})
    assert [(c["code"], c["area_code"]) for c in projects.list_centres(con)] == \
        [("C-B2", "B2"), ("C-B1", "B1"), ("C-0", None)]


def test_cechas_ir_analitika_su_barais(sample_client):
    login(sample_client, "vadovas")
    f = sample_client.get("/api/floor").json()
    assert [a["code"] for a in f["areas"]] == ["MAB", "TKB", "SVB", "DZB", "ATB", "TIS"]
    by = {}
    for s in f["centres"]:
        by.setdefault(s["centre"]["area_code"], []).append(s["centre"]["code"])
    assert len(by["SVB"]) == 10 and by["DZB"] == ["SML-01", "DAZ-01", "DAZ-02"]
    a = sample_client.get("/api/analytics").json()
    names = {x["name"]: x for x in a["areas"]}
    assert names["Suvirinimo baras"]["work_s"] > 0


def test_suvirintojas_dirba_bet_kurioje_baro_stotyje(sample_client):
    login(sample_client, pin="3333")                     # op3: priskirtas barui SVB
    codes = [c["code"] for c in sample_client.get("/api/centres").json()]
    assert codes == [f"SV-{i:02d}" for i in range(1, 11)]
    assert sample_client.get("/api/terminal/SV-07").status_code == 200
    assert sample_client.get("/api/terminal/DAZ-01").status_code == 403


def test_administratorius_tvarko_barus(sample_client):
    login(sample_client, "admin")
    aid = sample_client.post("/api/areas", json={"code": "NAU", "name": "Naujas baras"}).json()["id"]
    c = [x for x in sample_client.get("/api/centres?all=1").json() if x["code"] == "TST-01"][0]
    assert sample_client.put(f"/api/centres/{c['id']}", json={"area_id": aid}).status_code == 200
    c = [x for x in sample_client.get("/api/centres?all=1").json() if x["code"] == "TST-01"][0]
    assert c["area_code"] == "NAU"
    login(sample_client, "vadovas")
    assert sample_client.post("/api/areas", json={"code": "X", "name": "X"}).status_code == 403
