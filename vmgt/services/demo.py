"""Pavyzdiniai projektai su visu technologiniu keliu ir istorija.

Penki projektai skirtingose stadijose – nuo baigto iki ką tik išleisto į
gamybą – su problemomis, jų sprendimais ir neatitiktimis. Istorija kuriama
NE įrašant duomenis tiesiai į lenteles, o tais pačiais veiksmais kaip ceche ir
biure (išleidimas, Start / Pauzė / Stop, neatitiktys, susitikimai, gavimai):
tad ji paklūsta toms pačioms taisyklėms, o analitika, sveikata, apkrova ir
atsekamumas rodo nuoseklius skaičius.

Kaip veikia: kiekviena operacija suplanuojama darbo pamainomis (I–V,
05:00–13:30 UTC ≈ 07/08–15:30 vietos laiku), kai jos darbo centras laisvas ir
ankstesnės srauto operacijos baigtos; tada visi įvykiai vykdomi laiko tvarka.
Kas turėtų įvykti po „dabar“, neįvyksta – todėl dabartinė būsena (kas dirba,
kas pristabdyta pamainos pabaigoje, kas laukia) atsiranda savaime ir atitinka
paleidimo momentą.

`RESERVED` – centrai, kuriuos paskutines dienas naudoja pagrindiniai
pavyzdžiai (`seed.py`, P-24117): čia šie projektai dirba tik iki tol.
"""

from __future__ import annotations

import heapq
import zlib
from datetime import datetime, timedelta

from .. import db
from . import actions, auth, components, drawings, meetings, ncfiles, ncr, projects, routing, tasks

SHIFT = (5 * 60, 13 * 60 + 30)            # pamaina minutėmis nuo vidurnakčio (UTC)
RESERVED = {"LAZ-01", "LNK-01", "SV-01"}

# Operatoriai pagal barą (pavyzdiniai, PIN – tik testams)
OPERATORS = [
    ("cnc1", "Andrius Tekintojas", "4001", ["TKB"]),
    ("suv1", "Tomas Suvirintojas", "4002", ["SVB"]),
    ("daz1", "Rimas Dažytojas", "4003", ["DZB"]),
    ("elek1", "Saulius Automatikas", "4004", ["ATB"]),
    ("sur1", "Mindaugas Montuotojas", "4005", ["TIS"]),
]
AREA_OPERATOR = {"MAB": "op1", "TKB": "cnc1", "SVB": "suv1", "DZB": "daz1", "ATB": "elek1", "TIS": "sur1"}
CENTRE_OPERATOR = {"LNK-01": "op2", "PLZ-01": "op2", "SV-06": "op3", "SV-08": "op3"}


def O(part, seq, centre, name, qty, norm, **x):
    """Operacija: detalė ('' – mazgo operacija), seka, centras, pavadinimas,
    kiekis, norma min/vnt. Papildomai: factor (faktas/norma), pauses
    [(dalis 0–1, priežastis, pastaba, min.)], scrap, ncr (žr. NCR)."""
    return {"part": part, "seq": seq, "centre": centre, "name": name, "qty": qty, "norm": norm, **x}


def NCR(category, description, resolution=None, close_days=2, assignee="kokybe", qty=0):
    return {"category": category, "description": description, "resolution": resolution,
            "close_days": close_days, "assignee": assignee, "qty": qty}


def A(code, name, qty, drawing, start, ops, requires="", release=True):
    """Mazgas; `start` – kurią projekto dieną technologas išleidžia maršrutą."""
    return {"code": code, "name": name, "qty": qty, "drawing": drawing, "start": start, "ops": ops,
            "requires": requires, "release": release}


# ---------- scenarijai ----------
# Dienos – nuo projekto pradžios (T0). Komponentai: (prekė, pavadinimas, spec., kiekis, tiekėjas,
# užsakyta, pažadėta, reikia iki, [(gavimo diena, kiekis)]). Etapai: (mazgas, rūšis, atsakingas,
# pradžia, pabaiga, valandos, faktinė pabaiga biuro etapui arba None).

PROJECTS = [
    {
        "code": "P-24095", "name": "Paletizavimo robotų celė PRC-2", "customer": "UAB Baltijos pakuotė",
        "t0": -100, "due": 76, "prio": 2, "done_day": 70,
        "story": "Baigtas: robotas vėlavo, programuota simuliatoriuje; rėmo deformacija ištiesinta; FAT – iš antro karto.",
        "assemblies": [
            A("100", "Celės rėmas", 1, "2495-100", 18, [
                O("2495-101", 10, "PJV-01", "Profilių pjovimas 100×100×5", 12, 6),
                O("2495-102", 10, "LAZ-01", "Tvirtinimo plokščių pjovimas S355 t10", 8, 4),
                O("", 30, "SV-04", "Rėmo surinkimas ir suvirinimas", 1, 720, factor=1.25,
                  ncr=NCR("suvirinimas", "Po suvirinimo rėmo įstrižainių skirtumas 6 mm (leistina 3 mm).",
                          "Rėmas ištiesintas presu, pakartotinai išmatuota – 2 mm. Technologijoje pridėtas "
                          "laikinas standumo statramstis suvirinimo metu.", 2)),
                O("", 40, "SML-01", "Smėliavimas Sa 2,5", 1, 90),
                O("", 50, "DAZ-02", "Miltelinis dažymas RAL 7016", 1, 120,
                  pauses=[(0.9, "kokybe", "Laukiama dangos storio matavimo", 90)],
                  ncr=NCR("pavirsius", "Dangos storis 45 µm dviejose zonose (reikia ≥ 60 µm).",
                          "Zonos perdažytos, išmatuota 70–85 µm. Dažymo kameroje pakeistas pistoleto antgalis.", 1)),
            ]),
            A("200", "Griebtuvas", 1, "2495-200", 20, [
                O("2495-201", 10, "LAZ-01", "Griebtuvo pirštų pjovimas", 6, 5),
                O("2495-201", 20, "LNK-01", "Pirštų lenkimas", 6, 6),
                O("2495-202", 10, "MECH-01", "Jungės frezavimas", 1, 180),
                O("", 30, "SV-05", "Griebtuvo suvirinimas", 1, 240),
                O("", 40, "DAZ-01", "Dažymas RAL 1003", 1, 60),
                O("", 50, "SUR-01", "Pneumatikos montavimas", 1, 180),
            ]),
            A("300", "Elektros spinta", 1, "2495-300", 24, [
                O("", 10, "EL-01", "Spintos montavimas pagal schemą", 1, 960),
            ]),
            A("900", "Celės surinkimas", 1, "2495-900", 26, [
                O("", 10, "SUR-01", "Celės mechaninis surinkimas", 1, 1200),
                O("", 20, "EL-01", "Kabeliai, jutikliai, saugos skeneris", 1, 600),
                O("", 30, "PRG-01", "Roboto ir PLC programavimas", 1, 1500, factor=0.8),
                O("", 40, "TST-01", "FAT su užsakovu", 1, 480, factor=1.6,
                  ncr=NCR("kita", "FAT metu saugos skenerio apsaugos zona per maža – robotas sustoja per vėlai.",
                          "PLC ir skenerio zonos perprogramuotos, pakartotas saugos testas – atitinka PL d. "
                          "Užsakovas FAT pasirašė.", 1, "technologas")),
            ], requires="100,200,300"),
        ],
        "phases": [
            (None, "projektavimas", "vadovas", 0, 14, 160, 15),
            (None, "technologija", "technologas", 12, 20, 40, 21),
            (None, "komponentai", "pirkimai", 10, 40, 30, None),
            (None, "gamyba", "meistras", 18, 45, None, None),
            (None, "surinkimas", "meistras2", 40, 55, None, None),
            (None, "programavimas", "vadovas", 45, 60, 120, None),
            (None, "testavimas", "kokybe", 58, 68, 40, None),
        ],
        "components": [
            ("ROB-PAL-160", "Paletizavimo robotas 160 kg", "4 ašių, 3200 mm sieksnis", 1, "UAB Robotai", 8, 30, 40,
             [(38, 1)]),
            ("EL-PLC-1515", "PLC Siemens S7-1500", "CPU 1515-2 PN", 1, "UAB Automatika", 9, 20, 24, [(19, 1)]),
            ("SAF-SCAN", "Saugos skeneris", "SICK microScan3, PL d", 2, "UAB Saugos sistemos", 10, 28, 30, [(27, 2)]),
            ("PN-VALVE-5", "Pneumatinių vožtuvų blokas", "Festo VTUG, 8 vietos", 1, "UAB Pneumatika", 12, 25, 40,
             [(24, 1)]),
        ],
        "events": [
            ("meeting", 1, "Projekto pradžios susitikimas", ["vadovas", "technologas", "pirkimai", "meistras", "kokybe"],
             "1. Celės išdėstymas\n2. Roboto pasirinkimas\n3. Terminai",
             "Užsakovas pageidauja 4 paletės schemų. Roboto pristatymas – iki 22 d.",
             "Robotas – 160 kg, 4 ašių\nRėmas – suvirintas, miltelinis dažymas RAL 7016",
             [("Užsakyti robotą ir saugos įrangą", "pirkimai", 8, 1), ("Gauti roboto CAD modelį iš tiekėjo", "technologas", 6, 2),
              ("Suderinti paletės schemas su užsakovu", "vadovas", 20, 2), ("Parengti FAT protokolą", "kokybe", 55, 2)]),
            ("status", 2, "Užsakyti robotą", "vykdoma", "pirkimai"), ("status", 8, "Užsakyti robotą", "atlikta", "pirkimai"),
            ("status", 3, "Gauti roboto CAD", "vykdoma", "technologas"), ("status", 6, "Gauti roboto CAD", "atlikta", "technologas"),
            ("status", 5, "Suderinti paletės", "vykdoma", "vadovas"),
            ("status", 9, "Suderinti paletės", "laukia", "vadovas", "Užsakovas dar nepateikė 3-ios ir 4-os schemos"),
            ("comment", 14, "Suderinti paletės", "vadovas", "Gautos visos 4 schemos, patvirtintos el. paštu"),
            ("status", 14, "Suderinti paletės", "vykdoma", "vadovas"), ("status", 15, "Suderinti paletės", "atlikta", "vadovas"),
            ("meeting", 31, "Roboto pristatymo vėlavimas", ["vadovas", "pirkimai", "technologas", "meistras2"],
             "1. Roboto pristatymas\n2. Poveikis terminui",
             "Tiekėjas perkėlė pristatymą 8 d. Mechaninė dalis vyksta pagal planą.",
             "Roboto programą pradėti simuliatoriuje, kol robotas atvyks\nCelės surinkimą pradėti be roboto",
             [("Parengti roboto programą simuliatoriuje", "vadovas", 38, 1)]),
            ("status", 32, "Parengti roboto programą", "vykdoma", "vadovas"),
            ("status", 40, "Parengti roboto programą", "atlikta", "vadovas"),
            ("status", 50, "Parengti FAT protokolą", "vykdoma", "kokybe"),
            ("status", 54, "Parengti FAT protokolą", "perziura", "kokybe"),
            ("status", 55, "Parengti FAT protokolą", "atlikta", "vadovas"),
        ],
    },
    {
        "code": "P-24113", "name": "Vežimėlių transportavimo sistema VTS-6", "customer": "AB Linijų gamyba",
        "t0": -72, "due": 80, "prio": 1,
        "story": "Testuojama: ratų matmenų neatitiktis išspręsta; pozicionavimo paklaida – atvira, sprendžiama.",
        "assemblies": [
            A("100", "Bėgių sekcijos", 6, "2513-100", 18, [
                O("2513-101", 10, "PJV-01", "Bėgių pjovimas", 12, 8),
                O("2513-101", 20, "MECH-01", "Tvirtinimo skylių frezavimas", 12, 12),
                O("2513-102", 10, "PLZ-01", "Atramų pjovimas S355 t12", 24, 3),
                O("2513-102", 20, "LNK-01", "Atramų lenkimas", 24, 4,
                  pauses=[(0.4, "gedimas", "Preso hidraulikos nuotėkis, kviestas servisas", 150)]),
                O("", 30, "SV-06", "Sekcijų suvirinimas", 6, 150),
                O("", 40, "SML-01", "Smėliavimas", 6, 30),
                O("", 50, "DAZ-02", "Miltelinis dažymas RAL 5015", 6, 35),
            ]),
            A("200", "Vežimėliai", 6, "2513-200", 19, [
                O("2513-201", 10, "TEK-02", "Ratų tekinimas", 24, 18, scrap=2,
                  ncr=NCR("matmenys", "2 ratų guolio lizdas Ø52,08 mm (reikia Ø52 H7) – guolis įeina laisvai.",
                          "Pagaminti 2 nauji ratai. Pakeista tekinimo peilio plokštelė, įvesta pirmos detalės "
                          "patikra kalibru.", 2, qty=2)),
                O("2513-202", 10, "LAZ-01", "Platformų pjovimas", 6, 10),
                O("2513-202", 20, "LNK-01", "Platformų lenkimas", 6, 12),
                O("", 30, "SV-07", "Vežimėlio suvirinimas", 6, 120),
                O("", 40, "DAZ-01", "Dažymas RAL 7035", 6, 30),
                O("", 50, "SUR-01", "Ratų ir pavarų montavimas", 6, 90),
            ]),
            A("300", "Valdymo spinta", 1, "2513-300", 22, [
                O("", 10, "EL-01", "Valdymo spintos montavimas", 1, 1200),
            ]),
            A("900", "Sistemos surinkimas", 1, "2513-900", 24, [
                O("", 10, "SUR-01", "Linijos montavimas", 1, 1500),
                O("", 20, "EL-01", "Kabelių trasos ir jutikliai", 1, 720),
                O("", 30, "PRG-01", "PLC ir HMI programavimas", 1, 1800),
                O("", 40, "TST-01", "Funkcinis testas ir FAT", 1, 2400, factor=1.0,
                  ncr=NCR("surinkimas", "Vežimėlio pozicionavimo paklaida ±4 mm (reikia ±1 mm) stotelėse 3 ir 5.",
                          None, assignee="technologas"), ncr_at="start"),
            ], requires="100,200,300"),
        ],
        "phases": [
            (None, "projektavimas", "vadovas", 0, 14, 200, 14),
            (None, "technologija", "technologas", 12, 19, 50, 19),
            (None, "komponentai", "pirkimai", 10, 45, 30, None),
            (None, "gamyba", "meistras", 18, 48, None, None),
            (None, "surinkimas", "meistras2", 45, 60, None, None),
            (None, "programavimas", "vadovas", 50, 66, 140, None),
            (None, "testavimas", "kokybe", 66, 76, 60, None),
        ],
        "components": [
            ("DRV-MOT-037", "Vežimėlio pavara 0,37 kW", "su stabdžiu, 24 V", 6, "UAB Pavaros", 10, 32, 40, [(31, 4), (39, 2)]),
            ("SNS-ENC", "Absoliutus enkoderis", "SSI, 13 bit", 6, "UAB Automatika", 11, 30, 50, [(29, 6)]),
            ("EL-HMI-10", "Operatoriaus pultas 10\"", "Siemens TP1000", 1, "UAB Automatika", 11, 35, 45, [(36, 1)]),
            ("RAIL-SPR", "Bėgių sujungimo plokštelės", "cinkuotos", 30, "UAB Metalo prekyba", 15, 25, 30, [(24, 30)]),
        ],
        "events": [
            ("meeting", 1, "Projekto pradžios susitikimas", ["vadovas", "technologas", "pirkimai", "meistras", "meistras2"],
             "1. Sistemos apimtis\n2. Pavarų pasirinkimas\n3. Bandymų tvarka",
             "6 vežimėliai, 6 bėgių sekcijos. Užsakovas reikalauja ±1 mm pozicionavimo.",
             "Pozicionavimui – absoliutūs enkoderiai\nFAT – užsakovo patalpose nedaroma, tik pas mus",
             [("Užsakyti pavaras ir enkoderius", "pirkimai", 11, 1), ("Parengti FAT programą", "kokybe", 60, 2)]),
            ("status", 2, "Užsakyti pavaras", "vykdoma", "pirkimai"), ("status", 11, "Užsakyti pavaras", "atlikta", "pirkimai"),
            ("meeting", 40, "Savaitinis susitikimas: ratų neatitiktis", ["vadovas", "kokybe", "meistras", "technologas"],
             "1. NCR – ratų guolio lizdai\n2. Pavarų pristatymas",
             "Du ratai netinkami. Pavarų tiekėjas pristatė 4 iš 6.",
             "Ratus perdaryti, įvesti pirmos detalės patikrą\nVežimėlius 5–6 montuoti, kai atvyks pavaros",
             [("Įvesti pirmos detalės patikrą tekinimo bare", "kokybe", 45, 2)]),
            ("status", 41, "Įvesti pirmos detalės", "vykdoma", "kokybe"),
            ("status", 44, "Įvesti pirmos detalės", "atlikta", "kokybe"),
            ("status", 62, "Parengti FAT programą", "vykdoma", "kokybe"),
            ("status", 66, "Parengti FAT programą", "atlikta", "kokybe"),
            ("meeting", 70, "Testavimo eiga: pozicionavimas", ["vadovas", "technologas", "kokybe", "meistras2"],
             "1. Pozicionavimo paklaida\n2. FAT data",
             "Stotelėse 3 ir 5 paklaida ±4 mm. Priežastis – bėgių sujungimų laisvumas arba enkoderio kalibravimas.",
             "Pirma patikrinti bėgių sujungimus\nJei nepadės – kalibruoti enkoderius ir pridėti stabdymo rampą PLC",
             [("Patikrinti bėgių sujungimus stotelėse 3 ir 5", "technologas", 71, 1),
              ("Pridėti stabdymo rampą PLC programoje", "vadovas", 73, 1)]),
            ("status", 70, "Patikrinti bėgių sujungimus", "vykdoma", "technologas"),
        ],
    },
    {
        "code": "P-24102", "name": "Sraigtiniai transporteriai ST-400 (2 vnt.)", "customer": "AB Grūdų terminalas",
        "t0": -48, "due": 58, "prio": 1,
        "story": "Gamyba / surinkimas: lenkimo kampas pataisytas programos v2; velenas perdarytas; motoreduktoriai vėluoja.",
        "assemblies": [
            A("100", "Lovys", 2, "2502-100", 14, [
                O("2502-101", 10, "LAZ-01", "Lovio lakštų pjovimas S235 t5", 4, 18),
                O("2502-101", 20, "LNK-01", "Lovio lenkimas", 4, 25, ncr_at="start",
                  file_v2=(40, "; v2: lenkimo kompensacija +2 laipsniai (NCR)"),
                  pauses=[(0.15, "kokybe", "Pirmo lakšto kampas 92° – laukiama technologo", 60)],
                  ncr=NCR("lenkimas", "Lenkimo kampas 92° vietoj 90° – lovys nesusiveda su galiniu flanšu.",
                          "Lakštai perlenkti. Lenkimo programa pataisyta (v2, kompensacija +2°), "
                          "patvirtinta meistro.", 1, "technologas")),
                O("2502-102", 10, "PLZ-01", "Flanšų pjovimas t10", 8, 6),
                O("", 30, "SV-08", "Lovio suvirinimas", 2, 360),
                O("", 40, "SML-01", "Smėliavimas", 2, 60),
                O("", 50, "DAZ-02", "Miltelinis dažymas RAL 6011", 2, 90),
            ]),
            A("200", "Sraigtas", 2, "2502-200", 15, [
                O("2502-201", 10, "TEK-01", "Veleno tekinimas Ø50", 2, 240, scrap=1,
                  ncr=NCR("matmenys", "Veleno guolio kaklelis Ø49,95 mm (reikia Ø50 k6) – per mažas.",
                          "Pagamintas naujas velenas. Kaklelis matuojamas mikrometru prieš nuimant detalę.", 2, qty=1)),
                O("2502-201", 20, "MECH-01", "Raktinių griovelių frezavimas", 2, 60),
                O("2502-202", 10, "PLZ-01", "Spiralės segmentų pjovimas", 40, 3),
                O("2502-202", 20, "LNK-01", "Segmentų formavimas", 40, 6),
                O("", 30, "SV-09", "Spiralės suvirinimas ant veleno", 2, 600,
                  pauses=[(0.5, "medziaga", "Baigėsi suvirinimo vielos ritė ER70S-6", 120)]),
                O("", 40, "DAZ-01", "Dažymas RAL 6011", 2, 60),
            ]),
            A("900", "Transporterio surinkimas", 2, "2502-900", 16, [
                O("", 10, "SUR-01", "Surinkimas su pavara ir guoliais", 2, 480,
                  waits="Negauti motoreduktoriai – be pavaros surinkti ir išbandyti negalima"),
                O("", 20, "TST-01", "Bandymas tuščiąja eiga", 2, 120),
            ], requires="100,200"),
        ],
        "phases": [
            (None, "projektavimas", "vadovas", 0, 10, 120, 11),
            (None, "technologija", "technologas", 9, 14, 30, 15),
            (None, "komponentai", "pirkimai", 8, 40, 16, None),
            ("100", "gamyba", "meistras", 14, 34, None, None),
            ("200", "gamyba", "meistras", 15, 36, None, None),
            (None, "surinkimas", "meistras2", 36, 50, None, None),
            (None, "testavimas", "kokybe", 50, 55, 16, None),
        ],
        "components": [
            ("DRV-SEW-55", "Motoreduktorius 5,5 kW", "SEW KA77, i=40", 2, "UAB Pavaros", 9, 38, 40, []),
            ("BRG-UCF210", "Guolių mazgas UCF210", "SKF", 4, "UAB Guoliai", 9, 20, 36, [(19, 4)]),
            ("SEAL-400", "Veleno sandarinimas", "riebokšlis, 400 mm lovys", 4, "UAB Sandarinimas", 12, 30, 40, [(33, 4)]),
        ],
        "events": [
            ("meeting", 1, "Projekto pradžios susitikimas", ["vadovas", "technologas", "pirkimai", "meistras"],
             "1. Apimtis: 2 transporteriai\n2. Pavaros\n3. Terminas",
             "Terminas trumpas. Motoreduktorių pristatymas – iki 30 d.",
             "Užsakyti motoreduktorius iškart po projekto patvirtinimo",
             [("Užsakyti motoreduktorius", "pirkimai", 9, 1), ("Suderinti spiralės žingsnį su užsakovu", "vadovas", 8, 2)]),
            ("status", 2, "Užsakyti motoreduktorius", "vykdoma", "pirkimai"),
            ("status", 9, "Užsakyti motoreduktorius", "atlikta", "pirkimai"),
            ("status", 3, "Suderinti spiralės", "vykdoma", "vadovas"), ("status", 8, "Suderinti spiralės", "atlikta", "vadovas"),
            ("meeting", 40, "Vėluojantys motoreduktoriai", ["vadovas", "pirkimai", "meistras2"],
             "1. Motoreduktorių pristatymas\n2. Surinkimo planas",
             "Tiekėjas nepatvirtino naujos datos. Be pavarų transporterių išbandyti negalima.",
             "Ieškoti alternatyvaus tiekėjo su pristatymu per 7 d.\nSurinkimą vykdyti, pavarą montuoti paskutinę",
             [("Rasti motoreduktorių su pristatymu per 7 d.", "pirkimai", 44, 1)]),
            ("status", 40, "Rasti motoreduktorių", "vykdoma", "pirkimai"),
            ("status", 43, "Rasti motoreduktorių", "laukia", "pirkimai", "Laukiama 2 tiekėjų pasiūlymų"),
            ("comment", 46, "Rasti motoreduktorių", "pirkimai", "UAB Pavaros pažadėjo išsiųsti iš Vokietijos sandėlio"),
        ],
    },
    {
        "code": "P-24108", "name": "Hidraulinis presas HP-60", "customer": "UAB Metalo formos",
        "t0": -34, "due": 90, "prio": 2,
        "story": "Gamyba: lakšto sertifikatas neatitiko – partija pakeista; brėžinio klaida – išleista rev. B.",
        "assemblies": [
            A("100", "Preso rėmas", 1, "2508-100", 17, [
                O("2508-101", 10, "PLZ-01", "Šoninių plokščių pjovimas t40", 2, 45, scrap=2, ncr_at="start",
                  pauses=[(0.3, "gedimas", "Plazmos degiklio antgalio keitimas", 40)],
                  ncr=NCR("medziaga", "Lakšto t40 sertifikatas 3.1: S235JR vietoj S355J2. Pirmos 2 plokštės išpjautos.",
                          "Partija grąžinta tiekėjui, gautas S355J2 su 3.1 sertifikatu, plokštės išpjautos iš naujo. "
                          "Gaunant lakštus tikrinamas sertifikatas.", 3, qty=2)),
                O("2508-101", 20, "MECH-01", "Plokščių frezavimas", 2, 240,
                  ncr=NCR("brezinys", "Brėžinyje 2508-100 rev. A skylių ašių atstumas 860 mm nesutampa su "
                                      "hidrocilindro tvirtinimu (850 mm).",
                          "Išleista rev. B, frezavimo programa pataisyta, patikrinta su cilindro brėžiniu.", 2,
                          "technologas")),
                O("2508-102", 10, "PLZ-01", "Skersinių pjovimas t30", 3, 30),
                O("2508-102", 20, "MECH-01", "Skersinių frezavimas", 3, 150),
                O("", 30, "SV-10", "Rėmo suvirinimas", 1, 1800),
                O("", 40, "SML-01", "Smėliavimas", 1, 120),
                O("", 50, "DAZ-01", "Dažymas RAL 5010", 1, 180),
            ]),
            A("200", "Stalas ir slankiklis", 1, "2508-200", 18, [
                O("2508-201", 10, "PLZ-01", "Stalo plokštės pjovimas t60", 1, 60),
                O("2508-201", 20, "MECH-01", "Stalo frezavimas, T grioveliai", 1, 480),
                O("2508-202", 10, "CNC-01", "Kreipiančiųjų tekinimas", 4, 90),
                O("", 30, "SV-09", "Slankiklio suvirinimas", 1, 600),
                O("", 40, "DAZ-01", "Dažymas RAL 5010", 1, 90),
            ]),
            A("300", "Hidraulinė stotis", 1, "2508-300", 20, [
                O("", 10, "SUR-01", "Hidraulinės stoties surinkimas", 1, 900),
                O("", 20, "EL-01", "Elektros montavimas", 1, 600),
            ]),
            A("900", "Preso surinkimas", 1, "2508-900", 21, [
                O("", 10, "SUR-01", "Preso surinkimas", 1, 1200),
                O("", 20, "PRG-01", "PLC programa, slėgio derinimas", 1, 900),
                O("", 30, "TST-01", "Bandymas 60 t apkrova", 1, 480),
            ], requires="100,200,300"),
        ],
        "phases": [
            (None, "projektavimas", "vadovas", 0, 14, 240, 15),
            (None, "technologija", "technologas", 12, 17, 40, 17),
            (None, "komponentai", "pirkimai", 10, 55, 24, None),
            (None, "gamyba", "meistras", 17, 45, None, None),
            (None, "surinkimas", "meistras2", 45, 60, 120, None),
            (None, "programavimas", "vadovas", 55, 68, 60, None),
            (None, "testavimas", "kokybe", 68, 75, 24, None),
        ],
        "components": [
            ("HYD-CYL-60", "Hidrocilindras 60 t", "Ø200/140, eiga 400 mm", 1, "UAB Hidraulika", 12, 52, 50, []),
            ("HYD-PUMP", "Hidraulinis siurblys su varikliu", "11 kW, 200 bar", 1, "UAB Hidraulika", 12, 35, 45, []),
            ("PLATE-S355-40", "Lakštas S355J2 t40", "2000×1000, 3.1 sert.", 2, "UAB Metalo prekyba", 14, 18, 17,
             [(17, 2)]),
            ("SNS-PRESS", "Slėgio jutiklis", "0–250 bar, 4–20 mA", 2, "UAB Automatika", 15, 28, 55, [(27, 2)]),
        ],
        "events": [
            ("meeting", 1, "Projekto pradžios susitikimas", ["vadovas", "technologas", "pirkimai", "meistras", "kokybe"],
             "1. Preso konstrukcija\n2. Hidraulika\n3. Medžiagos",
             "Rėmas – suvirintas iš t40 lakšto. Hidrocilindro pristatymas – 6 sav.",
             "Hidrocilindrą užsakyti iškart\nLakštas – tik su 3.1 sertifikatu",
             [("Užsakyti hidrocilindrą ir siurblį", "pirkimai", 12, 1),
              ("Patikrinti rėmo stiprumo skaičiavimą", "technologas", 14, 1)]),
            ("status", 2, "Užsakyti hidrocilindrą", "vykdoma", "pirkimai"),
            ("status", 12, "Užsakyti hidrocilindrą", "atlikta", "pirkimai"),
            ("status", 5, "Patikrinti rėmo stiprumo", "vykdoma", "technologas"),
            ("status", 13, "Patikrinti rėmo stiprumo", "atlikta", "technologas"),
            ("drawing_rev", 23, "2508-100", "B", "Pataisytas cilindro tvirtinimo skylių atstumas 850 mm"),
            ("meeting", 24, "Medžiagos ir brėžinio neatitiktys", ["vadovas", "technologas", "kokybe", "meistras", "pirkimai"],
             "1. Lakšto sertifikatas\n2. Brėžinio klaida 2508-100",
             "Gautas netinkamas lakštas. Brėžinyje klaidingas skylių atstumas.",
             "Tiekėjui – pretenzija, lakštas pakeistas\nGaunant metalą tikrinti 3.1 sertifikatą\n"
             "Brėžinys – rev. B, gamyba tęsiama",
             [("Pateikti pretenziją lakšto tiekėjui", "pirkimai", 26, 2),
              ("Įvesti metalo sertifikatų patikrą gaunant", "kokybe", 30, 2)]),
            ("status", 24, "Pateikti pretenziją", "vykdoma", "pirkimai"),
            ("status", 26, "Pateikti pretenziją", "atlikta", "pirkimai"),
            ("status", 25, "Įvesti metalo sertifikatų", "vykdoma", "kokybe"),
        ],
    },
    {
        "code": "P-24126", "name": "Nerūdijančio plieno talpa su maišykle T-3000", "customer": "UAB Pieno technologijos",
        "t0": -16, "due": 70, "prio": 2,
        "story": "Pradžia: korpusas gaminamas; maišyklės maršrutas – technologo juodraštis; pjūvio oksidacija – atvira.",
        "assemblies": [
            A("100", "Talpos korpusas", 1, "2526-100", 11, [
                O("2526-101", 10, "LAZ-01", "Apvalkalo lakštų pjovimas AISI 304 t4", 3, 25,
                  ncr=NCR("pjovimas", "Pjūvio kraštuose nusidažymas (oksidacija) – pjauta su O₂ vietoj N₂.", None,
                          assignee="technologas")),
                O("2526-101", 20, "LNK-01", "Lakštų valcavimas", 3, 60),
                O("2526-102", 10, "PLZ-01", "Dugno pjovimas", 1, 40),
                O("", 30, "SV-06", "Korpuso suvirinimas (TIG)", 1, 1500),
                O("", 40, "SML-01", "Ėsdinimas ir pasyvavimas", 1, 240),
            ]),
            A("200", "Maišyklė", 1, "2526-200", 0, [
                O("2526-201", 10, "TEK-02", "Veleno tekinimas", 1, 300),
                O("2526-202", 10, "LAZ-01", "Menčių pjovimas", 4, 8),
                O("", 30, "SV-07", "Maišyklės suvirinimas", 1, 300),
                O("", 40, "SUR-01", "Balansavimas ir montavimas", 1, 240),
            ], release=False),
            A("300", "Aptarnavimo aikštelė", 1, "2526-300", 0, [], release=False),
            A("900", "Talpos surinkimas", 1, "2526-900", 0, [
                O("", 10, "SUR-01", "Talpos surinkimas", 1, 600),
                O("", 20, "EL-01", "Elektros montavimas", 1, 480),
                O("", 30, "TST-01", "Sandarumo bandymas", 1, 240),
            ], requires="100,200", release=False),
        ],
        "phases": [
            (None, "projektavimas", "vadovas", 0, 10, 160, 10),
            (None, "technologija", "technologas", 9, 18, 50, None),
            (None, "komponentai", "pirkimai", 10, 40, 16, None),
            ("100", "gamyba", "meistras", 11, 30, None, None),
            ("200", "gamyba", "meistras", 18, 32, 40, None),
            (None, "surinkimas", "meistras2", 32, 45, 60, None),
            (None, "testavimas", "kokybe", 45, 50, 16, None),
        ],
        "components": [
            ("MIX-DRV", "Maišyklės pavara 2,2 kW", "nerūdijantis korpusas, IP66", 1, "UAB Pavaros", 11, 35, 32, []),
            ("SEAL-MECH", "Mechaninis sandariklis", "EPDM, maisto pramonei", 1, "UAB Sandarinimas", 12, 26, 32, []),
            ("VALVE-DN50", "Drugelinė sklendė DN50", "AISI 316L", 2, "", None, None, 35, []),
        ],
        "events": [
            ("meeting", 1, "Projekto pradžios susitikimas", ["vadovas", "technologas", "pirkimai", "meistras"],
             "1. Talpos konstrukcija\n2. Nerūdijančio plieno apdirbimas\n3. Higienos reikalavimai",
             "Maisto pramonė: Ra ≤ 0,8 µm vidinėms paviršiams, TIG suvirinimas, pasyvavimas.",
             "Nerūdijantį pjauti tik su azotu\nMaišyklės technologija – po pavaros pasirinkimo",
             [("Parengti maišyklės maršrutą ir programas", "technologas", 18, 1),
              ("Užsakyti maišyklės pavarą ir sandariklį", "pirkimai", 12, 1)]),
            ("status", 9, "Parengti maišyklės", "vykdoma", "technologas"),
            ("status", 2, "Užsakyti maišyklės pavarą", "vykdoma", "pirkimai"),
            ("status", 11, "Užsakyti maišyklės pavarą", "atlikta", "pirkimai"),
        ],
    },
]


# ---------- variklis ----------

def _h(*parts) -> float:
    return zlib.crc32("|".join(map(str, parts)).encode()) / 2 ** 32


def _next_work(t: datetime) -> datetime:
    while True:
        if t.weekday() >= 5:
            t = (t + timedelta(days=7 - t.weekday())).replace(hour=0, minute=0, second=0)
            continue
        m = t.hour * 60 + t.minute
        if m < SHIFT[0]:
            return t.replace(hour=SHIFT[0] // 60, minute=SHIFT[0] % 60, second=0)
        if m >= SHIFT[1]:
            t = (t + timedelta(days=1)).replace(hour=0, minute=0, second=0)
            continue
        return t


def _consume(t: datetime, minutes: float) -> tuple[list, datetime]:
    """Darbo minutės pamainomis: [(pradžia, pabaiga)], pabaiga."""
    segs = []
    t = _next_work(t)
    while minutes > 0.01:
        end_shift = t.replace(hour=SHIFT[1] // 60, minute=SHIFT[1] % 60, second=0)
        use = min(minutes, (end_shift - t).total_seconds() / 60)
        e = t + timedelta(minutes=use)
        segs.append((t, e))
        minutes -= use
        t = _next_work(e) if minutes > 0.01 else e
    return segs, t


def _timeline(start: datetime, work_min: float, pauses) -> list:
    """Operacijos eiga: [('w', s, e)] ir [('p', s, e, priežastis, pastaba)]."""
    items, t, done = [], start, 0.0
    for frac, reason, note, minutes in sorted(pauses or []):
        part = work_min * frac - done
        if part > 0:
            segs, t = _consume(t, part)
            items += [("w", s, e) for s, e in segs]
            done += part
        segs, t2 = _consume(t, minutes)
        items.append(("p", segs[0][0], segs[-1][1], reason, note))
        t = t2
    segs, t = _consume(t, work_min - done)
    items += [("w", s, e) for s, e in segs]
    return items


class Sim:
    def __init__(self, con, uid, cid, today, nc_dir, files_dir):
        self.con, self.uid, self.cid, self.today = con, uid, cid, today
        self.nc_dir, self.files_dir = nc_dir, files_dir
        self.events = []                     # (laikas, eilė, funkcija)
        self.busy = {}                       # centras → [(nuo, iki)]
        self.cutoff = (today - timedelta(days=3)).replace(hour=0, minute=0, second=0)
        self.centre_kind = {r[0]: r[1] for r in con.execute("SELECT code, kind FROM work_centres")}
        self.n = 0

    def U(self, login):
        return db.row(self.con.execute("SELECT * FROM users WHERE login=?", (login,)))

    def ev(self, when: datetime, fn, order=1):
        # eilė su prioritetu: įvykis gali sukurti naujų (užsakymas → gavimai)
        if when <= self.today:
            self.n += 1
            heapq.heappush(self.events, (when, order, self.n, fn))

    def at(self, dt):
        db.set_clock(lambda: dt.isoformat(timespec="seconds"))

    def run(self):
        while self.events:
            when, _, _, fn = heapq.heappop(self.events)
            self.at(when)
            fn()

    # --- darbo centro užimtumas ---
    def place(self, centre, ready: datetime, work_min, pauses):
        t = ready
        for _ in range(200):
            items = _timeline(t, work_min, pauses)
            s, e = items[0][1], items[-1][2]
            clash = [b for b in self.busy.get(centre, []) if b[0] < e and s < b[1]]
            if not clash:
                return items
            t = max(b[1] for b in clash)
        raise RuntimeError(f"Nepavyko suplanuoti {centre}")


def run(con, uid: dict, cid: dict, today: datetime, files_dir, nc_dir) -> None:
    """Sukuria pavyzdinius projektus ir jų istoriją iki `today`."""
    for login, name, pin, centres in OPERATORS:
        uid[login] = auth.create_user(con, login, name, "operatorius", "vmgt2026", pin=pin, centres=centres)
    sim = Sim(con, uid, cid, today, nc_dir, files_dir)
    area_of = {r["code"]: r["area_code"] for r in projects.list_centres(con, active_only=False)}
    jobs = []
    for spec in PROJECTS:
        jobs += _build(sim, spec)
    _schedule(sim, jobs, area_of)
    sim.run()
    _close_phases(sim)


def _build(sim: Sim, spec) -> list:
    con, uid, U = sim.con, sim.uid, sim.U
    t0 = (sim.today + timedelta(days=spec["t0"])).replace(hour=6, minute=0, second=0)
    day = lambda d, h=8: (t0 + timedelta(days=d)).replace(hour=h, minute=0, second=0)
    dstr = lambda d: (t0 + timedelta(days=d)).date().isoformat()
    sim.at(t0 - timedelta(days=3))
    pid = projects.save_project(con, uid["admin"], {
        "code": spec["code"], "name": f"{spec['name']} (PAVYZDYS)", "customer": f"{spec['customer']} (PAVYZDYS)",
        "due_date": dstr(spec["due"]), "priority": spec["prio"], "manager_id": uid["vadovas"],
        "notes": spec["story"]})
    con.execute("UPDATE projects SET sample=1 WHERE id=?", (pid,))
    asm, jobs = {}, []
    for a in spec["assemblies"]:
        asm[a["code"]] = projects.save_assembly(con, uid["admin"], pid, {
            "code": a["code"], "name": a["name"], "qty": a["qty"], "requires": a["requires"]})
    dept = {r["code"]: r["id"] for r in db.rows(con.execute("SELECT id, code FROM departments"))}
    phase_start = {(p[0], p[1]): p[3] for p in spec["phases"]}
    for acode, kind, owner, s, e, hours, real_end in spec["phases"]:
        ph = projects.save_phase(con, uid["admin"], pid, {
            "assembly_id": asm.get(acode), "kind": kind, "owner_id": uid[owner], "plan_start": dstr(s),
            "plan_end": dstr(e), "hours": hours,
            "department_id": dept.get("SVB") if kind == "gamyba" and hours else None})
        if kind in ("projektavimas", "technologija"):
            sim.ev(day(s, 7), lambda ph=ph, o=owner: projects.set_phase_status(con, uid[o], ph, "vykdoma"))
            if real_end is not None:
                sim.ev(day(real_end, 13), lambda ph=ph, o=owner: projects.set_phase_status(con, uid[o], ph, "baigta"))
    # brėžiniai – baigus projektavimą
    design_end = next(p[6] or p[4] for p in spec["phases"] if p[1] == "projektavimas")
    for a in spec["assemblies"]:
        sim.ev(day(design_end, 12), lambda a=a: drawings.save(
            con, sim.files_dir, U("technologas"), a["drawing"], "A", f"{a['drawing']}_A.pdf",
            drawings.sample_pdf([f"PAVYZDYS  {a['drawing']}  rev. A", f"{spec['code']} {a['name']}"]), a["name"]))
    # operacijos sukuriamos iš karto (technologo juodraštis), išleidžiamos – nurodytą dieną
    for a in spec["assemblies"]:
        for o in a["ops"]:
            o["task"] = tasks.create_task(con, uid["technologas"], {
                "project_id": pid, "assembly_id": asm[a["code"]], "centre_id": sim.cid[o["centre"]], "seq": o["seq"],
                "name": o["name"], "part_no": o["part"], "qty_plan": o["qty"], "norm_min": o["norm"],
                "drawing_no": a["drawing"], "drawing_rev": "A"})
        nc_ops = [o for o in a["ops"] if o["centre"] in _NC_FILE]
        if a["release"]:
            sim.ev(day(a["start"], 7), lambda a=a, nc_ops=nc_ops: _release(sim, asm[a["code"]], nc_ops))
            for o in a["ops"]:
                # surinkimas, programavimas, testavimas prasideda ne anksčiau nei jų etapas plane
                kind = tasks.CENTRE_PHASE.get(sim.centre_kind[o["centre"]], "gamyba")
                ph_start = phase_start.get((a["code"], kind), phase_start.get((None, kind), a["start"]))
                jobs.append({"o": o, "ready": day(max(a["start"], ph_start), 8), "project": spec["code"], "pid": pid})
        else:
            # juodraštis: dalis failų jau įkelta, dalies trūksta – matosi technologo sąraše
            for o in nc_ops[:-1]:
                sim.ev(day(13, 10), lambda o=o: _file(sim, o))
    # komponentai
    for item, name, specs, qty, sup, ordered, promised, need, receipts in spec["components"]:
        def make(item=item, name=name, specs=specs, qty=qty, sup=sup, ordered=ordered, promised=promised, need=need,
                 receipts=receipts):
            c = components.save(con, uid["pirkimai"], {
                "project_id": pid, "item_no": item, "name": name, "spec": specs, "qty": qty, "unit": "vnt",
                "supplier": f"{sup} (PAVYZDYS)" if sup else "", "po_no": f"PO-{spec['code'][2:]}-{item[:3]}" if sup else "",
                "po_line": "1" if sup else "", "ordered_date": dstr(ordered) if ordered is not None else None,
                "promised_date": dstr(promised) if promised is not None else None, "need_date": dstr(need)})
            for d, q in receipts:
                when = day(d, 10)
                sim.ev(when, lambda c=c, q=q, when=when: components.receive(
                    con, uid["sandelis"], c, q, when=when.isoformat(timespec="seconds")))
        sim.ev(day(ordered if ordered is not None else 10, 9), make)
    # susitikimai, užduotys, failų ir brėžinių keitimai
    for e in spec["events"]:
        sim.ev(day(e[1], 9 if e[0] == "meeting" else 11), lambda e=e: _event(sim, pid, asm, spec, e, dstr))
    if spec.get("done_day") is not None:
        sim.ev(day(spec["done_day"], 12), lambda: projects.save_project(con, uid["vadovas"], {"status": "baigtas"}, pid))
    return jobs


_NC_FILE = {"LAZ-01": "dxf", "PLZ-01": "dxf", "LNK-01": "nc", "CNC-01": "mpf", "MECH-01": "h", "PRG-01": "scl"}


def _file(sim, o, note=""):
    ext = _NC_FILE[o["centre"]]
    name = f"{o['part'] or 'mazgas'}_{o['centre'].split('-')[0].lower()}.{ext}"
    body = (f"; PAVYZDYS {o['name']}\n; kiekis {o['qty']}, norma {o['norm']} min/vnt\n{note}\nM30\n").encode()
    if ext == "scl":
        body = f"FUNCTION_BLOCK FB_Pavyzdys // {o['name']}\nEND_FUNCTION_BLOCK\n".encode()
    ncfiles.save(sim.con, sim.nc_dir, sim.U("technologas"), o["task"], name, body, note)
    return name


def _release(sim, assembly_id, nc_ops):
    for o in nc_ops:
        _file(sim, o)
    routing.release(sim.con, sim.uid["technologas"], assembly_id)
    sim.con.execute("UPDATE tasks SET approved=1 WHERE assembly_id=?", (assembly_id,))


def _event(sim, pid, asm, spec, e, dstr):
    con, U, uid = sim.con, sim.U, sim.uid
    kind = e[0]
    if kind == "meeting":
        _, d, title, people, agenda, notes, decisions, acts = e
        m = meetings.save(con, U("vadovas"), {
            "project_id": pid, "title": title, "held_at": db.now()[:16], "location": "Pasitarimų kambarys",
            "chair_id": uid["vadovas"], "attendees": [uid[p] for p in people], "agenda": agenda, "notes": notes,
            "decisions": decisions,
            "new_actions": [{"title": t, "owner_id": uid[o], "due_date": dstr(due), "priority": pr} for t, o, due, pr in acts]})
        meetings.approve(con, U("vadovas"), m)
    elif kind in ("status", "comment"):
        prefix = e[2]
        aid = con.execute("SELECT id FROM actions WHERE project_id=? AND title LIKE ? ORDER BY id DESC LIMIT 1",
                          (pid, prefix + "%")).fetchone()
        if not aid:
            return
        if kind == "status":
            actions.set_status(con, U(e[4]), aid[0], e[3], e[5] if len(e) > 5 else "")
        else:
            actions.comment(con, U(e[3]), aid[0], e[4])
    elif kind == "drawing_rev":
        _, d, number, rev, note = e
        drawings.save(con, sim.files_dir, U("technologas"), number, rev, f"{number}_{rev}.pdf",
                      drawings.sample_pdf([f"PAVYZDYS  {number}  rev. {rev}", note]), note)


def _schedule(sim: Sim, jobs, area_of):
    con = sim.con
    by_task = {j["o"]["task"]: j for j in jobs}
    end_of = {}                             # užduotis → pabaiga (None – nepradėta iki „dabar“)

    def deps(tid):
        t = tasks._task(con, tid)
        out = [u["id"] for u in routing.upstream(con, t)]
        if routing.is_entry(con, t):
            req = con.execute("SELECT requires, project_id FROM assemblies WHERE id=?", (t["assembly_id"],)).fetchone()
            for code in [c for c in req["requires"].split(",") if c]:
                out += [r[0] for r in con.execute(
                    "SELECT t.id FROM tasks t JOIN assemblies a ON a.id=t.assembly_id WHERE a.project_id=? AND a.code=?",
                    (req["project_id"], code))]
        return out

    pending = list(jobs)
    for _ in range(len(jobs) + 5):
        if not pending:
            break
        rest = []
        for j in pending:
            ds = deps(j["o"]["task"])
            if any(d in by_task and d not in end_of for d in ds):
                rest.append(j)
                continue
            if any(end_of.get(d, 0) is None for d in ds if d in by_task):
                end_of[j["o"]["task"]] = None            # ankstesnė dar nebaigta – šita laukia
                continue
            ups = [end_of[d] for d in ds if d in by_task]
            ready = j["ready"]
            if ups:
                # detalės laukia prieš kitą operaciją 0,3–1,5 darbo dienos: transportas,
                # eilė centre, meistro sprendimai – kaip tikrame ceche
                ready = max(ready, max(ups) + timedelta(hours=8.5 * (0.3 + 1.2 * _h("gap", j["o"]["task"]))))
            if j["o"].get("waits"):
                end_of[j["o"]["task"]] = None
                continue
            end_of[j["o"]["task"]] = _plan_job(sim, j, ready, area_of)
        pending = rest


def _plan_job(sim: Sim, j, ready, area_of):
    o = j["o"]
    centre = o["centre"]
    factor = o.get("factor") or (0.85 + 0.4 * _h(j["project"], o["task"]))
    work = max(5.0, o["norm"] * (o["qty"] + o.get("scrap", 0)) * factor)
    items = sim.place(centre, ready, work, o.get("pauses"))
    start, end = items[0][1], items[-1][2]
    if centre in RESERVED and end >= sim.cutoff:
        return None                                  # šiuos centrus paskutines dienas naudoja pagrindiniai pavyzdžiai
    sim.busy.setdefault(centre, []).append((start, end))
    con, U = sim.con, sim.U
    login = CENTRE_OPERATOR.get(centre) or AREA_OPERATOR.get(area_of.get(centre), "op1")
    tid = o["task"]
    meistras = U("meistras") if area_of.get(centre) in ("MAB", "TKB", "SVB") else U("meistras2")

    def start():
        con.execute("UPDATE tasks SET queue_pos=-1 WHERE id=?", (tid,))   # meistras paleidžia šią pirmą
        t = tasks._task(con, tid)
        why = tasks.block_reason(con, t) or ""
        if "revizija" in why:
            tasks.ack_revision(con, meistras, tid)
        if "technologo failas" in (tasks.block_reason(con, tasks._task(con, tid)) or ""):
            ncfiles.ack(con, meistras, tid)
        tasks.start(con, U(login), tid)

    sim.ev(items[0][1], start, order=2)
    if o.get("ncr") and o.get("ncr_at") == "start":
        sim.ev(items[0][1] + timedelta(minutes=20), lambda: _ncr(sim, o, U(login)))
    if o.get("file_v2"):
        # technologas pataiso programą operacijos metu, meistras patvirtina naują versiją
        mins, note = o["file_v2"]
        sim.ev(items[0][1] + timedelta(minutes=mins), lambda: _file(sim, o, note))
        sim.ev(items[0][1] + timedelta(minutes=mins + 10), lambda: ncfiles.ack(con, meistras, tid))
    prev = None
    for it in items:
        if it[0] == "w":
            if prev is not None and prev[0] == "w":            # tarp pamainų
                sim.ev(prev[2], lambda: tasks.pause(con, U(login), tid, "pamaina"), order=0)
                sim.ev(it[1], lambda: tasks.resume(con, U(login), tid), order=2)
            elif prev is not None:                              # po tikros pauzės
                sim.ev(it[1], lambda: tasks.resume(con, U(login), tid), order=2)
        else:
            # pauzė prasideda ten, kur baigėsi darbas – kitaip naktį prieš ją
            # užduotis būtų „vykdoma“
            reason, note = it[3], it[4]
            sim.ev(prev[2], lambda reason=reason, note=note: tasks.pause(con, U(login), tid, reason, note), order=0)
        prev = it

    def stop():
        tasks.stop(con, U(login), tid, o["qty"], o.get("scrap", 0))
        sim.con.execute("UPDATE tasks SET queue_pos=? WHERE id=?", (10000 + tid, tid))
        if o.get("ncr") and o.get("ncr_at") != "start":
            _ncr(sim, o, U(login))

    sim.ev(end, stop, order=0)
    return end


def _ncr(sim: Sim, o, reporter):
    con, U, n = sim.con, sim.U, o["ncr"]
    nid = ncr.report(con, reporter, {"task_id": o["task"], "category": n["category"], "description": n["description"],
                                     "qty": n["qty"] or o.get("scrap", 0)})
    now = db.parse_ts(db.now())
    assign_at = now + timedelta(hours=2)
    if assign_at <= sim.today:
        sim.at(assign_at)
        ncr.assign(con, U("kokybe"), nid, sim.uid[n["assignee"]])
    if n["resolution"]:
        close_at = (now + timedelta(days=n["close_days"])).replace(hour=11, minute=30)
        if close_at <= sim.today:
            sim.at(close_at)
            ncr.close(con, U("kokybe"), nid, n["resolution"])
    sim.at(now)


def _close_phases(sim: Sim):
    """Gamybos, surinkimo, programavimo, testavimo etapas baigtas, kai baigtos
    visos jo operacijos – pažymima paskutinės operacijos pabaigos momentu."""
    con = sim.con
    for ph in db.rows(con.execute(
            "SELECT ph.* FROM phases ph JOIN projects p ON p.id=ph.project_id WHERE p.sample=1 AND p.code IN ({}) "
            "AND ph.kind IN ('gamyba','surinkimas','programavimas','testavimas') AND ph.status='vykdoma'".format(
                ",".join("?" * len(PROJECTS))), [p["code"] for p in PROJECTS])):
        kinds = {k for k, v in tasks.CENTRE_PHASE.items() if v == ph["kind"]}
        q = ("SELECT t.status, (SELECT MAX(end) FROM intervals i WHERE i.task_id=t.id) AS ended FROM tasks t "
             "JOIN work_centres c ON c.id=t.centre_id WHERE t.project_id=?")
        args = [ph["project_id"]]
        if ph["assembly_id"]:
            q += " AND t.assembly_id=?"; args.append(ph["assembly_id"])
        rows = [r for r in db.rows(con.execute(q + " AND " + (
            f"c.kind IN ({','.join('?' * len(kinds))})" if kinds else "1=1") + (
            "" if kinds else f" AND c.kind NOT IN ({','.join('?' * len(tasks.CENTRE_PHASE))})"),
            args + (list(kinds) if kinds else list(tasks.CENTRE_PHASE))))]
        if rows and all(r["status"] == "baigta" for r in rows):
            sim.at(db.parse_ts(max(r["ended"] for r in rows)))
            projects.set_phase_status(con, sim.uid["meistras"], ph["id"], "baigta")
