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
| `services/routing.py` | Technologinis srautas: detalių atšakos → mazgas, kur keliauti toliau, išleidimas į gamybą, perdavimai, atsekamumas |
| `services/ncr.py` | Neatitiktys: atvira → priskirta → uzdaryta |
| `services/drawings.py` | PDF brėžiniai su revizija (vėliau – iš PDM) |
| `services/importer.py` | Maršrutų CSV importas (vėliau – D365 / PDM) |
| `services/components.py` | Komponentų pirkimai: eilutės, gavimai, CSV importas iš ERP eksporto, tiekėjų patikimumas |
| `services/actions.py` | Projekto komandos užduotys: statusai, leistini perėjimai, istorija |
| `services/meetings.py` | Susitikimų protokolai (MoM): veiksmai → užduotys, patvirtinimas |
| `services/health.py` | Projekto sveikata realiu laiku: 4 sritys, lygiai, priežastys |
| `services/capacity.py` | Resursų apkrova: departamentų poreikis prieš pajėgumą savaitėmis, trūkumai, krepšelio projektų tilpimas |
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

## Resursų apkrova (nuo 2026-10-25)

Vartotojo tikslas: matyti, kiek projektų vykdoma, kiek dar galima prisiimti ir
kur trūksta žmonių. Sprendimai (2026-10-25): departamentai – **biuro skyriai
ir gamybos barai**; poreikis – **etapų planuojamos valandos + cecho normos**;
žingsnis – **savaitė**. Langas „Apkrova“ (`#/apkrova`).

| | |
|---|---|
| departamentai | `departments` (migracija 6): biuro skyrius – `phase_kinds` (kurių etapų darbas: projektavimas, technologija, komponentai, programavimas, testavimas); gamybos baras – `area_id` |
| pajėgumas | žmonės × val. per savaitę × prieinamumas (numatyta 85 % – atostogos, ligos, kiti darbai); keičiama lange (teisė `projects`) |
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
- Kokybės patikrų šablonų ir protokolų, nuotraukų prie neatitikčių.
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
