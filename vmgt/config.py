"""Serviso nustatymai: `vmgt_config.json` šalia darbo katalogo.

Failo nėra – imamos numatytosios reikšmės. Nustatymai laikomi faile, o ne
kode, kad perkeliant servisą į kitą kompiuterį ar VM nereikėtų keisti kodo.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path


@dataclass
class Config:
    host: str = "0.0.0.0"
    port: int = 8080
    # bazė ir įkelti failai (brėžiniai, nuotraukos) – vienas duomenų katalogas
    data_dir: str = "data"
    # tuščią bazę užpildyti pavyzdiniais duomenimis (testinė aplinka)
    seed_sample: bool = True
    # ir penki pavyzdiniai projektai su visu technologiniu keliu (`demo.py`)
    seed_demo: bool = True
    session_hours: int = 12
    # technologo failų (DXF, NC, programų) katalogas; gali būti tinklo diskas,
    # kurį mato ir staklių kompiuteriai. Tuščia – data_dir/nc
    nc_dir: str = ""
    # kaip tą katalogą mato cecho kompiuteriai (pvz. \\serveris\NC) – rodoma
    # terminale, kad operatorius rastų failą staklėse. Tuščia – nc_dir
    nc_share: str = ""
    extra: dict = field(default_factory=dict)

    @property
    def db_path(self) -> Path:
        return Path(self.data_dir) / "vmgt.db"

    @property
    def files_dir(self) -> Path:
        return Path(self.data_dir) / "files"

    @property
    def nc_path(self) -> Path:
        return Path(self.nc_dir) if self.nc_dir else Path(self.data_dir) / "nc"


def load(path: str | os.PathLike = "vmgt_config.json") -> Config:
    p = Path(path)
    if not p.exists():
        return Config()
    raw = json.loads(p.read_text(encoding="utf-8"))
    known = {k: raw[k] for k in asdict(Config()) if k in raw}
    return Config(**known)
