import pytest
from fastapi.testclient import TestClient

from vmgt import config, db
from vmgt.web.app import create_app


@pytest.fixture
def cfg(tmp_path):
    return config.Config(data_dir=str(tmp_path / "data"), seed_sample=False)


@pytest.fixture
def con(cfg):
    c = db.connect(cfg.db_path)
    db.migrate(c)
    yield c
    c.close()


@pytest.fixture
def clock():
    """Valdomas laikrodis: clock.set('2026-10-20T08:00:00+00:00')."""
    class C:
        t = "2026-10-20T08:00:00+00:00"

        def set(self, t):
            self.t = t

    c = C()
    db.set_clock(lambda: c.t)
    yield c
    db.set_clock(None)


@pytest.fixture
def sample_client(tmp_path):
    # be penkių pavyzdinių projektų (`demo.py`) – kiti testai remiasi pagrindiniais
    # pavyzdžiais, o demo turi savo testą (test_demo.py)
    cfg = config.Config(data_dir=str(tmp_path / "data"), seed_sample=True, seed_demo=False)
    return TestClient(create_app(cfg))


@pytest.fixture
def demo_client(tmp_path):
    cfg = config.Config(data_dir=str(tmp_path / "data"), seed_sample=True, seed_demo=True)
    return TestClient(create_app(cfg))


def login(client, login=None, password="vmgt2026", pin=None):
    body = {"pin": pin} if pin else {"login": login, "password": password}
    r = client.post("/api/login", json=body)
    assert r.status_code == 200, r.text
    return r.json()
