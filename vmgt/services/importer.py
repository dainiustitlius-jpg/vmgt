"""Maršrutų importas iš CSV – laikinas kelias, kol nėra D365 / PDM integracijų.

Viena eilutė – viena mazgo operacija. Projektas ir mazgas sukuriami, jei jų
dar nėra. Skirtukas – kabliataškis (Excel lietuviškuose nustatymuose) arba
kablelis; atpažįstama savaime.

Importas – viskas arba nieko: radus bent vieną klaidą neįrašoma niekas, o
grąžinamas klaidų sąrašas su eilučių numeriais. Pusiau įkeltas maršrutas
ceche būtų blogiau už jokį.
"""

from __future__ import annotations

import csv
import io

from .. import db
from . import RuleError
from .projects import save_assembly, save_project
from .tasks import create_task

COLUMNS = ["projektas", "projekto_pavadinimas", "mazgas", "mazgo_pavadinimas", "seka", "centras",
           "operacija", "detale", "kiekis", "norma_min", "brezinys", "revizija"]
REQUIRED = ["projektas", "mazgas", "seka", "centras", "operacija"]


def template() -> str:
    return ";".join(COLUMNS) + "\n"


def parse(text: str) -> list[dict]:
    text = text.lstrip("﻿")
    first = text.splitlines()[0] if text else ""
    delim = ";" if first.count(";") >= first.count(",") else ","
    reader = csv.DictReader(io.StringIO(text), delimiter=delim)
    missing = [c for c in REQUIRED if c not in (reader.fieldnames or [])]
    if missing:
        raise RuleError(f"Trūksta stulpelių: {', '.join(missing)}. Reikalingi: {';'.join(COLUMNS)}")
    return [{k: (v or "").strip() for k, v in r.items() if k} for r in reader]


def run(con, user, text: str, dry_run: bool = False) -> dict:
    rows = parse(text)
    centres = {r["code"]: r["id"] for r in con.execute("SELECT id, code FROM work_centres")}
    errors = []
    for i, r in enumerate(rows, start=2):  # 1 eilutė – antraštė
        for c in REQUIRED:
            if not r.get(c):
                errors.append(f"{i} eil.: tuščias „{c}“")
        if r.get("centras") and r["centras"] not in centres:
            errors.append(f"{i} eil.: nežinomas darbo centras „{r['centras']}“")
        for c in ("seka", "kiekis"):
            if r.get(c) and not r[c].isdigit():
                errors.append(f"{i} eil.: „{c}“ turi būti sveikas skaičius")
        if r.get("norma_min"):
            try:
                float(r["norma_min"].replace(",", "."))
            except ValueError:
                errors.append(f"{i} eil.: „norma_min“ turi būti skaičius")
    summary = {"rows": len(rows), "errors": errors, "projects_new": 0, "assemblies_new": 0, "tasks_new": 0}
    if errors or dry_run:
        return summary

    by = user["id"]
    proj_ids, asm_ids = {}, {}
    try:
        for r in rows:
            pcode = r["projektas"]
            if pcode not in proj_ids:
                p = con.execute("SELECT id FROM projects WHERE code=?", (pcode,)).fetchone()
                if p:
                    proj_ids[pcode] = p[0]
                else:
                    proj_ids[pcode] = save_project(con, by, {"code": pcode, "name": r.get("projekto_pavadinimas") or pcode})
                    summary["projects_new"] += 1
            pid = proj_ids[pcode]
            akey = (pid, r["mazgas"])
            if akey not in asm_ids:
                a = con.execute("SELECT id FROM assemblies WHERE project_id=? AND code=?", akey).fetchone()
                if a:
                    asm_ids[akey] = a[0]
                else:
                    asm_ids[akey] = save_assembly(con, by, pid, {"code": r["mazgas"],
                                                                 "name": r.get("mazgo_pavadinimas") or r["mazgas"]})
                    summary["assemblies_new"] += 1
            create_task(con, by, {
                "project_id": pid, "assembly_id": asm_ids[akey], "centre_id": centres[r["centras"]],
                "seq": int(r["seka"]), "name": r["operacija"], "part_no": r.get("detale", ""),
                "qty_plan": int(r["kiekis"] or 1) if r.get("kiekis") else 1,
                "norm_min": float((r.get("norma_min") or "0").replace(",", ".")),
                "drawing_no": r.get("brezinys", ""), "drawing_rev": r.get("revizija", ""),
            })
            summary["tasks_new"] += 1
        db.log_event(con, by, "import", None, "routes", {k: v for k, v in summary.items() if k != "errors"})
    except Exception:
        con.rollback()
        raise
    return summary
