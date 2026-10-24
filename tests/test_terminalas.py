"""Terminalo taisyklės: eilė, maršrutas, pauzės, kiekiai, revizijos."""

import pytest

from vmgt.services import RuleError, auth, drawings, projects, tasks


@pytest.fixture
def plant(con, clock, cfg):
    """Vienas projektas, mazgas su dviem operacijomis ir antras mazgas."""
    admin = auth.create_user(con, "admin", "Admin", "admin", "x")
    op = auth.create_user(con, "op", "Op", "operatorius", "x", pin="1111")
    meistras = auth.create_user(con, "m", "M", "meistras", "x")
    laz = projects.save_centre(con, admin, {"code": "LAZ", "name": "Lazeris", "kind": "pjovimas"})
    sv = projects.save_centre(con, admin, {"code": "SV", "name": "Suvirinimas", "kind": "suvirinimas"})
    sur = projects.save_centre(con, admin, {"code": "SUR", "name": "Surinkimas", "kind": "surinkimas"})
    pid = projects.save_project(con, admin, {"code": "P1", "name": "Projektas"})
    a1 = projects.save_assembly(con, admin, pid, {"code": "100", "name": "Rėmas"})
    a2 = projects.save_assembly(con, admin, pid, {"code": "900", "name": "Surinkimas", "requires": "100"})
    projects.save_phase(con, admin, pid, {"assembly_id": a1, "kind": "gamyba"})
    projects.save_phase(con, admin, pid, {"kind": "surinkimas"})
    drawings.save(con, cfg.files_dir, {"id": admin}, "D-1", "A", "d.pdf", drawings.sample_pdf(["D-1"]))
    mk = lambda asm, c, seq, name, qty=2: tasks.create_task(con, admin, {
        "project_id": pid, "assembly_id": asm, "centre_id": c, "seq": seq, "name": name,
        "qty_plan": qty, "drawing_no": "D-1", "drawing_rev": "A"})
    ids = {"cut": mk(a1, laz, 10, "Pjovimas"), "cut2": mk(a1, laz, 15, "Pjovimas 2"),
           "weld": mk(a1, sv, 20, "Suvirinimas"), "asm": mk(a2, sur, 10, "Surinkimas", 1)}
    for c in (laz, sv, sur):
        tasks.approve_queue(con, admin, c)
    u = lambda i: dict(con.execute("SELECT * FROM users WHERE id=?", (i,)).fetchone())
    return {"pid": pid, "op": u(op), "meistras": u(meistras), "admin": admin, "ids": ids,
            "centres": {"LAZ": laz, "SV": sv, "SUR": sur}}


def T(con, i):
    return dict(con.execute("SELECT * FROM tasks WHERE id=?", (i,)).fetchone())


def test_neparvirtinta_eile_neleidzia_pradeti(con, plant):
    i = tasks.create_task(con, plant["admin"], {"project_id": plant["pid"], "assembly_id": T(con, plant["ids"]["cut"])["assembly_id"],
                                                "centre_id": plant["centres"]["LAZ"], "seq": 5, "name": "Nauja"})
    with pytest.raises(RuleError, match="nepatvirtinta"):
        tasks.start(con, plant["op"], i)


def test_griezta_eile_ir_vienas_darbas_centre(con, plant):
    op, ids = plant["op"], plant["ids"]
    with pytest.raises(RuleError, match="Pirma eilėje"):
        tasks.start(con, op, ids["cut2"])
    tasks.start(con, op, ids["cut"])
    with pytest.raises(RuleError, match="jau vykdoma"):
        tasks.start(con, op, ids["cut2"])


def test_marsrutas_laukia_ankstesnes_operacijos(con, plant, clock):
    op, ids = plant["op"], plant["ids"]
    with pytest.raises(RuleError, match="Laukiama ankstesnės operacijos"):
        tasks.start(con, op, ids["weld"])
    tasks.start(con, op, ids["cut"])
    clock.set("2026-10-20T08:30:00+00:00")
    r = tasks.stop(con, op, ids["cut"], good=1)            # dalinis: 1 iš 2
    assert r["status"] == "laukia"
    # pjovimas 2 dar neturi nė vieno gero – suvirinimas vis dar laukia
    with pytest.raises(RuleError, match="Pjovimas 2"):
        tasks.start(con, op, ids["weld"])


def test_mazgas_laukia_kitu_mazgu(con, plant):
    with pytest.raises(RuleError, match="Laukiama mazgų: 100"):
        tasks.start(con, plant["op"], plant["ids"]["asm"])


def test_pauze_reikalauja_priezasties_ir_neskaiciuojama_darbu(con, plant, clock):
    op, i = plant["op"], plant["ids"]["cut"]
    tasks.start(con, op, i)
    clock.set("2026-10-20T08:10:00+00:00")
    with pytest.raises(RuleError, match="priežastį"):
        tasks.pause(con, op, i, "")
    with pytest.raises(RuleError, match="pastaba"):
        tasks.pause(con, op, i, "kita", "")
    tasks.pause(con, op, i, "medziaga")
    with pytest.raises(RuleError, match="Tęsti"):
        tasks.start(con, op, i)
    clock.set("2026-10-20T08:40:00+00:00")
    tasks.resume(con, op, i)
    clock.set("2026-10-20T08:50:00+00:00")
    r = tasks.stop(con, op, i, good=2)
    assert r["status"] == "baigta"
    assert tasks._work_seconds(con, i) == 20 * 60           # 10 + 10 min, pauzė 30 min neįeina


def test_pristabdyta_uzduotis_blokuoja_centra(con, plant):
    op, ids = plant["op"], plant["ids"]
    tasks.start(con, op, ids["cut"])
    tasks.pause(con, op, ids["cut"], "gedimas")
    t = {**T(con, ids["cut2"]), "strict_order": 0}
    assert "pirma ją pratęskite" in tasks.block_reason(con, t)


def test_brokas_siulo_neatitikti_ir_baigia(con, plant):
    op, i = plant["op"], plant["ids"]["cut"]
    tasks.start(con, op, i)
    r = tasks.stop(con, op, i, good=1, scrap=1)
    assert r == {"status": "baigta", "suggest_ncr": True, "qty_good": 1, "qty_scrap": 1}


def test_revizija_uzrakina_kol_meistras_patvirtina(con, plant, cfg):
    op, i = plant["op"], plant["ids"]["cut"]
    drawings.save(con, cfg.files_dir, {"id": plant["admin"]}, "D-1", "B", "d.pdf", drawings.sample_pdf(["D-1 B"]))
    with pytest.raises(RuleError, match="revizija pasikeitė: A → B"):
        tasks.start(con, op, i)
    tasks.ack_revision(con, plant["meistras"], i)
    tasks.start(con, op, i)
    assert T(con, i)["drawing_rev"] == "B"


def test_operatorius_tik_savo_centruose(con, plant):
    auth.update_user(con, plant["op"]["id"], None, centres=["SV"])
    op = dict(con.execute("SELECT * FROM users WHERE id=?", (plant["op"]["id"],)).fetchone())
    with pytest.raises(RuleError, match="nepriskirtas"):
        tasks.start(con, op, plant["ids"]["cut"])


def test_pirmas_darbas_pradeda_etapa_ir_projekta(con, plant):
    tasks.start(con, plant["op"], plant["ids"]["cut"])
    ph = con.execute("SELECT status, actual_start FROM phases WHERE kind='gamyba'").fetchone()
    assert ph["status"] == "vykdoma" and ph["actual_start"]
    assert con.execute("SELECT status FROM projects").fetchone()[0] == "vykdomas"


def test_eiles_perkelimas(con, plant):
    ids = plant["ids"]
    tasks.move(con, plant["admin"], ids["cut2"], "top")
    order = [r[0] for r in con.execute("SELECT id FROM tasks WHERE centre_id=? ORDER BY queue_pos",
                                       (plant["centres"]["LAZ"],))]
    assert order == [ids["cut2"], ids["cut"]]


def test_terminalo_laikas_be_atviro_intervalo(con, plant, clock):
    """Naršyklė atviro intervalo laiką prideda pati – serveris jo neįskaičiuoja,
    kitaip laikmatis rodytų dvigubai (rasta tikrinant ekraną)."""
    op, i = plant["op"], plant["ids"]["cut"]
    tasks.start(con, op, i)
    clock.set("2026-10-20T08:20:00+00:00")
    tasks.pause(con, op, i, "gedimas")
    tasks.resume(con, op, i)
    clock.set("2026-10-20T09:00:00+00:00")
    c = dict(con.execute("SELECT * FROM work_centres WHERE code='LAZ'").fetchone())
    run = tasks.terminal_view(con, c)["running"]
    assert run["work_s"] == 20 * 60 and run["since"] == "2026-10-20T08:20:00+00:00"
