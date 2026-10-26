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
    # 2 – komponentų pirkimai ir jų gavimai
    """
    CREATE TABLE components (
        id INTEGER PRIMARY KEY,
        project_id INTEGER NOT NULL REFERENCES projects(id),
        assembly_id INTEGER REFERENCES assemblies(id),   -- NULL – visam projektui
        item_no TEXT NOT NULL DEFAULT '',      -- prekės kodas (D365)
        name TEXT NOT NULL,
        spec TEXT NOT NULL DEFAULT '',         -- gamintojas, modelis, parametrai
        qty REAL NOT NULL DEFAULT 1,
        unit TEXT NOT NULL DEFAULT 'vnt',
        supplier TEXT NOT NULL DEFAULT '',
        po_no TEXT NOT NULL DEFAULT '',        -- pirkimo užsakymo nr.
        po_line TEXT NOT NULL DEFAULT '',
        ordered_date TEXT,
        promised_date TEXT,                    -- tiekėjo patvirtinta pristatymo data
        need_date TEXT,                        -- reikia iki (gamybos poreikis)
        qty_received REAL NOT NULL DEFAULT 0,
        received_date TEXT,                    -- paskutinio gavimo data
        location TEXT NOT NULL DEFAULT '',     -- sandėlio vieta
        cancelled INTEGER NOT NULL DEFAULT 0,
        note TEXT NOT NULL DEFAULT '',
        source TEXT NOT NULL DEFAULT 'rankinis',   -- rankinis / importas / erp
        updated TEXT NOT NULL,
        created TEXT NOT NULL
    );
    CREATE INDEX ix_components_project ON components (project_id, assembly_id);
    CREATE INDEX ix_components_po ON components (po_no, po_line);
    -- kiekvienas gavimas atskirai: iš jų matoma, kada ir kiek atkeliavo
    CREATE TABLE component_receipts (
        id INTEGER PRIMARY KEY,
        component_id INTEGER NOT NULL REFERENCES components(id),
        qty REAL NOT NULL,
        at TEXT NOT NULL,
        user_id INTEGER REFERENCES users(id),
        source TEXT NOT NULL DEFAULT 'rankinis',
        note TEXT NOT NULL DEFAULT ''
    );
    """,
    # 3 – gamybos barai: darbo centrai sugrupuoti pagal cecho dalis
    """
    CREATE TABLE areas (
        id INTEGER PRIMARY KEY,
        code TEXT NOT NULL UNIQUE,
        name TEXT NOT NULL,
        master_id INTEGER REFERENCES users(id),   -- baro meistras
        sort INTEGER NOT NULL DEFAULT 0,
        active INTEGER NOT NULL DEFAULT 1
    );
    ALTER TABLE work_centres ADD COLUMN area_id INTEGER REFERENCES areas(id);
    """,
    # 4 – PIN randamas tiesiai pagal raktą (žr. auth.pin_key)
    """
    CREATE TABLE settings (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL
    );
    CREATE INDEX ix_users_pin ON users (pin_hash);
    """,
    # 5 – projekto valdymas: komandos užduotys, jų istorija, susitikimų protokolai
    """
    CREATE TABLE meetings (
        id INTEGER PRIMARY KEY,
        project_id INTEGER NOT NULL REFERENCES projects(id),
        title TEXT NOT NULL,
        held_at TEXT NOT NULL,                 -- data ir laikas
        location TEXT NOT NULL DEFAULT '',
        chair_id INTEGER REFERENCES users(id),
        attendees TEXT NOT NULL DEFAULT '[]',  -- JSON: vartotojų id
        guests TEXT NOT NULL DEFAULT '',       -- ne sistemos dalyviai (užsakovas, tiekėjas)
        agenda TEXT NOT NULL DEFAULT '',
        notes TEXT NOT NULL DEFAULT '',
        decisions TEXT NOT NULL DEFAULT '',    -- po vieną sprendimą eilutėje
        status TEXT NOT NULL DEFAULT 'juodrastis',
        created_by INTEGER REFERENCES users(id),
        created TEXT NOT NULL,
        approved_by INTEGER REFERENCES users(id),
        approved_at TEXT
    );
    CREATE TABLE actions (
        id INTEGER PRIMARY KEY,
        project_id INTEGER NOT NULL REFERENCES projects(id),
        assembly_id INTEGER REFERENCES assemblies(id),
        phase_id INTEGER REFERENCES phases(id),
        meeting_id INTEGER REFERENCES meetings(id),   -- iš kurio susitikimo kilo
        title TEXT NOT NULL,
        description TEXT NOT NULL DEFAULT '',
        owner_id INTEGER REFERENCES users(id),
        priority INTEGER NOT NULL DEFAULT 2,           -- 1 aukštas, 2 vidutinis, 3 žemas
        status TEXT NOT NULL DEFAULT 'nauja',
        due_date TEXT,
        wait_reason TEXT NOT NULL DEFAULT '',
        created_by INTEGER REFERENCES users(id),
        created TEXT NOT NULL,
        updated TEXT NOT NULL,
        started_at TEXT,
        done_at TEXT
    );
    CREATE INDEX ix_actions_project ON actions (project_id, status);
    CREATE INDEX ix_actions_owner ON actions (owner_id, status);
    -- komentarai ir kiekvienas būsenos pakeitimas: visa užduoties istorija
    CREATE TABLE action_log (
        id INTEGER PRIMARY KEY,
        action_id INTEGER NOT NULL REFERENCES actions(id),
        user_id INTEGER REFERENCES users(id),
        at TEXT NOT NULL,
        kind TEXT NOT NULL,                    -- comment / status / edit
        from_status TEXT,
        to_status TEXT,
        text TEXT NOT NULL DEFAULT ''
    );
    """,
    # 6 – resursų apkrova: departamentai (biuro skyriai ir gamybos barai),
    # etapų planuojamos valandos
    """
    CREATE TABLE departments (
        id INTEGER PRIMARY KEY,
        code TEXT NOT NULL UNIQUE,
        name TEXT NOT NULL,
        kind TEXT NOT NULL DEFAULT 'office',        -- office / production
        area_id INTEGER REFERENCES areas(id),       -- gamybos barui
        phase_kinds TEXT NOT NULL DEFAULT '',       -- biuro skyriui: kurių etapų darbas
        headcount REAL NOT NULL DEFAULT 1,          -- žmonių skaičius
        hours_per_week REAL NOT NULL DEFAULT 40,    -- vienam žmogui
        availability REAL NOT NULL DEFAULT 0.85,    -- dalis laiko projektams (be atostogų, ligų, kitų darbų)
        sort INTEGER NOT NULL DEFAULT 0,
        active INTEGER NOT NULL DEFAULT 1
    );
    ALTER TABLE phases ADD COLUMN hours REAL;
    ALTER TABLE phases ADD COLUMN department_id INTEGER REFERENCES departments(id);
    """,
    # 7 – technologinis srautas ir detalių atsekamumas: technologas išleidžia
    # mazgo maršrutą į gamybą, kiekvienas perdavimas kitam centrui įrašomas
    """
    ALTER TABLE assemblies ADD COLUMN released_at TEXT;
    ALTER TABLE assemblies ADD COLUMN released_by INTEGER REFERENCES users(id);
    -- esamos bazės maršrutai jau dirba ceche – laikomi išleistais
    UPDATE assemblies SET released_at = (SELECT MIN(created) FROM tasks WHERE assembly_id = assemblies.id)
        WHERE EXISTS (SELECT 1 FROM tasks WHERE assembly_id = assemblies.id);
    CREATE TABLE transfers (
        id INTEGER PRIMARY KEY,
        from_task_id INTEGER NOT NULL REFERENCES tasks(id),
        to_task_id INTEGER REFERENCES tasks(id),   -- NULL – mazgas baigtas, į sandėlį
        qty INTEGER NOT NULL,
        at TEXT NOT NULL,
        user_id INTEGER REFERENCES users(id)
    );
    CREATE INDEX ix_transfers_from ON transfers (from_task_id);
    CREATE INDEX ix_transfers_to ON transfers (to_task_id);
    """,
    # 8 – asmeninis darbų planas: užduotis be projekto (matoma tik
    # atsakingajam), planuojama diena ir įvertis valandomis. SQLite NOT NULL
    # nuimti negali, tad lentelė perkuriama (action_log nuoroda išlieka –
    # ji rodo į pavadinimą „actions“)
    """
    PRAGMA foreign_keys = OFF;
    CREATE TABLE actions_new (
        id INTEGER PRIMARY KEY,
        project_id INTEGER REFERENCES projects(id),    -- NULL – asmeninė užduotis
        assembly_id INTEGER REFERENCES assemblies(id),
        phase_id INTEGER REFERENCES phases(id),
        meeting_id INTEGER REFERENCES meetings(id),
        title TEXT NOT NULL,
        description TEXT NOT NULL DEFAULT '',
        owner_id INTEGER REFERENCES users(id),
        priority INTEGER NOT NULL DEFAULT 2,
        status TEXT NOT NULL DEFAULT 'nauja',
        due_date TEXT,
        wait_reason TEXT NOT NULL DEFAULT '',
        created_by INTEGER REFERENCES users(id),
        created TEXT NOT NULL,
        updated TEXT NOT NULL,
        started_at TEXT,
        done_at TEXT,
        plan_date TEXT,                                 -- kurią dieną atsakingasis planuoja daryti
        estimate_h REAL                                 -- jo įvertis, val.
    );
    INSERT INTO actions_new (id, project_id, assembly_id, phase_id, meeting_id, title, description, owner_id,
        priority, status, due_date, wait_reason, created_by, created, updated, started_at, done_at)
        SELECT id, project_id, assembly_id, phase_id, meeting_id, title, description, owner_id,
        priority, status, due_date, wait_reason, created_by, created, updated, started_at, done_at FROM actions;
    DROP TABLE actions;
    ALTER TABLE actions_new RENAME TO actions;
    CREATE INDEX ix_actions_project ON actions (project_id, status);
    CREATE INDEX ix_actions_owner ON actions (owner_id, status);
    CREATE INDEX ix_actions_plan ON actions (owner_id, plan_date);
    PRAGMA foreign_keys = ON;
    """,
    # 9 – technologo failai prie operacijų (DXF, NC, robotų ir PLC programos)
    """
    ALTER TABLE work_centres ADD COLUMN needs_files INTEGER NOT NULL DEFAULT 0;  -- staklės, kurioms reikia programos
    CREATE TABLE task_files (
        id INTEGER PRIMARY KEY,
        task_id INTEGER NOT NULL REFERENCES tasks(id),
        name TEXT NOT NULL,                    -- originalus pavadinimas: pagal jį skaičiuojamos versijos
        version INTEGER NOT NULL,
        path TEXT NOT NULL,                    -- santykinis nuo nc_dir: projektas/mazgas/centras/failas_vN.ext
        kind TEXT NOT NULL,
        size INTEGER NOT NULL,
        sha256 TEXT NOT NULL,
        note TEXT NOT NULL DEFAULT '',
        current INTEGER NOT NULL DEFAULT 1,    -- 0 – senesnė versija arba pašalintas
        needs_ack INTEGER NOT NULL DEFAULT 0,  -- pakeistas po išleidimo: meistras turi patvirtinti
        uploaded_by INTEGER REFERENCES users(id),
        uploaded_at TEXT NOT NULL,
        acked_by INTEGER REFERENCES users(id),
        acked_at TEXT
    );
    CREATE INDEX ix_task_files ON task_files (task_id, current);
    """,
    # 10 – planavimo signalai: pokyčių žurnalas ir asmeniniai pranešimai
    """
    CREATE TABLE plan_changes (
        id INTEGER PRIMARY KEY,
        at TEXT NOT NULL,
        user_id INTEGER REFERENCES users(id),
        kind TEXT NOT NULL,                    -- phase / priority / queue / activate / shop_delay / component_delay
        project_id INTEGER REFERENCES projects(id),
        summary TEXT NOT NULL,
        note TEXT NOT NULL DEFAULT '',
        impact TEXT NOT NULL DEFAULT '{}',     -- JSON: paveikti projektai ir priežastys
        key TEXT UNIQUE                        -- tas pats signalas (pvz. tos pačios pauzės) – tik kartą
    );
    CREATE INDEX ix_plan_changes_at ON plan_changes (at);
    CREATE TABLE notifications (
        id INTEGER PRIMARY KEY,
        user_id INTEGER NOT NULL REFERENCES users(id),
        project_id INTEGER REFERENCES projects(id),
        change_id INTEGER REFERENCES plan_changes(id),
        kind TEXT NOT NULL,
        severity TEXT NOT NULL DEFAULT 'info', -- red / yellow / info / good
        title TEXT NOT NULL,
        body TEXT NOT NULL DEFAULT '',
        link TEXT NOT NULL DEFAULT '',
        key TEXT NOT NULL,                     -- tas pats signalas tam pačiam žmogui – vieną kartą
        created TEXT NOT NULL,
        read_at TEXT,
        UNIQUE (user_id, key)
    );
    CREATE INDEX ix_notifications_user ON notifications (user_id, read_at);
    """,
    # 11 – cecho planas: barų ir centrų vieta plane (JSON {x, y, w, h}; centro –
    # baro viduje, kad perkeliant barą centrai keliautų kartu). NULL – automatinė
    """
    ALTER TABLE areas ADD COLUMN layout TEXT;
    ALTER TABLE work_centres ADD COLUMN layout TEXT;
    """,
    # 12 – kokybė pagal EN 1090 / ISO 3834: patikros maršrute, medžiagų
    # sertifikatai ir lydiniai, suvirintojų kvalifikacijos ir WPS, NCR 8D
    """
    ALTER TABLE projects ADD COLUMN exc_class TEXT NOT NULL DEFAULT '';   -- '', EXC1…EXC4
    ALTER TABLE tasks ADD COLUMN wps_id INTEGER REFERENCES wps(id);
    CREATE TABLE check_templates (
        id INTEGER PRIMARY KEY,
        code TEXT NOT NULL UNIQUE,
        name TEXT NOT NULL,
        kind TEXT NOT NULL DEFAULT 'check',     -- check (OK / NOK) / measure (skaičius su tolerancija)
        unit TEXT NOT NULL DEFAULT '',
        nominal REAL, tol_minus REAL, tol_plus REAL,
        performer TEXT NOT NULL DEFAULT 'operator',   -- operator – savikontrolė / qc – kokybės kontrolė
        instruction TEXT NOT NULL DEFAULT '',
        active INTEGER NOT NULL DEFAULT 1
    );
    CREATE TABLE task_checks (
        id INTEGER PRIMARY KEY,
        task_id INTEGER NOT NULL REFERENCES tasks(id),
        template_id INTEGER REFERENCES check_templates(id),
        name TEXT NOT NULL,
        kind TEXT NOT NULL DEFAULT 'check',
        unit TEXT NOT NULL DEFAULT '',
        nominal REAL, tol_minus REAL, tol_plus REAL,
        performer TEXT NOT NULL DEFAULT 'operator',
        instruction TEXT NOT NULL DEFAULT '',
        sort INTEGER NOT NULL DEFAULT 0,
        status TEXT NOT NULL DEFAULT 'laukia',  -- laukia / ok / nok / isimtis
        value REAL,
        done_by INTEGER REFERENCES users(id),
        done_at TEXT,
        ncr_id INTEGER REFERENCES ncr(id),
        waiver_reason TEXT NOT NULL DEFAULT ''
    );
    CREATE INDEX ix_task_checks ON task_checks (task_id);
    -- kiekvienas matavimas atskirai: pakartotinis po taisymo neištrina pirmojo
    CREATE TABLE check_results (
        id INTEGER PRIMARY KEY,
        check_id INTEGER NOT NULL REFERENCES task_checks(id),
        ok INTEGER NOT NULL,
        value REAL,
        note TEXT NOT NULL DEFAULT '',
        kind TEXT NOT NULL DEFAULT 'result',    -- result / waiver
        user_id INTEGER REFERENCES users(id),
        at TEXT NOT NULL
    );
    CREATE TABLE material_lots (
        id INTEGER PRIMARY KEY,
        heat_no TEXT NOT NULL,                  -- lydinio numeris (iš sertifikato)
        material TEXT NOT NULL,                 -- pvz. S355J2+N, AISI 304
        product TEXT NOT NULL DEFAULT '',       -- lakštas t10 3000×1500, vamzdis 60×5 …
        supplier TEXT NOT NULL DEFAULT '',
        cert_no TEXT NOT NULL DEFAULT '',
        cert_type TEXT NOT NULL DEFAULT '3.1',  -- EN 10204: 2.2 / 3.1 / 3.2
        cert_file TEXT,
        qty REAL NOT NULL DEFAULT 0,
        unit TEXT NOT NULL DEFAULT 'vnt',
        status TEXT NOT NULL DEFAULT 'tinkama', -- tinkama / blokuota
        note TEXT NOT NULL DEFAULT '',
        received_at TEXT NOT NULL,
        received_by INTEGER REFERENCES users(id),
        UNIQUE (heat_no, material, product)
    );
    CREATE TABLE task_materials (
        id INTEGER PRIMARY KEY,
        task_id INTEGER NOT NULL REFERENCES tasks(id),
        lot_id INTEGER NOT NULL REFERENCES material_lots(id),
        qty REAL NOT NULL DEFAULT 1,
        user_id INTEGER REFERENCES users(id),
        at TEXT NOT NULL
    );
    CREATE INDEX ix_task_materials ON task_materials (task_id);
    CREATE TABLE wps (
        id INTEGER PRIMARY KEY,
        code TEXT NOT NULL UNIQUE,
        process TEXT NOT NULL,                  -- ISO 4063: 135, 141, 111, 136 …
        material_group TEXT NOT NULL,           -- ISO/TR 15608: 1.1, 1.2, 8.1 …
        description TEXT NOT NULL DEFAULT '',
        file TEXT,
        active INTEGER NOT NULL DEFAULT 1
    );
    CREATE TABLE qualifications (
        id INTEGER PRIMARY KEY,
        user_id INTEGER NOT NULL REFERENCES users(id),
        standard TEXT NOT NULL DEFAULT 'ISO 9606-1',
        process TEXT NOT NULL,
        material_group TEXT NOT NULL,
        cert_no TEXT NOT NULL DEFAULT '',
        valid_until TEXT NOT NULL,
        file TEXT,
        note TEXT NOT NULL DEFAULT '',
        active INTEGER NOT NULL DEFAULT 1
    );
    ALTER TABLE ncr ADD COLUMN containment TEXT NOT NULL DEFAULT '';   -- D3 laikini veiksmai
    ALTER TABLE ncr ADD COLUMN root_cause TEXT NOT NULL DEFAULT '';    -- D4 šakninė priežastis
    ALTER TABLE ncr ADD COLUMN corrective TEXT NOT NULL DEFAULT '';    -- D5–D6 korekciniai veiksmai
    ALTER TABLE ncr ADD COLUMN preventive TEXT NOT NULL DEFAULT '';    -- D7 kad nepasikartotų
    ALTER TABLE ncr ADD COLUMN disposition TEXT NOT NULL DEFAULT '';   -- sprendimas dėl gaminio
    ALTER TABLE ncr ADD COLUMN check_id INTEGER REFERENCES task_checks(id);
    CREATE TABLE ncr_files (
        id INTEGER PRIMARY KEY,
        ncr_id INTEGER NOT NULL REFERENCES ncr(id),
        name TEXT NOT NULL,
        stored TEXT NOT NULL,
        user_id INTEGER REFERENCES users(id),
        at TEXT NOT NULL
    );
    """,
    # 13 – darbo kalendorius: pamainų šablonai (gamyklai, barui, centrui) ir
    # dienų išimtys (nedarbo diena, remontas, papildomas darbas, kitas laikas).
    # Laikas – vietinis (HH:MM), nes pamaina nesikeičia keičiantis vasaros laikui.
    """
    CREATE TABLE shift_patterns (
        id INTEGER PRIMARY KEY,
        name TEXT NOT NULL UNIQUE,
        week TEXT NOT NULL,                     -- JSON {"0": "07:00-11:00, 11:30-15:30", … "6": ""}, 0 – pirmadienis
        active INTEGER NOT NULL DEFAULT 1
    );
    INSERT INTO shift_patterns (name, week) VALUES
        ('1 pamaina', '{"0":"07:00-11:00, 11:30-15:30","1":"07:00-11:00, 11:30-15:30","2":"07:00-11:00, 11:30-15:30","3":"07:00-11:00, 11:30-15:30","4":"07:00-11:00, 11:30-15:30","5":"","6":""}'),
        ('2 pamainos', '{"0":"06:00-10:00, 10:30-18:30, 19:00-23:00","1":"06:00-10:00, 10:30-18:30, 19:00-23:00","2":"06:00-10:00, 10:30-18:30, 19:00-23:00","3":"06:00-10:00, 10:30-18:30, 19:00-23:00","4":"06:00-10:00, 10:30-18:30, 19:00-23:00","5":"","6":""}');
    INSERT INTO settings (key, value) VALUES ('factory_pattern', '1');
    ALTER TABLE areas ADD COLUMN shift_pattern_id INTEGER REFERENCES shift_patterns(id);
    ALTER TABLE work_centres ADD COLUMN shift_pattern_id INTEGER REFERENCES shift_patterns(id);
    CREATE TABLE calendar_days (
        id INTEGER PRIMARY KEY,
        scope TEXT NOT NULL,                    -- factory / area / centre
        scope_id INTEGER NOT NULL DEFAULT 0,    -- gamyklai 0
        day TEXT NOT NULL,                      -- YYYY-MM-DD
        kind TEXT NOT NULL,                     -- nedarbo / remontas / papildomas / kitas
        hours TEXT NOT NULL DEFAULT '',         -- „07:00-15:30“; remontui tuščia – visa diena
        note TEXT NOT NULL DEFAULT '',
        user_id INTEGER REFERENCES users(id),
        at TEXT NOT NULL,
        UNIQUE (scope, scope_id, day)
    );
    """,
    # 14 – rolės bazėje (redaguojamos lange), individualios vartotojo teisių
    # išimtys ir teisių pakeitimų žurnalas (auditui). Įprastos rolės įrašomos
    # paleidžiant (`auth.ensure_roles`) – jų sąrašas gyvena kode.
    """
    CREATE TABLE roles (
        code TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        perms TEXT NOT NULL DEFAULT '',        -- teisės per kablelį
        scope TEXT NOT NULL DEFAULT 'all',     -- all / own: bare ribojami veiksmai tik savo baruose
        description TEXT NOT NULL DEFAULT '',
        system INTEGER NOT NULL DEFAULT 0,     -- įprasta rolė: pašalinti negalima
        sort INTEGER NOT NULL DEFAULT 0
    );
    ALTER TABLE users ADD COLUMN perm_add TEXT NOT NULL DEFAULT '';
    ALTER TABLE users ADD COLUMN perm_remove TEXT NOT NULL DEFAULT '';
    CREATE TABLE access_log (
        id INTEGER PRIMARY KEY,
        at TEXT NOT NULL,
        by_id INTEGER REFERENCES users(id),
        target TEXT NOT NULL,                  -- user / role
        target_id TEXT NOT NULL,               -- vartotojo id arba rolės kodas
        summary TEXT NOT NULL,                 -- žmonių kalba: kas pakeista
        data TEXT NOT NULL DEFAULT '{}'
    );
    CREATE INDEX ix_access_log ON access_log (target, target_id, at);
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
