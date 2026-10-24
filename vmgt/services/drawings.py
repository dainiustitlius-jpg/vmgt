"""Brėžiniai: PDF su numeriu ir revizija.

Testinėje versijoje įkeliami ranka; vėliau juos pateiks PDM. Galioja
naujausia įkelta numerio revizija – ją rodo terminalas, o užduotis, sukurta
su senesne, užrakinama, kol meistras patvirtina (`tasks.ack_revision`).
"""

from __future__ import annotations

import re
import secrets
from pathlib import Path

from .. import db
from . import NotFound, RuleError


def save(con, files_dir: Path, user, number: str, revision: str, filename: str, content: bytes, title="") -> int:
    number, revision = (number or "").strip(), (revision or "").strip()
    if not number or not revision:
        raise RuleError("Reikia brėžinio numerio ir revizijos")
    if not content.startswith(b"%PDF"):
        raise RuleError("Failas nėra PDF")
    if con.execute("SELECT 1 FROM drawings WHERE number=? AND revision=?", (number, revision)).fetchone():
        raise RuleError(f"Brėžinys {number} rev. {revision} jau įkeltas")
    files_dir.mkdir(parents=True, exist_ok=True)
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", f"{number}_rev{revision}")
    stored = f"{safe}_{secrets.token_hex(4)}.pdf"
    (files_dir / stored).write_bytes(content)
    cur = con.execute(
        "INSERT INTO drawings (number, revision, title, filename, stored, uploaded_by, uploaded_at) "
        "VALUES (?,?,?,?,?,?,?)",
        (number, revision, title or "", filename or stored, stored, user["id"] if user else None, db.now()))
    db.log_event(con, user["id"] if user else None, "drawing", cur.lastrowid, "upload",
                 {"number": number, "revision": revision})
    return cur.lastrowid


def list_drawings(con) -> list[dict]:
    out = db.rows(con.execute(
        "SELECT d.*, u.name AS uploader FROM drawings d LEFT JOIN users u ON u.id=d.uploaded_by "
        "ORDER BY d.number, d.uploaded_at DESC, d.id DESC"))
    seen = set()
    for d in out:
        d["current"] = d["number"] not in seen
        seen.add(d["number"])
    return out


def file_for(con, files_dir: Path, number: str, revision: str | None = None) -> tuple[Path, dict]:
    if revision:
        d = db.row(con.execute("SELECT * FROM drawings WHERE number=? AND revision=?", (number, revision)))
    else:
        d = db.row(con.execute("SELECT * FROM drawings WHERE number=? ORDER BY uploaded_at DESC, id DESC LIMIT 1",
                               (number,)))
    if not d:
        raise NotFound(f"Brėžinio {number} nėra")
    return files_dir / d["stored"], d


def sample_pdf(lines: list[str]) -> bytes:
    """Mažas galiojantis PDF su tekstu – pavyzdiniams brėžiniams be failų."""
    import unicodedata

    def esc(s):
        # standartinis Helvetica šriftas lietuviškų raidžių neturi – nuimame diakritiką
        s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
        return s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")

    body = "BT /F1 18 Tf 60 520 Td " + " ".join(
        f"({esc(s)}) Tj 0 -28 Td" for s in lines) + " ET"
    body += " 40 40 m 802 40 l 802 555 l 40 555 l h S 40 100 m 802 100 l S"
    objs = [
        "<< /Type /Catalog /Pages 2 0 R >>",
        "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 842 595] /Contents 4 0 R "
        "/Resources << /Font << /F1 5 0 R >> >> >>",
        f"<< /Length {len(body)} >>\nstream\n{body}\nendstream",
        "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = b"%PDF-1.4\n"
    offs = []
    for i, o in enumerate(objs, start=1):
        offs.append(len(out))
        out += f"{i} 0 obj\n{o}\nendobj\n".encode("latin-1")
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode()
    for o in offs:
        out += f"{o:010d} 00000 n \n".encode()
    out += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return out
