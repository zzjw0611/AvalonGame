from pathlib import Path
from alembic import command
from alembic.config import Config
from sqlalchemy import inspect
from app.storage import Database


def test_upgrade_preserves_sessions_and_matches_models(tmp_path, monkeypatch):
    url = f'sqlite:///{tmp_path}/migrated.db'
    monkeypatch.setenv('DATABASE_URL', url)
    root = Path(__file__).resolve().parents[1]
    cfg = Config(str(root / 'alembic.ini'))
    command.upgrade(cfg, 'head')
    db = Database(url)
    guest = db.create_guest('迁移测试')
    command.upgrade(cfg, 'head')
    assert db.authenticate(guest['token'])['name'] == '迁移测试'
    assert {'guests', 'rooms', 'alembic_version'} <= set(inspect(db.engine).get_table_names())
    command.check(cfg)
    db.engine.dispose()
