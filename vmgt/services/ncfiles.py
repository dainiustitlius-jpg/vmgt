"""Technologo failai prie operacijų: DXF, NC programos, robotų ir PLC programos.

Failus VMGT tvarko pati, aiškioje katalogų struktūroje
`<nc_dir>/<projektas>/<mazgas>/<centras>/<failas>_v<N>.<plėtinys>`, kad juos
rastų ir staklių kompiuteris tinklo diske, ir žmogus be VMGT. Versija
skaičiuojama pagal originalų pavadinimą: tas pats failas įkeltas dar kartą –
nauja versija, senoji lieka diske ir istorijoje (`current=0`). Niekas
neperrašomas – kitaip nebūtų įmanoma atsekti, pagal kurią programą pjauta.

Failas, įkeltas jau išleidus maršrutą į gamybą, galioja tik meistrui
patvirtinus (`needs_ack`) – kaip brėžinio revizija: kad lazeris nepjautų
pagal programą, kurios niekas ceche nematė. Vykdomos operacijos nestabdo –
terminalas rodo įspėjimą.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path, PurePosixPath

from .. import db
from . import NotFound, RuleError, routing

MAX_BYTES = 200 * 1024 * 1024

# Plėtiniai pagal rūšį. Sąrašas leidžiamas, ne draudžiamas: nežinomas failas
# (pvz. .exe) į cecho katalogą nepateks. Naujas valdiklio formatas – įrašyti čia.
KINDS = {
    "cad": ("CAD / išklotinė", {"dxf", "dwg", "step", "stp", "igs", "iges", "sldprt", "sldasm", "slddrw", "x_t", "sat"}),
    "nc": ("NC programa", {"nc", "cnc", "mpf", "spf", "h", "tap", "gcode", "ngc", "iso", "eia", "din", "ptp", "lcc",
                           "mbx", "prg", "anc", "dnc", "bnd"}),
    "robot": ("Roboto programa", {"mod", "modx", "sys", "src", "dat", "ls", "tp", "jbi", "urp", "script"}),
    "plc": ("PLC / HMI projektas", {"zap13", "zap14", "zap15", "zap16", "zap17", "zap18", "zap19", "zap20",
                                    "ap13", "ap14", "ap15", "ap16", "ap17", "ap18", "ap19", "ap20",
                                    "acd", "l5x", "l5k", "smc", "scl", "awl", "xml", "tsproj"}),
    "doc": ("Dokumentas", {"pdf", "txt", "csv", "xlsx", "xls", "docx", "png", "jpg", "jpeg", "zip", "7z"}),
}
KIND_LABEL = {k: v[0] for k, v in KINDS.items()}


def kind_of(filename: str) -> str:
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    for k, (_, exts) in KINDS.items():
        if ext in exts:
            return k
    raise RuleError(f"Failo tipas „.{ext or '?'}“ neleidžiamas. Leidžiami: "
                    + ", ".join(f"{v[0]} ({', '.join(sorted(v[1])[:6])}…)" for v in KINDS.values()))


def _safe(s: str) -> str:
    # tik saugūs simboliai: kelias neturi išeiti iš katalogo (../) ir turi
    # veikti ir Windows tinklo diske
    s = re.sub(r"[^A-Za-z0-9._-]+", "_", s).strip("._")
    return s or "failas"


def _task(con, task_id) -> dict:
    t = db.row(con.execute(
        "SELECT t.*, p.code AS project_code, a.code AS assembly_code, c.code AS centre_code "
        "FROM tasks t JOIN projects p ON p.id=t.project_id JOIN assemblies a ON a.id=t.assembly_id "
        "JOIN work_centres c ON c.id=t.centre_id WHERE t.id=?", (task_id,)))
    if not t:
        raise NotFound("Užduoties nėra")
    return t


def save(con, nc_dir: Path, user, task_id, filename: str, content: bytes, note: str = "") -> dict:
    t = _task(con, task_id)
    name = Path((filename or "").replace("\\", "/")).name
    if not name:
        raise RuleError("Nėra failo pavadinimo")
    if not content:
        raise RuleError("Failas tuščias")
    if len(content) > MAX_BYTES:
        raise RuleError(f"Failas per didelis (daugiau nei {MAX_BYTES // 1024 // 1024} MB)")
    kind = kind_of(name)
    if t["status"] == "baigta":
        raise RuleError("Operacija jau atlikta – failo keisti nebereikia")
    prev = db.row(con.execute("SELECT * FROM task_files WHERE task_id=? AND name=? ORDER BY version DESC LIMIT 1",
                              (task_id, name)))
    digest = hashlib.sha256(content).hexdigest()
    if prev and prev["current"] and prev["sha256"] == digest:
        raise RuleError(f"{name} v{prev['version']} jau toks pat – nauja versija nesukurta")
    version = (prev["version"] + 1) if prev else 1
    stem, dot, ext = name.rpartition(".")
    fname = f"{_safe(stem if dot else name)}_v{version}{'.' + _safe(ext).lower() if dot else ''}"
    rel = PurePosixPath(_safe(t["project_code"]), _safe(t["assembly_code"]), _safe(t["centre_code"]), fname)
    full = nc_dir / Path(*rel.parts)
    full.parent.mkdir(parents=True, exist_ok=True)
    full.write_bytes(content)
    if prev:
        con.execute("UPDATE task_files SET current=0 WHERE task_id=? AND name=?", (task_id, name))
    # išleistame maršrute – naujas failas ceche galioja tik meistrui patvirtinus
    needs_ack = 1 if routing.is_released(con, t["assembly_id"]) else 0
    cur = con.execute(
        "INSERT INTO task_files (task_id, name, version, path, kind, size, sha256, note, needs_ack, uploaded_by, "
        "uploaded_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (task_id, name, version, str(rel), kind, len(content), digest, note or "", needs_ack,
         user["id"] if user else None, db.now()))
    db.log_event(con, user["id"] if user else None, "task", task_id, "file",
                 {"name": name, "version": version, "needs_ack": needs_ack})
    return get(con, cur.lastrowid)


def get(con, file_id) -> dict:
    f = db.row(con.execute(
        "SELECT f.*, u.name AS uploaded_by_name, a.name AS acked_by_name FROM task_files f "
        "LEFT JOIN users u ON u.id=f.uploaded_by LEFT JOIN users a ON a.id=f.acked_by WHERE f.id=?", (file_id,)))
    if not f:
        raise NotFound("Failo nėra")
    f["kind_label"] = KIND_LABEL.get(f["kind"], f["kind"])
    return f


def list_for(con, task_ids, history=False) -> dict[int, list[dict]]:
    """Užduočių failai: {task_id: [...]} – vienu kreipiniu visam sąrašui."""
    ids = list(task_ids)
    out = {i: [] for i in ids}
    if not ids:
        return out
    q = ("SELECT f.*, u.name AS uploaded_by_name FROM task_files f LEFT JOIN users u ON u.id=f.uploaded_by "
         f"WHERE f.task_id IN ({','.join('?' * len(ids))})" + ("" if history else " AND f.current=1")
         + " ORDER BY f.name, f.version DESC")
    for f in db.rows(con.execute(q, ids)):
        f["kind_label"] = KIND_LABEL.get(f["kind"], f["kind"])
        out[f["task_id"]].append(f)
    return out


def pending_ack(con, task_id) -> list[dict]:
    return db.rows(con.execute("SELECT name, version FROM task_files WHERE task_id=? AND current=1 AND needs_ack=1 "
                               "ORDER BY name", (task_id,)))


def ack(con, user, task_id) -> int:
    """Meistras patvirtina naujus operacijos failus."""
    n = con.execute("UPDATE task_files SET needs_ack=0, acked_by=?, acked_at=? WHERE task_id=? AND current=1 "
                    "AND needs_ack=1", (user["id"], db.now(), task_id)).rowcount
    if not n:
        raise RuleError("Naujų failų, laukiančių patvirtinimo, nėra")
    db.log_event(con, user["id"], "task", task_id, "ack_files", {"count": n})
    return n


def remove(con, user, file_id) -> None:
    """Pašalinti iš operacijos. Diske lieka (istorija), išleistame maršrute –
    tik grąžinus jį keisti: dingęs failas ceche būtų toks pat netikėtas kaip naujas."""
    f = get(con, file_id)
    if not f["current"]:
        raise RuleError("Tai ne galiojanti versija")
    routing.ensure_editable(con, _task(con, f["task_id"])["assembly_id"])
    con.execute("UPDATE task_files SET current=0 WHERE id=?", (file_id,))
    db.log_event(con, user["id"], "task", f["task_id"], "file_remove", {"name": f["name"], "version": f["version"]})


def full_path(nc_dir: Path, f: dict) -> Path:
    p = (nc_dir / Path(*PurePosixPath(f["path"]).parts)).resolve()
    if nc_dir.resolve() not in p.parents:
        raise NotFound("Failo nėra")
    return p


def copy_files(con, nc_dir: Path, user, from_task, to_task) -> int:
    """Kopijuojant maršrutą – ir galiojančius failus (kaip naujas v1)."""
    n = 0
    for f in list_for(con, [from_task])[from_task]:
        p = full_path(nc_dir, f)
        if p.exists():
            save(con, nc_dir, user, to_task, f["name"], p.read_bytes(), f"nukopijuota iš {f['path']}")
            n += 1
    return n
