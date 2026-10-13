"""Verify recovery uses configuration and refuses incomplete/unsafe archives."""
import importlib.util
import sqlite3
import zipfile
from contextlib import closing
from pathlib import Path
import pytest


@pytest.fixture
def recovery(tmp_path, monkeypatch):
    database = tmp_path / 'configured' / 'custom.db'
    database.parent.mkdir()
    media = tmp_path / 'configured-media'
    media.mkdir()
    monkeypatch.setenv('DATABASE_URL', 'sqlite:///' + database.as_posix())
    monkeypatch.setenv('MEDIA_ROOT', str(media))
    spec = importlib.util.spec_from_file_location('audit_recovery', Path(__file__).parents[1] / 'backend/recovery.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module, database, media


def test_configuration_aware_backup_restore_round_trip(recovery, tmp_path):
    module, database, media = recovery
    with closing(sqlite3.connect(database)) as connection, connection:
        connection.execute('CREATE TABLE marker (value TEXT)')
        connection.execute("INSERT INTO marker VALUES ('original')")
    (media / 'image.png').write_bytes(b'original fixture')
    archive = module.backup(tmp_path / 'backups')
    with zipfile.ZipFile(archive) as saved:
        assert 'luma.db' in saved.namelist()
        assert 'media/image.png' in saved.namelist()
    with closing(sqlite3.connect(database)) as connection, connection:
        connection.execute("UPDATE marker SET value='changed'")
    (media / 'image.png').write_bytes(b'changed')
    assert module.restore(archive) == database
    with closing(sqlite3.connect(database)) as connection:
        assert connection.execute('SELECT value FROM marker').fetchone()[0] == 'original'
    assert (media / 'image.png').read_bytes() == b'original fixture'


def test_missing_database_refuses_backup(recovery, tmp_path):
    module, _, _ = recovery
    with pytest.raises(RuntimeError, match='missing'):
        module.backup(tmp_path / 'backups')
    assert not (tmp_path / 'backups').exists()


def test_restore_rejects_missing_database(recovery, tmp_path):
    module, _, _ = recovery
    archive = tmp_path / 'missing.zip'
    with zipfile.ZipFile(archive, 'w') as output:
        output.writestr('media/image.png', b'fixture')
    with pytest.raises(RuntimeError, match='no database'):
        module.restore(archive)


def test_restore_refuses_archive_path_traversal(recovery, tmp_path):
    module, database, _ = recovery
    archive = tmp_path / 'unsafe.zip'
    with zipfile.ZipFile(archive, 'w') as output:
        output.writestr('media/../../outside.txt', b'fixture')
        output.writestr('luma.db', b'fixture')
    with pytest.raises(RuntimeError, match='Unsafe'):
        module.restore(archive)
    assert not database.exists()
    assert not (tmp_path / 'outside.txt').exists()
