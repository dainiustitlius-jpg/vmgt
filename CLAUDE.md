# VMGT — konteksto santrauka

Vienetinės metalo gamybos projektų stebėsenos ir shop floor web sistema.
Gaminiai projektuojami SolidWorks (PDM), technologai paruošia failus mašinoms
(Lantek – lazeris), gamyba: pjovimas → lenkimas → suvirinimas → dažymas →
surinkimas → programavimas (PLC, robotai) → testavimas. ERP – MS Dynamics 365
F&O. Dauguma darbo centrų rankiniai, staklės integruotis negalės.

Architektūros juodraštis: https://claude.ai/artifact/9EELgdH4xQFqTFnbJmm8nt

## Darbo taisyklės

- Bendravimas, kodo komentarai, sąsaja ir dokumentacija – **lietuviškai**.
  Commit žinutės – lietuviškai, be lietuviškų raidžių (ascii).
- Komentaruose – KODĖL, ne tik KAS. Kodas rašomas kaip aplinkinis.
- Kiekvienas reikšmingas pakeitimas aprašomas šiame faile.
- Commit / push – tik vartotojui paprašius.
- Gamybos serverių ir vartotojo duomenų nekeisti; slaptažodžių nerodyti.
- Neaiškų UX prašymą pirma patikslinti (2–3 variantai), ne spėti.
- Testai gyvena saugykloje (`tests/`), ne laikiname aplanke:
  `python -m pytest`.

## Paleidimas

`python -m vmgt` (portas 8080). Nustatymai – `vmgt_config.json` darbo
kataloge (`host`, `port`, `data_dir`, `seed_sample`, `seed_demo`, `session_hours`, `nc_dir`, `nc_share`); failo
nėra – numatytosios. Duomenys – `data/` (`vmgt.db`, įkelti brėžiniai
`data/files/`), į git neįtraukiami.

**Testinė aplinka (nuo 2026-10-24) – be integracijų.** Tuščia bazė užpildoma
pavyzdžiais (`services/seed.py`): 3 projektai su žyme PAVYZDYS, 10 darbo
centrų, dalis darbų „atlikta“ praeityje, kad cechas ir analitika turėtų ką
rodyti. Visų pavyzdinių vartotojų slaptažodis `vmgt2026` (tik testams):
`admin`, `vadovas`, `planuotojas`, `technologas`, `meistras` (PIN 9999),
`meistras2` (PIN 8888), `kokybe`, `pirkimai`, `sandelis` (PIN 5555), `op1` (PIN 1111),
`op2` (2222), `op3` (3333, tik Suvirinimo baras `SVB`); demo operatoriai pagal barus:
`cnc1` (4001, TKB), `suv1` (4002, SVB), `daz1` (4003, DZB), `elek1` (4004, ATB),
`sur1` (4005, TIS).

**Penki pavyzdiniai projektai su visu technologiniu keliu** (`services/demo.py`,
nuo 2026-10-25, `seed_demo`, numatyta įjungta). Vartotojo prašymas: netikri
projektai su pilnu keliu, problemomis, sprendimais, neatitiktimis.

| Projektas | Stadija | Problemos ir sprendimai |
|---|---|---|
| P-24095 Paletizavimo celė | baigtas | robotas vėlavo → programuota simuliatoriuje; rėmo deformacija → ištiesinta; dangos storis → perdažyta; FAT saugos zona → perprogramuota |
| P-24113 Vežimėlių sistema VTS-6 | testavimas | lenkimo preso gedimas; ratų lizdai → nauji ratai, pirmos detalės patikra; pozicionavimo paklaida – **atvira** |
| P-24102 Sraigtiniai transporteriai | surinkimas laukia | lenkimo kampas → programa v2 (meistras patvirtino); velenas → perdarytas; motoreduktoriai vėluoja (sveikata raudona) |
| P-24108 Hidraulinis presas HP-60 | gamyba baigta | lakšto sertifikatas → partija pakeista; brėžinio klaida → rev. B; plazmos antgalis |
| P-24126 NP talpa T-3000 | pradžia | korpusas suvirinamas; maišyklės maršrutas – juodraštis be failo; pjūvio oksidacija – **atvira** |

Istorija kuriama **tais pačiais veiksmais** kaip ceche (išleidimas, Start /
Pauzė / Stop, neatitiktys, susitikimai, gavimai), ne įrašais į lenteles:
operacijos planuojamos pamainomis (I–V 05:00–13:30 UTC), kai centras laisvas
ir ankstesnės baigtos, su 0,3–1,5 d. laukimu tarp operacijų; surinkimas /
programavimas / testavimas – ne anksčiau nei etapas plane; tada įvykiai
vykdomi laiko tvarka (`heapq` – įvykis gali sukurti naujų), o kas po „dabar“
– neįvyksta. Todėl dabartinė būsena atsiranda savaime bet kurią dieną.
`RESERVED` (LAZ-01, LNK-01, SV-01) – paskutines 3 dienas jas naudoja
pagrindiniai pavyzdžiai. Testai (`sample_client`) – be demo; `test_demo.py` –
4 skirtingos „dabar“ datos. Rasta: įvykiai, pridėti vykdymo metu
(komponentų gavimai), su `sorted()` sąrašu neįvykdavo → `heapq`.

## Struktūra

| Kur | Kas |
|---|---|
| `vmgt/db.py` | SQLite jungtis, schema (`MIGRATIONS`, `PRAGMA user_version`), laikrodis `now()` / `set_clock` testams, įvykių žurnalas `log_event` |
| `vmgt/services/` | **Gamybos taisyklės be web** – jokio FastAPI. `RuleError` → 409, `NotFound` → 404 |
| `services/auth.py` | Vartotojai, rolės (`ROLES`), teisės (`PERMS`), PBKDF2, sesijos (bazėje – žetono SHA-256), PIN terminalui, centrų apribojimas `can_centre` |
| `services/projects.py` | Krepšelis, mazgai (`requires` – nuo kurių mazgų priklauso), etapai (`PHASE_KINDS`), gamybos barai, darbo centrai |
| `services/tasks.py` | Užduotys, eilės, terminalo veiksmai, **visos pradėjimo taisyklės – `block_reason`** |
| `services/routing.py` | Technologinis srautas: detalių atšakos → mazgas, kur keliauti toliau, išleidimas į gamybą, perdavimai, atsekamumas, technologo darbų sąrašas, maršruto kopijavimas |
| `services/ncfiles.py` | Technologo failai prie operacijų (DXF, NC, robotų, PLC): katalogai, versijos, meistro patvirtinimas |
| `services/ncr.py` | Neatitiktys: atvira → priskirta → uzdaryta |
| `services/quality.py` | Kokybė (EN 1090 / ISO 3834): patikros maršrute, lydiniai ir sertifikatai, WPS ir kvalifikacijos, NCR 8D, dosjė |
| `services/drawings.py` | PDF brėžiniai su revizija (vėliau – iš PDM) |
| `services/importer.py` | Maršrutų CSV importas (vėliau – D365 / PDM) |
| `services/components.py` | Komponentų pirkimai: eilutės, gavimai, CSV importas iš ERP eksporto, tiekėjų patikimumas |
| `services/actions.py` | Projekto komandos užduotys: statusai, leistini perėjimai, istorija |
| `services/meetings.py` | Susitikimų protokolai (MoM): veiksmai → užduotys, patvirtinimas |
| `services/health.py` | Projekto sveikata realiu laiku: 4 sritys, lygiai, priežastys |
| `services/workcal.py` | Darbo kalendorius: pamainų šablonai, LT šventės, išimtys gamykla → baras → centras, darbo laiko skaičiavimas (UTC ↔ vietinis) |
| `services/forecast.py` | Operacijų prognozė: pradžia ir pabaiga pagal centrų eiles, normas, srautą ir kalendorių |
| `services/capacity.py` | Resursų apkrova: departamentų poreikis prieš pajėgumą savaitėmis, trūkumai, krepšelio projektų tilpimas |
| `services/planner.py` | Planuotojo Gantt pagal departamentus, pakeitimų poveikis (SAVEPOINT + apkrovos palyginimas), įrašymas |
| `services/signals.py` | Pokyčių signalai ir pranešimai: planuotojo pakeitimai, vėlavimai ceche, komponentai, nauji projektai |
| `services/analytics.py` | Cecho būsena (`floor`) ir efektyvumo ataskaita (`report`) |
| `services/layout.py` | Cecho planas: barų ir centrų išdėstymas, būsenos, įspėjimai, detalių judėjimas, projekto kelias |
| `services/seed.py`, `demo.py` | Pavyzdiniai duomenys; `demo` – 5 projektai su visa istorija |
| `vmgt/web/app.py` | FastAPI: tik teisės ir HTTP → `services` |
| `vmgt/web/static/` | `index.html`, `app.js` (hash maršrutai), `app.css` – be surinkimo įrankio |
| `pavyzdziai/marsrutai.csv`, `komponentai.csv` | Importo pavyzdžiai |

## Duomenų modelis

Projektas → mazgai → (etapai mazgui arba visam projektui) → užduotys.
Užduotis = viena mazgo maršruto operacija viename darbo centre (`seq` – vieta
maršrute, `queue_pos` – vieta centro eilėje, `approved` – matoma terminale).
Vykdymas: `intervals` (darbas) ir `pauses` (su priežastimi); kiekiai –
`qty_good` / `qty_scrap` ant užduoties. `events` – visų pakeitimų žurnalas.

## Terminalo taisyklės (`tasks.block_reason`)

Pradėti galima, jei:
0. mazgo maršrutas išleistas į gamybą (`assemblies.released_at`);
1. užduotis patvirtinta planuotojo (`approved`);
2. centre niekas nevyksta ir nėra pristabdytos užduoties;
3. griežtos eilės centre (`strict_order`, numatyta) – tai pirma patvirtinta;
4. ankstesnė **srauto** operacija baigta arba perdavė bent dalį (`qty_good > 0`)
   – dalinis perdavimas vienetinėje gamyboje kasdienis; pirmajai mazgo
   operacijai – kiekvienos detalės atšakos paskutinė („Laukiama detalių: …“);
5. įėjimo operacija (pirmoji mazgo, o jei jų nėra – atšakų pirmosios) – visi
   `requires` mazgai baigti;
6. brėžinio revizija nepasikeitė; pasikeitus – meistras patvirtina
   (`ack_revision`, teisė `ack_rev`);
7. ankstesnės operacijos detalės nesulaikytos kokybės kontrolei, o suvirinimui
   su WPS – prisijungęs suvirintojas turi galiojančią kvalifikaciją (žr. „Kokybė“).

Pauzė – tik su priežastimi (`PAUSE_REASONS`), „Kita“ – su pastaba. Stop
įrašo kiekį: gera + brokas ≥ planas → baigta, kitaip lieka eilėje savo
vietoje (dalinis). Brokas > 0 – terminalas siūlo neatitikties įrašą.
Pirmas pradėtas darbas pažymi atitinkamą projekto etapą „vykdoma“
(`CENTRE_PHASE`: surinkimas / elektra → surinkimas, testavimas → testavimas,
kiti → gamyba) ir projektą perkelia iš krepšelio į vykdomus.

**Laikmatis.** Terminalas ir cechas gauna `work_s` – tik UŽDARYTŲ intervalų
sumą, o atvirą naršyklė prideda pati kas sekundę. Iki 2026-10-24 terminalas
gaudavo sumą su atviru intervalu ir jį pridėdavo dar kartą (8:02 vietoj
6:00). `test_terminalo_laikas_be_atviro_intervalo`.

## Technologinis srautas ir detalių atsekamumas (nuo 2026-10-25)

Vartotojo prašymas: ceche kiekviename centre patvirtinus operaciją turi matytis,
kur detalė keliauja toliau; visą srautą technologas nurodo paleisdamas į
gamybą. Sprendimai (2026-10-25): **detalės susilieja į mazgą**, **maršruto
lapas su QR**, perdavimas **automatiškai baigus operaciją** (vienas veiksmas).

| | |
|---|---|
| srautas | operacijos `part_no` – detalės atšaka (pvz. lazeris → lenkimas), tuščias – mazgo operacija, kurioje atšakos susilieja (suvirinimas → dažymas). Atšakos eina lygiagrečiai. Baigtas mazgas → mazgai, kurie jo laukia (`requires`), kitaip – „į sandėlį / išsiuntimui“. Tas pats CSV stulpelis `detale` – naujo formato nereikia |
| išleidimas | technologas (teisė `release`) lange „Srautas ir atsekamumas“ (`#/r/<mazgo id>`) spaudžia „Išleisti į gamybą“: `routing.check` – klaidos draudžia (nėra operacijų, mazgo operacija prieš detalių, nėra laukiamo mazgo), įspėjimai – ne (be normos, be brėžinio, atšakos nesusilieja). Iki tol planuotojas užduočių netvirtina (`approve_queue` jų nepaima), terminalas nepradeda |
| užraktas | išleistame maršrute negalima pridėti, šalinti, keisti centro, sekos, detalės, kiekio (pavadinimą, normą, brėžinį – galima); CSV importas į išleistą mazgą – klaida. „Keisti maršrutą“ (`unrelease`) – tik su priežastimi; pradėti darbai tęsiami, nepradėti užrakinami iki naujo išleidimo. Abu veiksmai – `events` |
| perdavimas | Stop su gerais vienetais → `transfers` (iš, į, kiek, kas, kada) ir terminale didelis langas „PERDUOKITE N VNT. → SV-02 …, čia susilieja 2 detalės“ |
| terminale | prie kiekvienos užduoties eilutė „Detalė … · iš ← LNK-01 ✓ · atkeliavo 2 vnt. · toliau → SV-02“. Lauke „Skenuokite maršruto lapą“ USB skaitytuvas įveda QR nuorodą + Enter: randama ir paryškinama šio centro užduotis, o jei detalė čia neateina / dar ne eilėje / jau apdirbta – parodoma, kur ji dabar |
| atsekamumas | `routing.trace`: atšakos ir mazgas su būsenomis, „📍 kur dabar“ (apdirbama, laukia N vnt., liko N vnt., detalės atkeliavo), kliūtis, perdavimų istorija; atsinaujina kas 20 s. Operatorius (be teisės `view`) jį mato – QR nuskenuoja ir telefonu |
| maršruto lapai | `#/r/<id>/lapai` – po lapą kiekvienai detalei ir mazgui: projektas, mazgas, brėžinys, operacijos su vieta parašui, „Baigus →“, QR (`/api/qr`, piešia serveris – `segno`, nes cecho kompiuteriai gali būti be interneto). Neišleistas – „JUODRAŠTIS“ |
| atvykę vienetai | `routing.arrived` skaičiuojamas tik toje pačioje atšakoje – 4 plokštės ≠ 1 rėmas, sumuoti negalima |

Migracija 7: `assemblies.released_at/released_by`, `transfers`; esamos bazės
mazgai su operacijomis laikomi išleistais. Pavyzdžiuose P-24117 200 – dvi
detalės (1023-201, 1023-210) susilieja SV-02; P-24121 200 – technologo
juodraštis išleidimui išbandyti. `requirements.txt` + `segno` (`paleisti.bat`
įdiegia pats). `test_srautas.py`.

## Technologo darbo aplinka ir failai (nuo 2026-10-25)

Vartotojo prašymas: lazeriui, plazmai, CNC reikia DXF ir kitų failų, kuriuos
technologas parengia ir priskiria operacijai; failai – kataloguose; technologo
aplinka visam technologiniam keliui. Sprendimai: **VMGT tvarko katalogus pati**,
**darbų sąrašas + maršruto redaktorius**, pakeistas po išleidimo failas –
**kaip brėžinio revizija (meistras patvirtina)**.

| | |
|---|---|
| katalogai | `ncfiles.save`: `<nc_dir>/<projektas>/<mazgas>/<centras>/<failas>_v<N>.<plėtinys>`. `vmgt_config.json`: `nc_dir` (tuščia – `data/nc`; gali būti tinklo diskas), `nc_share` – kaip katalogą mato cecho kompiuteriai (rodoma terminale ir redaktoriuje). Pavadinimai valomi (`_safe`) – kelias iš katalogo neišeina |
| versijos | tas pats originalus pavadinimas → nauja versija, senoji lieka diske ir istorijoje (`task_files.current=0`); toks pat turinys (sha256) – klaida. Pašalinti – tik neišleistame maršrute, diske lieka |
| tipai | leidžiamų plėtinių sąrašas `ncfiles.KINDS`: CAD (dxf, dwg, step…), NC (nc, mpf, h, tap…), robotų (mod, src, ls, jbi…), PLC (zap*, ap*, l5x, scl…), dokumentai. Nežinomas (.exe) – atmetamas; naujas valdiklio formatas – įrašyti ten. Iki 200 MB |
| staklės | `work_centres.needs_files` (migracija 9, administravime „Reikia failo“): be failo maršruto išleisti negalima (`routing.check` – klaida). Pavyzdžiuose: LAZ-01, PLZ-01, LNK-01, CNC-01, MECH-01, PRG-01 |
| po išleidimo | įkeltas failas – `needs_ack=1`: nepradėta operacija užrakinama (`block_reason`: „Atnaujintas technologo failas … Reikia meistro patvirtinimo“), terminale mygtukas „Patvirtinti failą“ (teisė `ack_rev`); vykdomai – įspėjimas |
| technologo sąrašas | `#/technologija` (teisė `tasks`, `routing.worklist`): vykdomų ir krepšelio projektų mazgai – nėra maršruto / juodraštis / išleista, be failo, be normos, laukia meistro, technologijos etapo atsakingas ir terminas; „Mano“ – pagal technologijos etapo atsakingąjį |
| redaktorius | `#/technologija/<mazgo id>`: lentelės pagal detales ir mazgą, keitimas vietoje, failai (įkelti, nutempti ant eilutės, versijų istorija), operacijos pridėjimas, **maršruto kopijavimas iš kito mazgo** (`routing.copy_route`: kiekiai perskaičiuojami pagal mazgų kiekį, failai – kaip v1), srauto peržiūra, išleidimas / grąžinimas |
| terminale | failų žymos su atsisiuntimu ir katalogo kelias; maršruto lapuose – stulpelis „Failai“ |

`test_failai.py`. Pavyzdžiuose P-24121 200 lenkimui failo sąmoningai nėra
(išleidimas rodo klaidą), P-24121 100 plazmos programa pakeista po išleidimo
(PLZ-01 laukia meistro).

## Kokybė pagal EN 1090 / ISO 3834 (nuo 2026-10-26)

Vartotojo sprendimai: diegiamos **visos keturios dalys** (patikros maršrute,
medžiagų sertifikatai ir lydiniai, suvirintojų kvalifikacijos / WPS, dosjė ir
NCR 8D); taisyklės **griežtos**; patikrą atlieka **tas, kurį nurodė
technologas** (operatorius – savikontrolė terminale, arba kokybės
inžinierius – kokybės eilė). `services/quality.py`, migracija 12, teisė
`quality` (kokybe, admin). Langas „Kokybė“ (`#/kokybe/<kontrole|medziagos|
suvirinimas|sablonai|dosje>`), dosjė – `#/dosje/<projekto id>`.

| | |
|---|---|
| vykdymo klasė | `projects.exc_class` (EN 1090-2: EXC1–EXC4), projekto „Planas“ kortelėje. Nuo **EXC2** (`TRACE_FROM`): pjovimo operacijai privalomas lydinys, suvirinimo – WPS (išleidimo klaida `quality.route_check`, be kokybės inžinieriaus patikros – įspėjimas) |
| patikros | šablonai `check_templates` (OK/NOK arba matavimas su tolerancija, atlieka operator / qc); technologas redaktoriuje – stulpelis „Kokybė“: „+ Patikra“, WPS suvirinimui. Kiekvienas rezultatas – `check_results` (pakartotinis neištrina ankstesnio). Matavimui OK skaičiuojamas iš tolerancijos; kablelis priimamas (įvedimo laukai – tekstiniai su `inputmode=decimal`, nes `type=number` kablelio nepriima – rasta Playwright) |
| griežtumas | Stop su gerais: operatoriaus patikros ir (EXC2+ pjovimui) lydinys – privalomi (`check_stop`). Liko qc patikra – kiekis įrašomas, bet detalės **sulaikomos**: perdavimas – tik užbaigus (`release_transfers`, tik skirtumas – nedubliuoja), kita operacija užrakinta („Laukiama kokybės kontrolės“, `block_reason`). NOK → automatinė neatitiktis (`ncr.check_id`), patikra atvira iki OK ar išimties. Išimtis (`waive`) – meistras (`ack_rev`) ar kokybė, su priežastimi. Išleistame maršrute patikros nepašalinamos |
| medžiagos | `material_lots`: lydinys, medžiaga, gaminys, tiekėjas, sertifikatas EN 10204 (2.2/3.1/3.2, PDF `files/sertifikatai/`), būsena tinkama / blokuota (su priežastimi – blokuoto naudoti negalima). Registruoja sandėlis (`receive`) ar kokybė. Terminale „Nurodyti lydinį“ – paieška → `task_materials` |
| suvirinimas | `wps` (procesas ISO 4063, grupė ISO/TR 15608), `qualifications` (ISO 9606-1, galioja iki, PDF). Start: suvirinimo operacijai su WPS – prisijungęs turi galiojančią kvalifikaciją tam procesui ir grupei (`welder_lock`, terminale – užraktas tam, kas prisijungęs). Išimties nėra – tai teisinis reikalavimas |
| NCR 8D | `ncr` + D3 laikini veiksmai, D4 šakninė priežastis, D5–6 korekciniai, D7 prevenciniai, sprendimas dėl gaminio (`DISPOSITIONS`), nuotraukos `ncr_files`. Uždarant per API – šakninė priežastis ir sprendimas dėl gaminio privalomi |
| dosjė | `quality.dossier`: medžiagų atsekamumas (detalė → lydinys → sertifikatas), suvirinimo žurnalas (kas, kada, WPS, kvalifikacija), patikrų protokolas, neatitiktys 8D, „Ko trūksta“; spausdinimui / PDF; `dossier_zip` – sertifikatai, kvalifikacijos, WPS, NCR nuotraukos + `turinys.csv` |

Pavyzdžiai (`seed._quality`, kuriami PO istorijos, praeities lydiniai ir WPS –
atgaline data kaip iš žurnalų): 7 šablonai, 3 WPS, kvalifikacijos (`suv1`
galioja, 141/8.1 baigiasi po 20 d.; `op3` – pasibaigusi), 7 lydiniai
(H-60014 blokuotas – P-24108 istorija), klasės (P-24108 EXC3, P-24113 EXC1,
kiti EXC2), patikros laukiančioms operacijoms; P-24108 dažytas rėmas
**sulaikytas** kokybės eilėje (dangos storis). Demo NCR – su 8D.
`test_kokybe.py`.

## Darbo kalendorius (nuo 2026-10-26)

Vartotojo sprendimai: lygiai **gamykla → baras → centras**; žymima **pamainos,
šventės ir nedarbo dienos, remontai, papildomas darbas**; veikia **apkrovą,
operacijų prognozę, cechą ir terminalą, planuotojo Gantt**; redaguojama
**metiniame kalendoriuje**. Langas – „Planas“ skirtukas „Darbo kalendorius“
(`#/planas/kalendorius[/area|centre/<id>]`), keisti – teisė `calendar`
(admin, vadovas, planuotojas, meistras). Migracija 13.

| | |
|---|---|
| šablonai | `shift_patterns` (savaitė: dienai „07:00-11:00, 11:30-15:30“, tarpas – pertrauka). Gamyklos – `settings.factory_pattern`, baro / centro – `shift_pattern_id` (NULL – paveldėti). Numatyti: „1 pamaina“ (8 val.), „2 pamainos“ (16 val.). Laikas – **vietinis**: pamaina nesikeičia keičiantis vasaros laikui; poslinkis – ES taisyklė (`utc_offset`), ne `zoneinfo` (Windows be `tzdata`) |
| diena | šablonas → LT valstybinė šventė (`holidays`, Velykos skaičiuojamos) → išimtys gamyklos, baro, centro eile (`calendar_days`): nedarbo – nieko, remontas – atima (be laiko – visą dieną, pastaba privaloma), papildomas – prideda, kitas – pakeičia. Tad šventę galima paversti darbo diena, o centro remontas kitų baro centrų nepaliečia |
| laikas | `Calendar.add_work` – kada bus atlikta N sek. darbo tik darbo langais; `status` – ar dabar darbo laikas, kodėl ne, kada prasidės |
| prognozė | `forecast.forecast`: centro eilės tvarka, vykdomos likutis (norma × planas − dirbta, bet ≥ 15 % likusių vnt.), laukia ankstesnės srauto operacijos (jei ji nieko neperdavė) ir `requires` mazgų – tos pačios taisyklės kaip `block_reason`; kartojama, kol nebesikeičia (prieštaraujanti eilė – „loop“). Vėluoja – pabaiga po etapo (mazgo ar projekto) plano pabaigos. Neišleista / nepatvirtinta – „jei paleista dabar“. Rodoma centro eilėje ir projekto „Gamyba“. Supaprastinimai: eilė laikoma griežta, KK laukimas ir derinimas neprognozuojami |
| apkrova | savaitės pajėgumas × `week_factor` = kalendoriaus valandos / šablono valandos (barui – jo centrų suma: 1 iš 10 postų remontas – −10 %; biurui – gamyklos); etapų valandos paskirstomos tik kalendoriaus darbo dienomis; langelyje – kas tą savaitę neįprasta |
| Gantt | `planner._off_days`: fone nedarbo (pilka), šventė / uždaryta (raudona), papildomas (žalia), remontas (ochra, ir centrų) |
| ceche | `analytics.floor` ir planas – `calendar`: ne darbo metu laisvas centras blankus „⏾ šventė / remontas / po pamainos“; terminale juosta ir **Start / Tęsti paklausia** (įspėjimas, ne draudimas – viršvalandžius sprendžia meistras) |
| signalai | `planner.calendar_change`: prieš ir po – apkrova (`_compare`) ir prognozė (operacija baigsis ≥ 1 val. vėliau; raudona – nebespės iki etapo pabaigos); `plan_changes` rūšis `calendar`, pranešimai paveiktiems, langas „Kalendorius pakeistas“ |

Pavyzdžiai (`seed._calendar`): MAB – 2 pamainos, LAZ-01 servisas artimiausią
trečiadienį, DAZ-02 krosnies valymas 07–11, SVB šeštadienio viršvalandžiai,
gamykla uždaryta 12-28…12-31. `test_kalendorius.py`.

## Planavimas ir pokyčių signalai (nuo 2026-10-26)

Vartotojo prašymas: planuotojo lange matyti visų departamentų užduotis, o
kiekvienas pakeitimas turi signalizuoti apie poveikį kitiems projektams.
Sprendimai: **Gantt pagal departamentus**; **poveikio peržiūra prieš
įrašant + pranešimai**; signalą kelia **planuotojo pakeitimai, vėlavimai
ceche, komponentų vėlavimai, nauji projektai iš krepšelio**.

| | |
|---|---|
| langas | `#/planas` – „Departamentų planas“ (Gantt), `#/planas/eiles` ir `#/planas/<centras>` – centrų eilės (kaip anksčiau). Eilutės – departamentai (`capacity`), juostos – etapai (gamybos / surinkimo – kiekviename bare, kuriame yra jų operacijų, `planner._phase_departments`), viršuje – savaitės apkrova. Spalva – projektas; brūkšniuota – krepšelis; raudonas kraštas – vėluoja. Projektų juosta: paryškinimas, prioritetas, „Patvirtinti…“ krepšeliui |
| keitimas | tempti juostą (perkelti) ar dešinį kraštą (pabaiga), arba spustelėti ir įvesti datas → `POST /api/planner/impact` → langas „Pakeitimo poveikis“ (paveikti projektai su priežastimis, paties projekto įspėjimai, kas atsilaisvina, pastaba) → `apply`. Teisė `plan` arba `projects` |
| poveikis | `planner.impact`: pakeitimas pritaikomas SAVEPOINT viduje, `capacity.report` prieš / po, atšaukiama – peržiūra lygiai tokia, kokia bus įrašius. Paveiktas = KITAS projektas, kurio darbas yra departamento savaitėje, kuri persikrovė (> 100 % – raudona) ar perlipo 85 % (geltona); eilėje – kurio darbai pasislinko (vietos ir ~valandos); prioriteto pakėlimas – kas dalijasi departamentais. Patvirtinimas iš krepšelio – lyginama tik su vykdomais (`committed`) |
| visi keliai | projekto kortelės etapo datos, prioritetas, statusas „vykdomas“ ir centro eilės perkėlimas (`/api/tasks/{id}/move`) eina per `planner.apply` – signalas atsiranda, kad ir kur keista |
| ceche | `signals.on_stop` – baigta operacija > 125 % normos ir ≥ 30 min. daugiau; `on_resume` – neplanuota pauzė ≥ 60 min. Paveikti – kitų projektų patvirtinti darbai TAME centre (sukurti iki to momento) |
| komponentai | `components.save`: tiekėjas nukėlė pažadėtą datą (ir importas – tas pats kelias); `signals.scan` (skaitant pranešimus) – pažadėta data praėjo, negauta. Raudona, jei data vėlesnė už surinkimo etapo pradžią |
| krepšelis | projektas tapo vykdomu (patvirtintas, pradėtas etapas ar darbas) – `signals.project_activated` |
| įrašai | `plan_changes` (migracija 10; bendras žurnalas „Pokyčių signalai“, `key` – tas pats signalas tik kartą) ir `notifications` (vienam žmogui; gavėjai – projekto vadovas, neužbaigtų etapų atsakingieji, planuotojai; ne pats keitėjas). Varpelis viršuje (kas minutę), langas su priežastimis ir nuoroda |

`test_planavimas.py`. Pavyzdžiuose signalai susidaro iš demo istorijos
(vėlavimai ceche, nauji projektai, vėluojantys komponentai).

## Cecho planas (nuo 2026-10-26)

Vartotojo prašymas: preliminarus interaktyvus cecho planas su išdėstytais
barais ir centrais, matomi centrų statusai. Sprendimai: **redaguojamas
nutempiant** (preliminarų sudeda sistema); plane – **dabartinis darbas ir
laikmatis, detalių judėjimas, projekto filtras, įspėjimai**; vieta – lange
**„Cechas“ kaip skirtukas** (`#/cechas/planas`, numatytas; `#/cechas/korteles`
– ankstesnės kortelės; paskutinis pasirinkimas – `localStorage pf.floorView`).

| | |
|---|---|
| išdėstymas | `layout.auto_layout`: barai iš kairės į dešinę `areas.sort` (technologinio srauto) tvarka, eilutėmis iki 110 m; centrai – tinkleliu baro viduje (8×6 m). Vieta – `areas.layout`, `work_centres.layout` (migracija 11, JSON {x,y,w,h}, sąlyginiai metrai; centro – baro viduje, tad perkeliant barą keliauja kartu). NULL – automatinė, todėl naujas centras plane atsiranda pats |
| redagavimas | „Redaguoti išdėstymą“ (teisė `admin`): tempti barą / centrą, kampo kvadratėliu – dydis (žingsnis 0,5 m), centras lieka baro viduje; „Išsaugoti“ / „Atšaukti“ / „Automatinis“ (`PUT /api/floor/layout`, `reset`). Tempiant keičiamas tik tempiamas SVG elementas – perpiešus visą SVG naršyklė prarasdavo tempimą po pirmo judesio (rasta Playwright) |
| būsenos | tos pačios kaip kortelėse (`analytics.floor`): dirba (žalia, mirksi lemputė), pristabdyta, gali pradėti, laukia (užrakinta, raudonas brūkšninis), laisvas; ant centro – projektas · mazgas, operacija, laikmatis (kaip terminale: uždarytų intervalų suma + naršyklė prideda atvirą) arba eilės ilgis |
| įspėjimai | `layout._alerts`: neplanuota pauzė ≥ 60 min. (raudona), vykdoma > 125 % normos, atvira neatitiktis, failas laukia meistro – mirksintis „!“, sąrašas centro lange |
| detalės | ⧗N – atkeliavusios ir laukiančios detalės (`routing.arrived`, susiliejusios – 1); rodyklės – šiandien perduota (`transfers`), ant rodyklės – vnt. |
| projektas | pasirinkus – kiti centrai blankūs, projekto centrai oranžiniu kraštu su ✓ atlikta ▶ vyksta ○ laukia, rodyklės – maršruto kelias (ištisinė – praeita, brūkšninė – dar ne) |
| kita | spustelėjus centrą – langas su darbu, įspėjimais, nuorodomis į terminalą ir eilę; „Visas ekranas“ – sieniniam ekranui; atsinaujina kas 10 s; telefone – slenkama kortelėje |

Klasės: plano rodyklės – `.fmove` (`.flow` jau terminalo srauto eilutė).
`test_cecho_planas.py`.

## Resursų apkrova (nuo 2026-10-25)

Vartotojo tikslas: matyti, kiek projektų vykdoma, kiek dar galima prisiimti ir
kur trūksta žmonių. Sprendimai (2026-10-25): departamentai – **biuro skyriai
ir gamybos barai**; poreikis – **etapų planuojamos valandos + cecho normos**;
žingsnis – **savaitė**. Langas „Apkrova“ (`#/apkrova`).

| | |
|---|---|
| departamentai | `departments` (migracija 6): biuro skyrius – `phase_kinds` (kurių etapų darbas: projektavimas, technologija, komponentai, programavimas, testavimas); gamybos baras – `area_id` |
| pajėgumas | žmonės × val. per savaitę × prieinamumas (numatyta 85 % – atostogos, ligos, kiti darbai) × savaitės kalendoriaus santykis (žr. „Darbo kalendorius“); keičiama lange (teisė `projects`) |
| biuro poreikis | etapo `hours` tolygiai per etapo darbo dienas (`spread`); etapas gali turėti `department_id`, kitaip – pagal `phase_kinds` |
| gamybos poreikis | likusios cecho operacijų normos (norma × likęs kiekis) per mazgo gamybos / surinkimo etapo likusias dienas; etapas praėjęs ar jo nėra – likutis į šią savaitę. Kol etapo apimtyje NĖRA operacijų – etapo `hours` su nurodytu baru (įvertis krepšelio projektui); atsiradus operacijoms įvertis nebeskaičiuojamas (dvigubai negali) |
| prielaidos | nepradėtas etapas, kurio pradžia praėjo, perkeliamas į šiandien tiek pat DARBO dienų; vykdomo etapo praeitis laikoma atlikta; vėluojančio vykdomo – tempas tęsiamas savaitę (kad vėlavimas nedingtų); savaitgalį grafikas prasideda nuo kitos savaitės |
| krepšelis | krepšelio projektų valandos rodomos atskirai (jungiklis); trūkumas žymimas „tik priėmus krepšelį“, jei vykdomi patys telpa |
| ar telpa | krepšelio projektas tikrinamas **kiekvieną savaitę**: vykdomi + jis ≤ pajėgumas; sumomis per laikotarpį lyginti negalima (700 val. „tilptų“ į 12 sav., nors suplanuota per 2) |
| duomenų spragos | etapai be valandų, be datų, gamybos etapas be baro – sąrašas „Ko trūksta tiksliam skaičiavimui“ su nuoroda į projekto planą |

Projekto „Planas“ kortelėje – stulpeliai „Val.“ ir „Departamentas“.
`test_apkrova.py`. Rasta testu: perkeliant nepradėtą etapą kalendorinėmis
dienomis savaitgalis „suvalgydavo“ valandas (50 → 30).

## Projekto valdymas (nuo 2026-10-25)

Vartotojo sprendimai (2026-10-25): užduotys – **projekto komandos** (biuro)
darbai, ne cecho operacijos; protokolo **veiksmai tampa užduotimis**;
sveikata – visos 4 sritys. Projekto puslapis – kortelės `#/p/<id>/<kortelė>`:
sveikata (numatyta), planas, užduotys, susitikimai, gamyba, komponentai,
neatitiktys. Meniu „Užduotys“ (`#/uzduotys`) – mano / visų projektų Kanban.

**Užduotys (`actions`, migracija 5).** Statusai: nauja → vykdoma → laukia →
peržiūra → atlikta / atšaukta; tik `actions.TRANSITIONS` perėjimai (pvz.
nauja → atlikta neleidžiama; atlikta → vykdoma – atidaryti iš naujo).
Laukiant ir atšaukiant **priežastis būtina** (`wait_reason`). Kiekvienas
pakeitimas, redagavimas ir komentaras – `action_log` (istorija lange, laukimo
trukmė `wait_seconds`). Keisti visas – teisė `actions`; savo užduoties
statusą ir komentarus – pats atsakingasis, kad ir kokia rolė (operatorius
mato `?owner=me`). Vėluoja – terminas praėjo, o būsena atvira.

**Mano darbai – asmeninis savaitės planas (`#/mano`, nuo 2026-10-25).**
Vartotojo sprendimai: lange – **asmeninės + man priskirtos projektų**
užduotys; planas – **savaitė dienomis**; asmeninės – **matomos tik man**.
Asmeninė užduotis – `actions` be projekto (migracija 8 perkūrė lentelę:
`project_id` gali būti NULL, nauji `plan_date`, `estimate_h`). Kuria kiekvienas
(ir operatorius), savininkas – visada kūrėjas; kitiems ji neegzistuoja (404,
ne 403 – net vadovui). Kolegai priskirti – tik susiejus su projektu (tada ją
mato komanda); atgal asmenine nepaverčiama. Asmeninę galima iškart pažymėti
atlikta (projekto – tik per „vykdoma“). Dieną ir įvertį keičia tik
atsakingasis; pasikeitus atsakingajam planas išvalomas. Stulpeliai:
Neplanuota, Pr–Pn (savaitgalis – tik jei jame kas yra), Vėliau; dienos
valandos prieš `DAY_HOURS` = 8. Neatlikta praėjusios dienos užduotis rodoma
pirmą darbo dieną su „↻ perkelta iš …“ – `plan_date` neperrašomas, tad matyti,
nuo kada stumiama. Savaitgalį planas – nuo pirmadienio. Į praeitį planuoti
negalima. `actions.week`, `test_mano_darbai.py`.

**Protokolai (`meetings`).** Dalyviai (vartotojai + svečiai tekstu),
darbotvarkė, aptarta, sprendimai (po vieną eilutėje), veiksmai. Kiekvienas
veiksmas su pavadinimu – iškart `actions` su `meeting_id`. Kitame susitikime
rodomi **ankstesnių susitikimų neuždaryti veiksmai** (`review`). Patvirtintas
protokolas užrakinamas (tekstas – susitarimo įrašas), iš jo kilusios užduotys
gyvena toliau. Tekstas el. laiškui – `as_text`, „Kopijuoti“, spausdinimas
(`@media print`). Vesti / tvirtinti – teisė `meetings` (vadovas, admin).

**Sveikata (`health.project_health`).** Sritys ir svoriai: terminai ir etapai
35 %, užduotys ir gamyba 25 %, komponentai 25 %, kokybė 15 %. Kiekviena –
žalia / geltona / raudona, išvada ir **priežasčių sąrašas**. Bendras lygis –
**blogiausia sritis** (vidurkis paslėptų vieną kritišką), balas – svertinis
vidurkis. Ribos – `health.LIMITS`.

| Sritis | Kas tikrinama |
|---|---|
| Terminai | vėluojantys / laiku nepradėti etapai; prognozė = paskutinio neužbaigto etapo pabaiga + didžiausias dabartinis atsilikimas (be etapų priklausomybių – sąmoningai paprasta ir paaiškinama); prognozė > terminas – raudona |
| Užduotys ir gamyba | vėluojančios ir laukiančios užduotys; cecho operacijų atlikta dalis (pagal normuotas valandas) prieš laiko eigą gamybos / surinkimo / testavimo etapų lange; faktas / norma |
| Komponentai | reikėjo – negauta, tiekėjas vėluoja, rizika, neužsakyta (`components.decorate`) |
| Kokybė | atviros neatitiktys ir jų amžius, broko dalis |

Portfelyje (krepšelis) – sveikatos ženklas ir 4 srities taškai; projekto
sveikatos kortelė atsinaujina kas 30 s. `test_projekto_valdymas.py`.

## Gamybos barai (nuo 2026-10-25)

Vartotojo sprendimas: cechas skirstomas į barus, kiekvienas darbo centras
priklauso vienam (`areas`, `work_centres.area_id`, migracija 3). Pavyzdžiuose:

| Kodas | Baras | Centrai |
|---|---|---|
| `MAB` | Mechaninio apdirbimo | juostinis pjūklas, lazeris, plazma, lenkimas |
| `TKB` | Tekinimo | universalios tekinimo staklės, CNC tekinimas, CNC frezavimas |
| `SVB` | Suvirinimo | 10 rankinių surinkimo ir suvirinimo stočių `SV-01…SV-10` |
| `DZB` | Dažymo | smėliavimas, šlapias dažymas, miltelinis dažymas |
| `ATB` | Automatikos | elektros spintų surinkimas, programavimas ir derinimas |
| `TIS` | Technologinių įrenginių surinkimo | mechaninis surinkimas, testavimas |

- Baras turi meistrą (`master_id`); cecho lange – grupės su meistru ir
  skaičiais (dirba / pristabdyta / gali pradėti), filtras pagal barą
  (`localStorage pf.area`). Terminalo centro pasirinkimas, planas (`optgroup`),
  analitika („Gamybos barai“) ir administravimas – taip pat pagal barus.
- **Vartotojui galima priskirti baro kodą** vietoje centrų (`users.centres`
  `["SVB"]`): `auth.can_centre(user, centras, baras)` leidžia visus to baro
  centrus, ir naujus. Todėl baro ir centro kodai negali sutapti
  (`save_area` / `save_centre` tikrina).
- Centras be baro rodomas grupėje „Be baro“ – nieko nedingsta.
- Nauja centro rūšis `programavimas` → etapas „Programavimas“ (`CENTRE_PHASE`).

**PIN – greita paieška ir bandymų riba** (2026-10-25). PIN buvo PBKDF2, tad
neturint vardo tekdavo tikrinti visus vartotojus iš eilės: 6 PIN – iki 0,9 s,
50 operatorių būtų ~7 s. Dabar `auth.pin_key` – HMAC-SHA256 su diegties
paslaptimi (`settings.pin_secret`, migracija 4), paieška pagal indeksą
(0,005–0,02 s). 4 skaitmenų PIN lėta maiša vis tiek neapsaugotų (10^4
variantų), todėl `web.app` riboja nesėkmingus bandymus: 8 per 5 min. vienam
adresui → 429. Seni PBKDF2 PIN atpažįstami ir prisijungus perrašomi.
`test_pin_randamas_greitai_ir_bandymu_riba`,
`test_senas_pbkdf2_pin_perrasomas_prisijungus`, `test_barai.py`.

## Komponentų pirkimai (nuo 2026-10-25)

Vartotojo prašymas: suprojektavus reikia užsakyti standartinius komponentus;
atskiras langas, kurio duomenys vėliau ateis iš ERP (D365), ir **realaus laiko
gavimo būsenos**. Langas `#/komponentai` (ir `#/komponentai/<projekto id>`),
projekto puslapyje – santrauka ir lentelė.

| | |
|---|---|
| eilutė | `components`: projektas, mazgas (arba visam projektui), prekės kodas, kiekis, tiekėjas, užsakymo nr. / eilutė, užsakyta, tiekėjo patvirtinta data, reikia iki, gauta, vieta |
| būsena | **išvedama iš faktų**, ne įrašoma (`components.status_of`): neužsakyta → užsakyta (yra PO nr.) → patvirtinta data → gauta dalinai → gauta; atšaukta – žymė. Tad ji atitinka duomenis ir įvedant ranka, ir importuojant |
| įspėjimai | `late` – patvirtinta data praėjo, ne viskas gauta; `risk` – patvirtinta data vėlesnė už „reikia iki“ arba reikia per 7 d., o data nepatvirtinta; `overdue_need` – „reikia iki“ praėjo |
| gavimai | `component_receipts` – kiekvienas atskirai (kas, kada, kiek, šaltinis); daugiau nei užsakyta – klaida; gautos eilutės atšaukti negalima |
| importas | CSV iš ERP eksporto (`components.COLUMNS`); eilutė atpažįstama pagal užsakymo nr. + eilutę (be jų – projektas, mazgas, prekės kodas), rasta atnaujinama; padidėjęs gautas kiekis registruojamas kaip gavimas – TIK skirtumas, tad pakartotinis importas nedubliuoja; klaida – neįrašoma niekas. Prijungus D365 tas pats `import_csv` kelias keičiamas tiesioginiu skaitymu |
| etapas | `_sync_phase`: projekto / mazgo etapas „Komponentų užsakymas“ – vykdoma, kai kas nors užsakyta, baigta, kai viskas gauta; nauja negauta eilutė jį vėl atidaro |
| ceche | terminale ir plane – **įspėjimas, ne draudimas** „negauti pirktiniai komponentai: N eil.“ (`missing_for_assembly`: mazgo ir viso projekto eilutės); dalį darbų galima pradėti ir be visų komponentų, sprendžia meistras |
| teisės | `purchase` (eilutės, importas) – pirkimai, vadovas, admin; `receive` (gavimas) – pirkimai, sandėlis, meistras, admin; matyti – `view` |
| analitika | „Tiekėjų patikimumas“: gauta vėliau nei pažadėta, vid. vėlavimas, dabar vėluoja (`supplier_report`) |

Langas atsinaujina kas 30 s (ne kai atidarytas dialogas). `test_komponentai.py`.

## Analitika

Darbo laikas, prastovos (planuotos pauzės `pertrauka`, `pamaina` rodomos,
bet į prastovą neįeina – kitaip naktis užgožtų tikras priežastis), faktas /
norma, brokas, laukimas prieš operaciją (nuo ankstesnės maršruto operacijos
pabaigos iki šios pradžios), etapų planas prieš faktą, neatitiktys pagal
kategoriją.

## Ko dar nėra (sąmoningai)

- Integracijų (D365, PDM, Lantek) – testinė versija be jų.
- Lantek lakšto kaip atskiros užduoties su detalėmis iš kelių projektų.
- Etapų priklausomybių (pabaiga → pradžia, poslinkis) – kol kas tik mazgų
  `requires` ir maršruto eilė.
- Patvirtintos eilės kopijos: planuotojo perrikiavimas matomas terminale iš
  karto (PrefabFlow laikė patvirtintą tvarką atskirai).
- MS SQL – schema paprasta, kad perkelti būtų nesunku.

## Vizualinis stilius (nuo 2026-10-25)

Vartotojo sprendimas: **šviesus inžinerinis** stilius (kaip CAD brėžinys ir
technologinė dokumentacija), logotipas – **paprastas ženklas + VMGT**.

- Spalvos – `app.css` `:root`. Brėžinio mėlyna `--accent` – mygtukai,
  nuorodos. Signalinė oranžinė `--signal` – TIK ženklas ir žymekliai:
  logotipas, juosta po antrašte, aktyvus meniu ir kortelė, antraštės žymė,
  fokusas. Būsenai oranžinė nenaudojama: pristabdyta / „dėmesio“ – ochra
  (`--pause`, `--h-yellow` #a87800), kitaip nesiskirtų nuo ženklo.
- Fonas – brėžinio tinklelis (24 px, kas 120 px ryškesnis). Kortelės – kampų
  žymės (`--tick`) ir oranžinis kvadratėlis prie antraštės. Būsenų žymos –
  „indikatoriaus lemputė“ (`.pill::before`). Kampai 2–3 px, skaičiai lentelėse
  – vienodo pločio šriftu.
- Logotipas – stilizuota robotinės rankos jungtis (SVG `index.html`, taip pat
  favicon). Prisijungimo lange – robotinės rankos brėžinys (`ARM_SVG`).
- Terminalas lieka tamsus (staklių pultas), su oranžinėmis kampų žymėmis.
  Tamsus režimas – pagal sistemos nustatymą (`prefers-color-scheme`).
- Rasta perdarant: srauto atšakų `.lane` sutapo su `.gantt .lane` (iškraipė
  etapų grafiką) → `.flane`; savaitės plano `.hbar` perrašė analitikos juostą
  → `.dbar`. Naujoms klasėms tikrinti, ar pavadinimas dar neužimtas.

## UI pastaba

`.card > *, main > * { min-width: 0 }` – tinklelio vaikas be šito išsiplečia
pagal plačią lentelę ir telefone puslapis tampa platesnis už ekraną (rasta
2026-10-25: departamentų lentelė, 716 px).


`[hidden] { display: none !important; }` būtina: be jos `#modal`
`display: grid` nugalėdavo `hidden` atributą, ir paslėptas langas dengė visus
mygtukus (rasta Playwright patikra 2026-10-24).
