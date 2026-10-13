"""Configured SQLite/media recovery. Stop Backend services before restoring."""
import argparse
import json
import os
import shutil
import sqlite3
import tempfile
import zipfile
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from dotenv import load_dotenv
from luma_backend.config import Config
from luma_backend.maintenance import sqlite_path


def locations():
    load_dotenv(Path(__file__).with_name('.env'))
    config = Config()
    return sqlite_path(config.SQLALCHEMY_DATABASE_URI), Path(config.MEDIA_ROOT).resolve()


def backup(destination):
    database, media = locations()
    destination = Path(destination).resolve()
    if not database.is_file():
        raise RuntimeError('Configured database is missing; backup refused.')
    if destination == media or media in destination.parents:
        raise RuntimeError('Backup destination must be outside media.')
    destination.mkdir(parents=True, exist_ok=True)
    archive = destination / ('luma_backup_' + datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S_%f') + '.zip')
    temporary_archive = archive.with_suffix('.tmp')
    try:
        with tempfile.TemporaryDirectory(prefix='luma-backup-') as temp:
            snapshot = Path(temp) / 'luma.db'
            with closing(sqlite3.connect(database)) as source, closing(sqlite3.connect(snapshot)) as target:
                source.backup(target)
            with zipfile.ZipFile(temporary_archive, 'w', zipfile.ZIP_DEFLATED) as output:
                output.write(snapshot, 'luma.db')
                output.writestr('manifest.json', json.dumps({'version': 1}))
                for file in media.rglob('*') if media.exists() else []:
                    if file.is_symlink():
                        raise RuntimeError('Symlinked media cannot be backed up.')
                    if file.is_file():
                        output.write(file, 'media/' + file.relative_to(media).as_posix())
        os.replace(temporary_archive, archive)
    except Exception:
        temporary_archive.unlink(missing_ok=True)
        raise
    return archive


def restore(archive):
    database, media = locations()
    if any(Path(str(database)+suffix).exists() for suffix in ('-wal','-shm','-journal')):
        raise RuntimeError('Stop Backend services and resolve SQLite journals before restoring.')
    with tempfile.TemporaryDirectory(prefix='luma-restore-') as temp:
        staging = Path(temp)
        with zipfile.ZipFile(archive) as source:
            for member in source.infolist():
                name = PurePosixPath(member.filename)
                if name.is_absolute() or '..' in name.parts or '\\' in member.filename or ':' in member.filename:
                    raise RuntimeError('Unsafe archive path; restore refused.')
                if ((member.external_attr >> 16) & 0o170000) == 0o120000:
                    raise RuntimeError('Archive symlinks are not allowed.')
            if 'luma.db' not in source.namelist():
                raise RuntimeError('Archive contains no database; restore refused.')
            source.extractall(staging)
        restored = staging / 'luma.db'
        with closing(sqlite3.connect(restored.as_uri()+'?mode=ro', uri=True)) as connection:
            if connection.execute('PRAGMA quick_check').fetchone()[0] != 'ok':
                raise RuntimeError('Backup integrity check failed.')
        database.parent.mkdir(parents=True, exist_ok=True)
        fd, name = tempfile.mkstemp(prefix='.luma-restore-', suffix='.db', dir=database.parent)
        os.close(fd)
        pending = Path(name)
        try:
            shutil.copy2(restored, pending)
            os.replace(pending, database)
        finally:
            pending.unlink(missing_ok=True)
        for file in (staging / 'media').rglob('*'):
            if file.is_file():
                target = (media / file.relative_to(staging / 'media')).resolve()
                if media not in target.parents:
                    raise RuntimeError('Media target escaped configured directory.')
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(file, target)
    return database


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    save = commands.add_parser('backup'); save.add_argument('--destination', type=Path, required=True)
    recover = commands.add_parser('restore'); recover.add_argument('--archive', type=Path, required=True)
    args = parser.parse_args()
    result = backup(args.destination) if args.command == 'backup' else restore(args.archive)
    print(json.dumps({'path': str(result)}))
