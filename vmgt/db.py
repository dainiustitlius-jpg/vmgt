"""SQLite bazė ir jos schema.

Testinė aplinka dirba su vienu SQLite failu – be serverio ir be diegimo.
Schema rašoma taip, kad vėliau ją būtų galima perkelti į MS SQL: paprasti
tipai, jokių SQLite specifinių gudrybių logikoje.

Schemos versija laikoma `PRAGMA user_version`; kiekvienas `MIGRATIONS` įrašas
pakelia ją vienetu, tad sena bazė atsinaujina pati ir nė vienas žingsnis
nevykdomas du kartus.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

# Laikas – vienoje vietoje, kad testai galėtų jį pakeisti (`set_clock`).
# Saugomas UTC ISO tekstu: rikiuojasi kaip tekstas ir nepriklauso nuo zonos.
_clock = None


def now() -> str:
    if _clock is not None:
        return _clock()
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def set_clock(fn) -> None:
    global _clock
    _clock = fn


def parse_ts(s: str | None) -> datetime | None:
    if not s:
        return None
    return datetime.fromisoformat(s)


MIGRATIONS: list[str] = [
    # 1 – pradinė schema
    """
    CREATE TABLE users (
        id INTEGER PRIMARY KEY,
        login TEXT NOT NULL UNIQUE,
        name TEXT NOT NULL,
        role TEXT NOT NULL,
        pw_hash TEXT NOT NULL,
        pin_hash TEXT,
        centres TEXT NOT NULL DEFAULT '[]',   -- JSON: darbo centrų kodai, [] – visi
        active INTEGER NOT NULL DEFAULT 1,
        created TEXT NOT NULL
    );
    CREATE TABLE sessions (
        token_hash TEXT PRIMARY KEY,
        user_id INTEGER NOT NULL REFERENCES users(id),
        created TEXT NOT NULL,
        expires TEXT NOT NULL
    );
    CREATE TABLE work_centres (
        id INTEGER PRIMARY KEY,
        code TEXT NOT NULL UNIQUE,
        name TEXT NOT NULL,
        kind TEXT NOT NULL,                    -- pjovimas, lenkimas, suvirinimas ...
        manual INTEGER NOT NULL DEFAULT 1,     -- 1 – rankinis, 0 – staklės
        strict_order INTEGER NOT NULL DEFAULT 1,
        active INTEGER NOT NULL DEFAULT 1,
        sort INTEGER NOT NULL DEFAULT 0
    );
    CREATE TABLE projects (
        id INTEGER PRIMARY KEY,
        code TEXT NOT NULL UNIQUE,
        name TEXT NOT NULL,
        customer TEXT NOT NULL DEFAULT '',
        due_date TEXT,
        priority INTEGER NOT NULL DEFAULT 3,   -- 1 aukščiausias
        status TEXT NOT NULL DEFAULT 'krepselis',
        manager_id INTEGER REFERENCES users(id),
        ext_ref TEXT NOT NULL DEFAULT '',      -- D365 projekto nr. ateityje
        notes TEXT NOT NULL DEFAULT '',
        sample INTEGER NOT NULL DEFAULT 0,     -- pavyzdiniai duomenys
        created TEXT NOT NULL
    );
    CREATE TABLE assemblies (
        id INTEGER PRIMARY KEY,
        project_id INTEGER NOT NULL REFERENCES projects(id),
        code TEXT NOT NULL,
        name TEXT NOT NULL,
        revision TEXT NOT NULL DEFAULT '',
        qty INTEGER NOT NULL DEFAULT 1,
        -- mazgų kodai, kurių visos užduotys turi būti atliktos prieš šio
        -- mazgo pirmą operaciją (pvz. galutinis surinkimas laukia rėmo)
        requires TEXT NOT NULL DEFAULT '',
        sort INTEGER NOT NULL DEFAULT 0,
        UNIQUE (project_id, code)
    );
    CREATE TABLE phases (
        id INTEGER PRIMARY KEY,
        project_id INTEGER NOT NULL REFERENCES projects(id),
        assembly_id INTEGER REFERENCES assemblies(id),   -- NULL – visas projektas
        kind TEXT NOT NULL,
        owner_id INTEGER REFERENCES users(id),
        plan_start TEXT,
        plan_end TEXT,
        status TEXT NOT NULL DEFAULT 'planuota',
        actual_start TEXT,
        actual_end TEXT,
        sort INTEGER NOT NULL DEFAULT 0
    );
    CREATE TABLE drawings (
        id INTEGER PRIMARY KEY,
        number TEXT NOT NULL,
        revision TEXT NOT NULL,
        title TEXT NOT NULL DEFAULT '',
        filename TEXT NOT NULL,
        stored TEXT NOT NULL,
        uploaded_by INTEGER REFERENCES users(id),
        uploaded_at TEXT NOT NULL,
        UNIQUE (number, revision)
    );
    CREATE TABLE tasks (
        id INTEGER PRIMARY KEY,
        project_id INTEGER NOT NULL REFERENCES projects(id),
        assembly_id INTEGER NOT NULL REFERENCES assemblies(id),
        centre_id INTEGER NOT NULL REFERENCES work_centres(id),
        seq INTEGER NOT NULL,                  -- operacijos vieta mazgo maršrute
        name TEXT NOT NULL,
        part_no TEXT NOT NULL DEFAULT '',
        qty_plan INTEGER NOT NULL DEFAULT 1,
        norm_min REAL NOT NULL DEFAULT 0,
        drawing_no TEXT NOT NULL DEFAULT '',
        drawing_rev TEXT NOT NULL DEFAULT '',
        queue_pos INTEGER NOT NULL DEFAULT 0,  -- vieta centro eilėje
        approved INTEGER NOT NULL DEFAULT 0,   -- matoma terminale
        status TEXT NOT NULL DEFAULT 'laukia',
        qty_good INTEGER NOT NULL DEFAULT 0,
        qty_scrap INTEGER NOT NULL DEFAULT 0,
        created TEXT NOT NULL
    );
    CREATE INDEX ix_tasks_centre ON tasks (centre_id, approved, queue_pos);
    CREATE INDEX ix_tasks_assembly ON tasks (assembly_id, seq);
    CREATE TABLE intervals (
        id INTEGER PRIMARY KEY,
        task_id INTEGER NOT NULL REFERENCES tasks(id),
        user_id INTEGER REFERENCES users(id),
        start TEXT NOT NULL,
        end TEXT
    );
    CREATE TABLE pauses (
        id INTEGER PRIMARY KEY,
        task_id INTEGER NOT NULL REFERENCES tasks(id),
        user_id INTEGER REFERENCES users(id),
        start TEXT NOT NULL,
        end TEXT,
        reason TEXT NOT NULL,
        note TEXT NOT NULL DEFAULT ''
    );
    CREATE TABLE ncr (
        id INTEGER PRIMARY KEY,
        project_id INTEGER NOT NULL REFERENCES projects(id),
        assembly_id INTEGER REFERENCES assemblies(id),
        task_id INTEGER REFERENCES tasks(id),
        reported_by INTEGER REFERENCES users(id),
        reported_at TEXT NOT NULL,
        qty INTEGER NOT NULL DEFAULT 0,
        category TEXT NOT NULL,
        description TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'atvira',
        assignee_id INTEGER REFERENCES users(id),
        resolution TEXT NOT NULL DEFAULT '',
        closed_by INTEGER REFERENCES users(id),
        closed_at TEXT
    );
    -- visų pakeitimų žurnalas: įrašai tik pridedami
    CREATE TABLE events (
        id INTEGER PRIMARY KEY,
        at TEXT NOT NULL,
        user_id INTEGER,
        entity TEXT NOT NULL,
        entity_id INTEGER,
        action TEXT NOT NULL,
        data TEXT NOT NULL DEFAULT '{}'
    );
    """,
]


def connect(path: str | Path) -> sqlite3.Connection:
    """Nauja jungtis. Kiekvienai užklausai – sava, tad tarp užklausų ji
    nedalinama. `check_same_thread=False` reikalingas, nes FastAPI
    priklausomybę ir async užklausą (failų įkėlimas) vykdo skirtingose gijose."""
    if str(path) != ":memory:":
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(path), timeout=10, check_same_thread=False)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    con.execute("PRAGMA journal_mode = WAL")
    return con


def migrate(con: sqlite3.Connection) -> int:
    ver = con.execute("PRAGMA user_version").fetchone()[0]
    for i, sql in enumerate(MIGRATIONS[ver:], start=ver + 1):
        con.executescript(sql)
        con.execute(f"PRAGMA user_version = {i}")
    con.commit()
    return con.execute("PRAGMA user_version").fetchone()[0]


def log_event(con, user_id, entity, entity_id, action, data: dict | None = None):
    import json

    con.execute(
        "INSERT INTO events (at, user_id, entity, entity_id, action, data) VALUES (?,?,?,?,?,?)",
        (now(), user_id, entity, entity_id, action, json.dumps(data or {}, ensure_ascii=False)),
    )


def rows(cur) -> list[dict]:
    return [dict(r) for r in cur.fetchall()]


def row(cur) -> dict | None:
    r = cur.fetchone()
    return dict(r) if r else None
