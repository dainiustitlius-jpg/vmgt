"""Darbo kalendorius: kada dirba gamykla, barai ir darbo centrai.

Vartotojo sprendimai (2026-10-26): lygiai **gamykla → baras → centras**
(gamyklos pamaina ir šventės visiems, baras gali turėti savo pamainas,
centras – savo išimtis); žymima **pamainos, šventės ir nedarbo dienos,
remontai, papildomas darbas**; kalendorius veikia **apkrovą, operacijų
prognozę, cechą ir terminalą, planuotojo Gantt**; redaguojama **metiniame
kalendoriuje**.

Laikas kalendoriuje – vietinis (Lietuva), nes pamaina „07:00–15:30“ ceche
nesikeičia pasikeitus vasaros laikui; bazėje viskas UTC (`db.now`). Zonos
poslinkis skaičiuojamas ES taisykle (paskutinis kovo ir spalio sekmadienis),
ne `zoneinfo`: Windows Python be `tzdata` paketo zonų neturi.

Dienos darbo laikas sudedamas taip:

1. pamainų šablonas – centro, jei nėra – baro, jei nėra – gamyklos;
2. valstybinė šventė – nedarbo diena;
3. išimtys iš eilės: gamyklos, baro, centro. Kiekviena keičia ankstesnį
   rezultatą: nedarbo – nieko, remontas – atima (be laiko – visą dieną),
   papildomas – prideda, kitas laikas – pakeičia.

Tad šventę galima paversti darbo diena (gamyklos „kitas laikas“), o centro
remontas nepaliečia kitų baro centrų.
"""

from __future__ import annotations

import json
import re
from datetime import date, datetime, timedelta, timezone

from .. import db
from . import NotFound, RuleError

KINDS = {"nedarbo": "Nedarbo diena", "remontas": "Remontas / priežiūra", "papildomas": "Papildomas darbas",
         "kitas": "Kitas darbo laikas"}
# dienos rūšys, kurias mato vartotojas (be išimčių – darbo, poilsio, šventė)
DAY_LABEL = {"darbo": "Darbo diena", "poilsio": "Poilsio diena", "svente": "Šventė", **KINDS}
SCOPES = ("factory", "area", "centre")
WEEKDAYS = ["Pr", "An", "Tr", "Kt", "Pn", "Št", "Sk"]
MAX_DAYS = 370              # ilgiausias laikotarpis vienu veiksmu ir paieškos riba

_FIXED = {(1, 1): "Naujieji metai", (2, 16): "Valstybės atkūrimo diena", (3, 11): "Nepriklausomybės atkūrimo diena",
          (5, 1): "Tarptautinė darbo diena", (6, 24): "Joninės", (7, 6): "Valstybės (karaliaus Mindaugo karūnavimo) diena",
          (8, 15): "Žolinė", (11, 1): "Visų šventųjų diena", (11, 2): "Vėlinės", (12, 24): "Kūčios",
          (12, 25): "Kalėdos", (12, 26): "Kalėdos (antra diena)"}


def easter(y: int) -> date:
    """Velykų sekmadienis (Grigaliaus kalendorius, anoniminis algoritmas)."""
    a, b, c = y % 19, y // 100, y % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    return date(y, month, (h + l - 7 * m + 114) % 31 + 1)


def holidays(y: int) -> dict[date, str]:
    """Lietuvos valstybinės šventės (Darbo kodeksas, 123 str.). Motinos ir
    Tėvo dienos – sekmadieniai, tad darbo laikui įtakos neturi."""
    out = {date(y, m, d): n for (m, d), n in _FIXED.items()}
    e = easter(y)
    out[e] = "Velykos"
    out[e + timedelta(days=1)] = "Velykų antroji diena"
    return out


def _last_sunday(y, m) -> date:
    d = date(y, m, 31)
    return d - timedelta(days=(d.weekday() + 1) % 7)


def utc_offset(d: date) -> int:
    """Lietuvos laiko poslinkis valandomis: vasarą +3, žiemą +2."""
    return 3 if _last_sunday(d.year, 3) <= d < _last_sunday(d.year, 10) else 2


def local_date(ts: datetime) -> date:
    x = ts.astimezone(timezone.utc)
    return (x + timedelta(hours=utc_offset((x + timedelta(hours=2)).date()))).date()


def local_text(iso: str | None) -> str:
    """UTC laikas → „MM-DD HH:MM“ vietos laiku (pranešimų tekstams)."""
    if not iso:
        return "—"
    x = db.parse_ts(iso).astimezone(timezone.utc)
    return (x + timedelta(hours=utc_offset(local_date(x)))).strftime("%m-%d %H:%M")


# ---------- laiko intervalai ----------

_HM = re.compile(r"^\s*(\d{1,2})(?::(\d{2}))?\s*[-–]\s*(\d{1,2})(?::(\d{2}))?\s*$")


def parse_hours(text: str) -> list[tuple[int, int]]:
    """„07:00-11:00, 11:30-15:30“ → [(420, 660), (690, 930)] minutėmis nuo vidurnakčio.
    Persidengiantys sujungiami; naktinė pamaina per vidurnaktį – dviem dalimis."""
    out = []
    for part in [p for p in re.split(r"[,;\n]+", text or "") if p.strip()]:
        m = _HM.match(part)
        if not m:
            raise RuleError(f"Netinkamas laikas „{part.strip()}“ – rašykite pvz. 07:00-15:30")
        a = int(m[1]) * 60 + int(m[2] or 0)
        b = int(m[3]) * 60 + int(m[4] or 0)
        if not (0 <= a < b <= 24 * 60) or int(m[2] or 0) > 59 or int(m[4] or 0) > 59:
            raise RuleError(f"Netinkamas laikas „{part.strip()}“: pabaiga turi būti po pradžios, iki 24:00 "
                            "(naktinę pamainą rašykite dviem dalimis: 22:00-24:00, 00:00-06:00)")
        out.append((a, b))
    return _union(out)


def _union(iv) -> list[tuple[int, int]]:
    out = []
    for a, b in sorted(iv):
        if out and a <= out[-1][1]:
            out[-1] = (out[-1][0], max(out[-1][1], b))
        else:
            out.append((a, b))
    return out


def _minus(iv, cut) -> list[tuple[int, int]]:
    out = []
    for a, b in iv:
        parts = [(a, b)]
        for c, d in cut:
            parts = [p for x, y in parts for p in ((x, min(y, c)), (max(x, d), y)) if p[1] > p[0]]
        out += parts
    return out


def fmt_hours(iv) -> str:
    f = lambda m: f"{m // 60:02d}:{m % 60:02d}"
    return ", ".join(f"{f(a)}-{f(b)}" for a, b in iv)


def minutes(iv) -> int:
    return sum(b - a for a, b in iv)


# ---------- kalendorius ----------

class Calendar:
    """Visas kalendorius vienai užklausai: duomenys įkeliami vieną kartą,
    dienos – talpinamos (prognozė jų klausia tūkstančius kartų)."""

    def __init__(self, con):
        self.patterns = {}
        for p in db.rows(con.execute("SELECT * FROM shift_patterns ORDER BY id")):
            raw = json.loads(p["week"] or "{}")
            p["days"] = [parse_hours(raw.get(str(i), "")) for i in range(7)]
            p["text"] = [raw.get(str(i), "") for i in range(7)]
            p["week_minutes"] = sum(minutes(x) for x in p["days"])
            self.patterns[p["id"]] = p
        r = con.execute("SELECT value FROM settings WHERE key='factory_pattern'").fetchone()
        self.factory_pattern = int(r[0]) if r and int(r[0]) in self.patterns else next(iter(self.patterns), None)
        self.areas = {a["id"]: a for a in db.rows(con.execute("SELECT id, code, name, shift_pattern_id FROM areas"))}
        self.centres = {c["id"]: c for c in db.rows(con.execute(
            "SELECT id, code, name, area_id, shift_pattern_id, active FROM work_centres"))}
        self.exc = {}
        for e in db.rows(con.execute("SELECT * FROM calendar_days")):
            e["iv"] = parse_hours(e["hours"])
            self.exc.setdefault((e["scope"], e["scope_id"]), {})[e["day"]] = e
        self._hol = {}
        self._days = {}
        self._win = {}

    # --- kuris šablonas ir kurios išimtys taikomos ---

    def chain(self, scope, sid) -> list[tuple[str, int]]:
        if scope == "factory":
            return [("factory", 0)]
        if scope == "area":
            return [("factory", 0), ("area", sid)]
        c = self.centres.get(sid) or {}
        return [("factory", 0)] + ([("area", c["area_id"])] if c.get("area_id") else []) + [("centre", sid)]

    def pattern_of(self, scope, sid) -> tuple[dict | None, str]:
        """Taikomas šablonas ir iš kur jis (rodoma lange: „paveldėta iš baro“)."""
        if scope == "centre":
            c = self.centres.get(sid) or {}
            if c.get("shift_pattern_id") in self.patterns:
                return self.patterns[c["shift_pattern_id"]], "centre"
            sid, scope = c.get("area_id"), "area"
        if scope == "area" and sid in self.areas and self.areas[sid]["shift_pattern_id"] in self.patterns:
            return self.patterns[self.areas[sid]["shift_pattern_id"]], "area"
        return self.patterns.get(self.factory_pattern), "factory"

    def holiday(self, d: date) -> str | None:
        if d.year not in self._hol:
            self._hol[d.year] = holidays(d.year)
        return self._hol[d.year].get(d)

    def day(self, scope, sid, d: date) -> dict:
        """Dienos darbo laikas: {kind, label, iv, minutes, note, own, src}."""
        key = (scope, sid, d)
        if key in self._days:
            return self._days[key]
        pat, _ = self.pattern_of(scope, sid)
        iv = list(pat["days"][d.weekday()]) if pat else []
        kind, note, src, own = ("darbo" if iv else "poilsio"), "", None, False
        hol = self.holiday(d)
        if hol:
            iv, kind, note = [], "svente", hol
        for level in self.chain(scope, sid):
            e = self.exc.get(level, {}).get(d.isoformat())
            if not e:
                continue
            if e["kind"] == "nedarbo":
                iv = []
            elif e["kind"] == "remontas":
                iv = _minus(iv, e["iv"] or [(0, 24 * 60)])
            elif e["kind"] == "papildomas":
                iv = _union(iv + e["iv"])
            elif e["kind"] == "kitas":
                iv = list(e["iv"])
            kind, note, src, own = e["kind"], e["note"] or (hol or ""), level, level == (scope, sid)
        out = {"date": d.isoformat(), "kind": kind, "label": DAY_LABEL[kind], "iv": iv, "minutes": minutes(iv),
               "hours": fmt_hours(iv), "note": note, "own": own, "src": src}
        self._days[key] = out
        return out

    def normal_minutes(self, scope, sid, d: date) -> int:
        """Kiek šablonas numato be švenčių ir išimčių – pajėgumo santykiui."""
        pat, _ = self.pattern_of(scope, sid)
        return minutes(pat["days"][d.weekday()]) if pat else 0

    def is_work(self, scope, sid, d: date) -> bool:
        return self.day(scope, sid, d)["minutes"] > 0

    # --- tikras laikas (UTC) ---

    def windows(self, scope, sid, d: date) -> list[tuple[datetime, datetime]]:
        """Dienos darbo langai UTC laiku."""
        key = (scope, sid, d)
        if key not in self._win:
            base = datetime(d.year, d.month, d.day, tzinfo=timezone.utc) - timedelta(hours=utc_offset(d))
            self._win[key] = [(base + timedelta(minutes=a), base + timedelta(minutes=b))
                              for a, b in self.day(scope, sid, d)["iv"]]
        return self._win[key]

    def add_work(self, scope, sid, start: datetime, seconds: float) -> datetime | None:
        """Kada bus atlikta `seconds` darbo, pradėjus `start` (tik darbo laiku).
        0 sekundžių – artimiausia darbo laiko akimirka. None – metus nedirba."""
        cur, left = start, max(0.0, seconds)
        d = local_date(start)
        for _ in range(MAX_DAYS):
            for a, b in self.windows(scope, sid, d):
                if b <= cur:
                    continue
                s = max(a, cur)
                avail = (b - s).total_seconds()
                if left <= avail:
                    return s + timedelta(seconds=left)
                left -= avail
                cur = b
            d += timedelta(days=1)
        return None

    def status(self, scope, sid, now: datetime) -> dict:
        """Ar dabar darbo laikas; jei ne – kodėl ir kada prasidės."""
        d = local_date(now)
        info = self.day(scope, sid, d)
        working = any(a <= now < b for a, b in self.windows(scope, sid, d))
        nxt = None if working else self.add_work(scope, sid, now, 0)
        if working:
            why = ""
        elif info["kind"] in ("svente", "nedarbo", "poilsio") or (info["kind"] == "remontas" and not info["iv"]):
            why = info["label"] + (f": {info['note']}" if info["note"] else "")
        elif info["kind"] == "remontas":
            why = "Remontas / priežiūra" + (f": {info['note']}" if info["note"] else "") + f" (dirba {info['hours']})"
        else:
            why = f"Ne darbo laikas (šiandien {info['hours']})"
        return {"working": working, "kind": info["kind"], "why": why,
                "next": nxt.isoformat(timespec="minutes") if nxt else None}


# ---------- keitimas ----------

def _scope_name(con, scope, sid) -> str:
    if scope == "factory":
        return "Gamykla"
    tbl = "areas" if scope == "area" else "work_centres"
    r = con.execute(f"SELECT code, name FROM {tbl} WHERE id=?", (sid,)).fetchone()
    if not r:
        raise NotFound("Baro ar centro nėra")
    return f"{r['code']} {r['name']}"


def _check_scope(scope, sid) -> tuple[str, int]:
    if scope not in SCOPES:
        raise RuleError("Nežinoma kalendoriaus sritis")
    return scope, 0 if scope == "factory" else int(sid or 0)


def list_patterns(con) -> list[dict]:
    cal = Calendar(con)
    used = {}
    for a in cal.areas.values():
        if a["shift_pattern_id"]:
            used.setdefault(a["shift_pattern_id"], []).append(a["code"])
    for c in cal.centres.values():
        if c["shift_pattern_id"]:
            used.setdefault(c["shift_pattern_id"], []).append(c["code"])
    return [{"id": p["id"], "name": p["name"], "week": p["text"], "active": p["active"],
             "week_hours": round(p["week_minutes"] / 60, 1), "factory": p["id"] == cal.factory_pattern,
             "used_by": used.get(p["id"], [])} for p in cal.patterns.values()]


def save_pattern(con, by, data: dict, pattern_id=None) -> int:
    name = (data.get("name") or "").strip()
    week = data.get("week")
    if not isinstance(week, list) or len(week) != 7:
        raise RuleError("Šablonui reikia 7 savaitės dienų")
    week = [(w or "").strip() for w in week]
    norm = {str(i): fmt_hours(parse_hours(w)) for i, w in enumerate(week)}      # patikrina ir sutvarko
    if not name:
        raise RuleError("Nurodykite šablono pavadinimą")
    if con.execute("SELECT 1 FROM shift_patterns WHERE name=? AND id!=?", (name, pattern_id or 0)).fetchone():
        raise RuleError(f"Šablonas „{name}“ jau yra")
    if pattern_id is None:
        cur = con.execute("INSERT INTO shift_patterns (name, week) VALUES (?,?)", (name, json.dumps(norm)))
        db.log_event(con, by, "shift_pattern", cur.lastrowid, "create", {"name": name, "week": norm})
        return cur.lastrowid
    if not con.execute("SELECT 1 FROM shift_patterns WHERE id=?", (pattern_id,)).fetchone():
        raise NotFound("Šablono nėra")
    con.execute("UPDATE shift_patterns SET name=?, week=? WHERE id=?", (name, json.dumps(norm), pattern_id))
    db.log_event(con, by, "shift_pattern", pattern_id, "update", {"name": name, "week": norm})
    return pattern_id


def set_pattern(con, by, scope, sid, pattern_id) -> None:
    """Kurį šabloną naudoja gamykla, baras ar centras. None – paveldėti
    (gamyklai privalomas – nuo jo paveldi visi)."""
    scope, sid = _check_scope(scope, sid)
    pattern_id = int(pattern_id) if pattern_id else None
    if pattern_id and not con.execute("SELECT 1 FROM shift_patterns WHERE id=?", (pattern_id,)).fetchone():
        raise NotFound("Šablono nėra")
    if scope == "factory":
        if not pattern_id:
            raise RuleError("Gamyklai šablonas privalomas – nuo jo paveldi visi barai ir centrai")
        con.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('factory_pattern', ?)", (str(pattern_id),))
    else:
        _scope_name(con, scope, sid)
        con.execute(f"UPDATE {'areas' if scope == 'area' else 'work_centres'} SET shift_pattern_id=? WHERE id=?",
                    (pattern_id, sid))
    db.log_event(con, by, "calendar", sid, "pattern", {"scope": scope, "pattern_id": pattern_id})


def set_days(con, by, data: dict) -> dict:
    """Pažymi dienų intervalą [from, to]: `kind` – išimtis arba „iprasta“
    (išimtį pašalinti). Grąžina, kiek dienų pakeista."""
    scope, sid = _check_scope(data.get("scope"), data.get("scope_id"))
    name = _scope_name(con, scope, sid)
    kind = data.get("kind")
    if kind != "iprasta" and kind not in KINDS:
        raise RuleError("Nežinoma dienos rūšis")
    try:
        a = date.fromisoformat(data.get("from") or "")
        b = date.fromisoformat(data.get("to") or data.get("from") or "")
    except ValueError:
        raise RuleError("Nurodykite datas") from None
    if b < a:
        raise RuleError("Pabaiga negali būti prieš pradžią")
    if (b - a).days >= MAX_DAYS:
        raise RuleError("Vienu kartu – ne daugiau kaip metai")
    hours = fmt_hours(parse_hours(data.get("hours") or ""))
    note = (data.get("note") or "").strip()
    if kind in ("papildomas", "kitas") and not hours:
        raise RuleError(f"{KINDS[kind]}: nurodykite laiką, pvz. 07:00-13:00")
    if kind == "remontas" and not note:
        raise RuleError("Remontui nurodykite, kas daroma (matys meistras ir planuotojas)")
    days = [a + timedelta(days=i) for i in range((b - a).days + 1)]
    if data.get("workdays_only"):
        cal = Calendar(con)
        days = [d for d in days if cal.day(scope, sid, d)["kind"] not in ("poilsio", "svente")]
    for d in days:
        con.execute("DELETE FROM calendar_days WHERE scope=? AND scope_id=? AND day=?", (scope, sid, d.isoformat()))
        if kind != "iprasta":
            con.execute("INSERT INTO calendar_days (scope, scope_id, day, kind, hours, note, user_id, at) "
                        "VALUES (?,?,?,?,?,?,?,?)", (scope, sid, d.isoformat(), kind, hours, note, by, db.now()))
    db.log_event(con, by, "calendar", sid, "days", {"scope": scope, "from": a.isoformat(), "to": b.isoformat(),
                                                    "kind": kind, "hours": hours, "note": note, "days": len(days)})
    label = "įprasta" if kind == "iprasta" else KINDS[kind].lower()
    span = a.isoformat() if a == b else f"{a.isoformat()}…{b.isoformat()}"
    return {"days": len(days), "summary": f"{name}: {span} – {label}{f' {hours}' if hours else ''}"
                                          f"{f' ({note})' if note else ''}"}


# ---------- metų vaizdas ----------

def year_view(con, scope, sid, year: int) -> dict:
    scope, sid = _check_scope(scope, sid)
    cal = Calendar(con)
    pat, src = cal.pattern_of(scope, sid)
    own = None
    if scope == "factory":
        own = cal.factory_pattern
    elif scope == "area":
        own = (cal.areas.get(sid) or {}).get("shift_pattern_id")
    else:
        own = (cal.centres.get(sid) or {}).get("shift_pattern_id")
    d, days = date(year, 1, 1), []
    while d.year == year:
        x = cal.day(scope, sid, d)
        days.append({k: x[k] for k in ("date", "kind", "minutes", "hours", "note", "own")}
                    | {"src": "/".join(map(str, x["src"])) if x["src"] else None})
        d += timedelta(days=1)
    exc = []
    for level in cal.chain(scope, sid):
        for e in sorted(cal.exc.get(level, {}).values(), key=lambda e: e["day"]):
            if not e["day"].startswith(str(year)):
                continue
            last = exc[-1] if exc else None
            # vienodos iš eilės einančios dienos – viena eilutė
            if last and last["level"] == level and last["kind"] == e["kind"] and last["hours"] == e["hours"] \
                    and last["note"] == e["note"] and date.fromisoformat(last["to"]) + timedelta(days=1) == date.fromisoformat(e["day"]):
                last["to"] = e["day"]
                last["days"] += 1
                continue
            exc.append({"level": level, "from": e["day"], "to": e["day"], "days": 1, "kind": e["kind"],
                        "label": KINDS[e["kind"]], "hours": e["hours"], "note": e["note"],
                        "where": _scope_name(con, *level) if level[0] != "factory" else "Gamykla",
                        "own": level == (scope, sid)})
    exc.sort(key=lambda e: (e["from"], not e["own"]))
    hol = [{"date": k.isoformat(), "name": v} for k, v in sorted(holidays(year).items())]
    work_days = sum(1 for x in days if x["minutes"])
    return {"scope": scope, "scope_id": sid, "name": _scope_name(con, scope, sid), "year": year,
            "pattern": {"id": pat["id"], "name": pat["name"], "week": pat["text"],
                        "week_hours": round(pat["week_minutes"] / 60, 1)} if pat else None,
            "pattern_src": src, "own_pattern": own, "days": days, "exceptions": exc, "holidays": hol,
            "totals": {"work_days": work_days, "hours": round(sum(x["minutes"] for x in days) / 60, 1)},
            "kinds": KINDS, "day_labels": DAY_LABEL}


def centre_status(con, cal: Calendar | None = None, now: str | None = None) -> dict:
    """Visų centrų „ar dabar darbo laikas“ – cechui ir terminalui."""
    cal = cal or Calendar(con)
    ts = db.parse_ts(now or db.now())
    return {cid: cal.status("centre", cid, ts) for cid in cal.centres}
