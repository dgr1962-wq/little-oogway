import hashlib
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import sys

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('dev', ROOT / 'scripts/dev.py')
dev = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dev)

class DevTests(unittest.TestCase):
    def test_migrations_lock_transaction_and_checksum(self):
        sql = dev.migration_sql()
        checksum = hashlib.sha256((ROOT / 'migrations/0001_core.sql').read_bytes()).hexdigest()
        self.assertIn(checksum, sql)
        self.assertLess(sql.index('pg_advisory_lock'), sql.index('CREATE TABLE'))
        self.assertIn("RAISE EXCEPTION 'Applied migration changed:", sql)
        self.assertIn('\\if :pending', sql)
        self.assertLess(sql.index('BEGIN;'), sql.index('CREATE EXTENSION'))
        self.assertLess(sql.index('INSERT INTO tokenspace_migrations.applied'), sql.index('COMMIT;'))

    def test_rejects_unsafe_migration_name(self):
        with tempfile.TemporaryDirectory() as folder:
            Path(folder, "bad'name.sql").write_text('SELECT 1;')
            with self.assertRaises(ValueError):
                dev.migration_sql(Path(folder))

    def test_fixed_compose_target_and_psql_no_host_connection(self):
        with patch.object(dev.shutil, 'which', return_value='/usr/bin/docker'), patch.object(dev.subprocess, 'run') as run:
            dev.psql('SELECT 1;')
        argv = run.call_args.args[0]
        self.assertIn(dev.PROJECT, argv)
        self.assertIn(str(ROOT / 'compose.yaml'), argv)
        self.assertEqual(argv[-4:], ['-U','tokenspace_dev','-d','tokenspace_v2_dev'])
        self.assertIn('exec', argv)
        self.assertNotIn('-h', argv)
        self.assertEqual(run.call_args.kwargs['input'], 'SELECT 1;')
        self.assertTrue(run.call_args.kwargs['check'])

    def test_reset_requires_explicit_flag(self):
        with patch.object(sys, 'argv', ['dev.py','reset']), patch.object(dev.Path, 'is_file', return_value=True), patch.object(dev, 'compose') as compose:
            with self.assertRaises(SystemExit):
                dev.main()
            compose.assert_not_called()

    def test_reset_only_fixed_compose_volume(self):
        with patch.object(sys, 'argv', ['dev.py','reset','--confirm-disposable-reset']), patch.object(dev.Path, 'is_file', return_value=True), patch.object(dev, 'compose') as compose:
            dev.main()
            compose.assert_called_once_with('down','--volumes')

if __name__ == '__main__':
    unittest.main()
