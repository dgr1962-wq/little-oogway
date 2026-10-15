import importlib.util
import json
import sqlite3
import tempfile
import time
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "configure-openwebui-models.py"
SPEC = importlib.util.spec_from_file_location("configure_openwebui_models", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class OpenWebUiSelectorTests(unittest.TestCase):
    def test_base_engines_stay_active_but_hidden(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            database = root / "webui.db"
            connection = sqlite3.connect(database)
            now = int(time.time())
            connection.executescript(
                """
                CREATE TABLE model(
                    id TEXT PRIMARY KEY, user_id TEXT NOT NULL, base_model_id TEXT,
                    name TEXT NOT NULL, meta TEXT NOT NULL, params TEXT NOT NULL,
                    created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL,
                    is_active BOOLEAN NOT NULL
                );
                CREATE TABLE function(
                    id TEXT PRIMARY KEY, user_id TEXT NOT NULL, name TEXT NOT NULL,
                    type TEXT NOT NULL, content TEXT NOT NULL, meta TEXT NOT NULL,
                    created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL,
                    valves TEXT, is_active INTEGER NOT NULL, is_global INTEGER NOT NULL
                );
                CREATE TABLE user(
                    id TEXT PRIMARY KEY, role TEXT NOT NULL, created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL, settings TEXT
                );
                """
            )
            connection.execute(
                "INSERT INTO user VALUES (?, 'admin', ?, ?, ?)",
                ("admin-test", now, now, json.dumps({"ui": {}})),
            )
            connection.execute(
                "INSERT INTO model VALUES (?, ?, ?, ?, '{}', '{}', ?, ?, 1)",
                (
                    "little-oogway-core",
                    "admin-test",
                    "qwen3:8b",
                    "Little Oogway Core",
                    now,
                    now,
                ),
            )
            connection.commit()
            connection.close()

            MODULE.configure(database, root / "backups", None)

            connection = sqlite3.connect(database)
            active, meta = connection.execute(
                "SELECT is_active, meta FROM model WHERE id = 'qwen3:8b'"
            ).fetchone()
            self.assertEqual(active, 1)
            self.assertTrue(json.loads(meta)["hidden"])
            self.assertEqual(
                connection.execute(
                    "SELECT is_active FROM function WHERE id = 'little-oogway-roundtable'"
                ).fetchone(),
                (1,),
            )
            settings = json.loads(
                connection.execute(
                    "SELECT settings FROM user WHERE id = 'admin-test'"
                ).fetchone()[0]
            )
            self.assertEqual(settings["ui"]["models"], ["little-oogway-core"])
            core_meta = json.loads(
                connection.execute(
                    "SELECT meta FROM model WHERE id = 'little-oogway-core'"
                ).fetchone()[0]
            )
            self.assertFalse(core_meta["capabilities"]["builtin_tools"])
            connection.close()


if __name__ == "__main__":
    unittest.main()
