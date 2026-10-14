#!/usr/bin/env python3
"""Operate only the disposable TokenSpace Compose database."""
import argparse
import hashlib
from pathlib import Path
import re
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
PROJECT = 'little-oogway-tokenspace-dev'

def compose(*args, sql=None):
    if not shutil.which('docker'):
        raise SystemExit('Docker missing. Install docker.io and docker-compose-v2 in the host terminal.')
    return subprocess.run(
        ['docker', 'compose', '--project-name', PROJECT, '--project-directory', str(ROOT),
         '--env-file', str(ROOT / '.env'), '-f', str(ROOT / 'compose.yaml'), *args],
        input=sql, text=True, check=True)

def psql(sql):
    return compose('exec', '-T', 'db', 'psql', '-X', '-v', 'ON_ERROR_STOP=1',
                   '-U', 'tokenspace_dev', '-d', 'tokenspace_v2_dev', sql=sql)

def migration_sql(directory=ROOT / 'migrations'):
    chunks = ["SELECT pg_advisory_lock(740021602);", """
CREATE SCHEMA IF NOT EXISTS tokenspace_migrations;
CREATE TABLE IF NOT EXISTS tokenspace_migrations.applied (
 version text PRIMARY KEY, checksum text NOT NULL, applied_at timestamptz NOT NULL DEFAULT now()
);
"""]
    paths = sorted(directory.glob('*.sql'))
    if not paths:
        raise ValueError('No migrations found')
    for path in paths:
        if not re.fullmatch(r'[0-9]{4}_[a-z0-9_]+\.sql', path.name):
            raise ValueError(f'Invalid migration name: {path.name}')
        raw = path.read_bytes()
        checksum = hashlib.sha256(raw).hexdigest()
        version = path.stem
        chunks.append(f"""
BEGIN;
DO $$ BEGIN
 IF EXISTS (SELECT 1 FROM tokenspace_migrations.applied
 WHERE version = '{version}' AND checksum <> '{checksum}') THEN
 RAISE EXCEPTION 'Applied migration changed: {version}';
 END IF;
END $$;
SELECT NOT EXISTS (SELECT 1 FROM tokenspace_migrations.applied WHERE version = '{version}') AS pending \\gset
\\if :pending
{raw.decode('utf-8')}
INSERT INTO tokenspace_migrations.applied(version, checksum) VALUES ('{version}', '{checksum}');
\\endif
COMMIT;
""")
    chunks.append('SELECT pg_advisory_unlock(740021602);')
    return '\n'.join(chunks)

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['start', 'stop', 'inspect', 'migrate', 'smoke', 'reset'])
    parser.add_argument('--confirm-disposable-reset', action='store_true')
    args = parser.parse_args()
    if not (ROOT / '.env').is_file():
        parser.error('Create tokenspace/.env from .env.example first')
    if args.action == 'reset':
        if not args.confirm_disposable_reset:
            parser.error('Reset deletes ONLY little-oogway-tokenspace-dev-data; supply --confirm-disposable-reset')
        compose('down', '--volumes')
    elif args.action == 'start':
        compose('up', '-d', '--wait', '--wait-timeout', '120')
    elif args.action == 'stop':
        compose('stop')
    elif args.action == 'migrate':
        psql(migration_sql())
    elif args.action == 'smoke':
        psql((ROOT / 'tests' / 'smoke.sql').read_text())
    else:
        compose('ps')
        compose('port', 'db', '5432')
        psql("SELECT current_database(), version(); SELECT extname, extversion FROM pg_extension WHERE extname='vector'; SELECT table_schema, table_name FROM information_schema.tables WHERE table_schema IN ('tokenspace_v2','tokenspace_migrations') ORDER BY 1,2; SELECT * FROM tokenspace_migrations.applied ORDER BY version;")

if __name__ == '__main__':
    main()
