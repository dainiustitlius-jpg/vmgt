"""Paleidimas: `python -m vmgt` (nustatymai – `vmgt_config.json`, jei yra)."""

import uvicorn

from . import config
from .web.app import create_app


def main() -> None:
    cfg = config.load()
    print(f"VMGT: http://localhost:{cfg.port}  (bazė: {cfg.db_path})")
    uvicorn.run(create_app(cfg), host=cfg.host, port=cfg.port)


if __name__ == "__main__":
    main()
