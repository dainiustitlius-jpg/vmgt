"""Paleidimas: `python -m vmgt` (nustatymai – `vmgt_config.json`, jei yra)."""

import socket

import uvicorn

from . import config
from .web.app import create_app


def lan_addresses() -> list[str]:
    """Šio kompiuterio IPv4 adresai vietiniame tinkle – kad būtų aišku, kokiu
    adresu VMGT atidaryti kituose biuro ir cecho kompiuteriuose."""
    out = []
    try:
        # UDP „jungtis“ nieko nesiunčia – tik parodo, per kurią tinklo plokštę eitų srautas
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("10.255.255.255", 1))
            out.append(s.getsockname()[0])
    except OSError:
        pass
    try:
        out += socket.gethostbyname_ex(socket.gethostname())[2]
    except OSError:
        pass
    return [a for i, a in enumerate(out) if a not in out[:i] and not a.startswith(("127.", "169.254."))]


def main() -> None:
    cfg = config.load()
    print(f"VMGT: http://localhost:{cfg.port}  (bazė: {cfg.db_path})")
    if cfg.host in ("0.0.0.0", ""):
        for a in lan_addresses():
            print(f"      kitiems kompiuteriams tinkle: http://{a}:{cfg.port}")
        print(f"      neatsidaro kitur? Vieną kartą paleiskite leisti_tinkle.bat (ugniasienė, prievadas {cfg.port})")
    uvicorn.run(create_app(cfg), host=cfg.host, port=cfg.port)


if __name__ == "__main__":
    main()
