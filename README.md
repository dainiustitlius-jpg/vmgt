# VMGT

Vienetinės gamybos projektų stebėsena ir shop floor valdymas.

Projektai pereina etapus nuo projektavimo iki testavimo; gamybos ir surinkimo
etapuose darbas vyksta darbo centrų terminaluose. Sistema rodo projekto eigą
realiu laiku, registruoja kokybės neatitiktis ir analizuoja, kur prarandamas
laikas.

Šaltiniai ateityje: MS Dynamics 365 F&O (projektai, pirkimai), SolidWorks PDM
(brėžiniai, BOM), Lantek (lazerio išdėstymai). Testinė versija dirba be
integracijų: duomenys įvedami ranka arba importuojami iš CSV.

## Paleidimas

```powershell
pip install -r requirements.txt
python -m vmgt
```

Naršyklėje: <http://localhost:8080>. Pirmą kartą bazė sukuriama
`data/vmgt.db` ir užpildoma pavyzdiniais duomenimis.

Testiniai vartotojai (slaptažodis visiems `vmgt2026`, tik testinei aplinkai):
`admin`, `vadovas`, `planuotojas`, `technologas`, `meistras`, `kokybe`.
Operatoriai jungiasi PIN kodu terminale: `1111`, `2222`, `3333`.

Terminalą planšetėje atidarykite adresu `http://<kompiuterio-IP>:8080`
tame pačiame tinkle. Iš naujo pradėti su pavyzdžiais – ištrinkite `data/`.

## Testai

```powershell
pip install -r requirements-dev.txt
python -m pytest
```
