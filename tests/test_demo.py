"""Penki pavyzdiniai projektai (`demo.py`): istorija sukurta per tikras
taisykles, todėl turi būti nuosekli bet kurią paleidimo dieną."""

from datetime import datetime, timezone

import pytest
from conftest import login

from vmgt import db
from vmgt.services import seed

CODES = ["P-24095", "P-24102", "P-24108", "P-24113", "P-24126"]


@pytest.mark.parametrize("now", ["2026-10-25T20:27:00", "2026-10-28T09:15:00", "2026-11-02T06:00:00",
                                 "2027-03-14T12:00:00"])
def test_istorija_nuosekli_bet_kuria_diena(tmp_path, now):
    """Šeštadienis, darbo diena vidury pamainos, pirmadienio rytas, kitas metų laikas."""
    con = db.connect(tmp_path / "v.db")
    db.migrate(con)
    today = datetime.fromisoformat(now).replace(tzinfo=timezone.utc)
    seed.seed(con, tmp_path / "files", today=today, nc_dir=tmp_path / "nc")
    rows = lambda q, *a: [tuple(r) for r in con.execute(q, a)]
    st = {c: dict(rows("SELECT t.status, COUNT(*) FROM tasks t JOIN projects p ON p.id=t.project_id "
                       "WHERE p.code=? GROUP BY t.status", c)) for c in CODES}
    assert rows("SELECT status FROM projects WHERE code='P-24095'") == [("baigtas",)]
    assert st["P-24095"] == {"baigta": 16}
    assert st["P-24102"].get("laukia") == 2                     # surinkimas laukia motoreduktorių
    assert st["P-24113"].get("baigta") == 17                    # testuojama
    # kiekvienas centras – ne daugiau vienos vykdomos / pristabdytos užduoties
    assert rows("SELECT centre_id FROM tasks WHERE status IN ('vykdoma','pristabdyta') "
                "GROUP BY centre_id HAVING COUNT(*)>1") == []
    # niekas neįvyko ateityje
    assert rows("SELECT COUNT(*) FROM intervals WHERE start > ?", today.isoformat()) == [(0,)]
    assert rows("SELECT COUNT(*) FROM ncr WHERE closed_at > ?", today.isoformat()) == [(0,)]
    # neatitiktys: uždarytos su sprendimais ir atviros
    ncr = rows("SELECT n.status, n.resolution FROM ncr n JOIN projects p ON p.id=n.project_id WHERE p.sample=1")
    assert sum(1 for s, r in ncr if s == "uzdaryta" and r) >= 7 and any(s != "uzdaryta" for s, _ in ncr)
    # technologo failai ir perdavimai
    assert rows("SELECT COUNT(*) FROM task_files")[0][0] > 30
    assert rows("SELECT COUNT(*) FROM transfers")[0][0] > 50


def test_langai_su_demo(demo_client):
    c = demo_client
    login(c, "vadovas")
    ps = {p["code"]: p for p in c.get("/api/projects?all=1").json()}
    assert set(CODES) <= set(ps)
    assert ps["P-24102"]["health"]["level"] == "red"            # motoreduktoriai vėluoja
    an = c.get("/api/analytics").json()
    assert an and c.get("/api/capacity").status_code == 200
    login(c, "technologas")
    w = c.get("/api/tech/worklist").json()
    poz = next(x for x in w if x["project_code"] == "P-24126" and x["code"] == "200")
    assert poz["state"] == "juodrastis" and poz["no_file"] == 1
    login(c, pin="4002")                                        # suvirintojas mato tik suvirinimo barą
    assert c.get("/api/terminal/SV-06").status_code == 200
    assert c.get("/api/terminal/LAZ-01").status_code == 403
