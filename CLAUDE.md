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
kataloge (`host`, `port`, `data_dir`, `seed_sample`, `session_hours`); failo
nėra – numatytosios. Duomenys – `data/` (`vmgt.db`, įkelti brėžiniai
`data/files/`), į git neįtraukiami.

**Testinė aplinka (nuo 2026-10-24) – be integracijų.** Tuščia bazė užpildoma
pavyzdžiais (`services/seed.py`): 3 projektai su žyme PAVYZDYS, 10 darbo
centrų, dalis darbų „atlikta“ praeityje, kad cechas ir analitika turėtų ką
rodyti. Visų pavyzdinių vartotojų slaptažodis `vmgt2026` (tik testams):
`admin`, `vadovas`, `planuotojas`, `technologas`, `meistras` (PIN 9999),
`meistras2` (PIN 8888), `kokybe`, `pirkimai`, `sandelis` (PIN 5555), `op1` (PIN 1111),
`op2` (2222), `op3` (3333, tik Suvirinimo baras `SVB`).

## Struktūra

| Kur | Kas |
|---|---|
| `vmgt/db.py` | SQLite jungtis, schema (`MIGRATIONS`, `PRAGMA user_version`), laikrodis `now()` / `set_clock` testams, įvykių žurnalas `log_event` |
| `vmgt/services/` | **Gamybos taisyklės be web** – jokio FastAPI. `RuleError` → 409, `NotFound` → 404 |
| `services/auth.py` | Vartotojai, rolės (`ROLES`), teisės (`PERMS`), PBKDF2, sesijos (bazėje – žetono SHA-256), PIN terminalui, centrų apribojimas `can_centre` |
| `services/projects.py` | Krepšelis, mazgai (`requires` – nuo kurių mazgų priklauso), etapai (`PHASE_KINDS`), gamybos barai, darbo centrai |
| `services/tasks.py` | Užduotys, eilės, terminalo veiksmai, **visos pradėjimo taisyklės – `block_reason`** |
| `services/ncr.py` | Neatitiktys: atvira → priskirta → uzdaryta |
| `services/drawings.py` | PDF brėžiniai su revizija (vėliau – iš PDM) |
| `services/importer.py` | Maršrutų CSV importas (vėliau – D365 / PDM) |
| `services/components.py` | Komponentų pirkimai: eilutės, gavimai, CSV importas iš ERP eksporto, tiekėjų patikimumas |
| `services/analytics.py` | Cecho būsena (`floor`) ir efektyvumo ataskaita (`report`) |
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
1. užduotis patvirtinta planuotojo (`approved`);
2. centre niekas nevyksta ir nėra pristabdytos užduoties;
3. griežtos eilės centre (`strict_order`, numatyta) – tai pirma patvirtinta;
4. ankstesnė maršruto operacija baigta arba perdavė bent dalį (`qty_good > 0`)
   – dalinis perdavimas vienetinėje gamyboje kasdienis;
5. pirmoji mazgo operacija – visi `requires` mazgai baigti;
6. brėžinio revizija nepasikeitė; pasikeitus – meistras patvirtina
   (`ack_revision`, teisė `ack_rev`).

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
- Kokybės patikrų šablonų ir protokolų, nuotraukų prie neatitikčių.
- Patvirtintos eilės kopijos: planuotojo perrikiavimas matomas terminale iš
  karto (PrefabFlow laikė patvirtintą tvarką atskirai).
- MS SQL – schema paprasta, kad perkelti būtų nesunku.

## UI pastaba

`[hidden] { display: none !important; }` būtina: be jos `#modal`
`display: grid` nugalėdavo `hidden` atributą, ir paslėptas langas dengė visus
mygtukus (rasta Playwright patikra 2026-10-24).
