import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location("local_env", Path(__file__).resolve().parents[1] / "local-env.py")
LOCAL = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(LOCAL)

MANIFEST = "infra/environment-sync.json"
PRODUCTION = {"file": MANIFEST, "target": "brain-production"}


def write_manifest(root, brain=None, ui=None):
    (root / "infra").mkdir(exist_ok=True)
    (root / MANIFEST).write_text(json.dumps({"targets": [
        {"name": "brain-production", "settings": brain or {
            "BRAIN_ENVIRONMENT": "production", "BRAIN_OPENAI_PROJECT": "project"}},
        {"name": "ui-production", "settings": ui or {"BRAIN_URL": "https://brain.example"}}]}))


class LocalEnvironmentTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "config").mkdir()
        write_manifest(self.root)
        self.config = {"brain": {"directory": "brain", "production_settings": PRODUCTION,
            "settings": {"BRAIN_ENVIRONMENT": "development"},
            "sources": [{"path": ".env.shared", "keys": ["BRAIN_OPENAI_API_KEY"]}]}}

    def load(self, source):
        (self.root / "config/local-environments.json").write_text(json.dumps(self.config))
        with patch.object(LOCAL, "dotenv_values", return_value=source):
            with patch.object(LOCAL.time, "sleep"):
                return LOCAL.load_environment("brain", self.root)

    def test_obsolete_secrets_and_settings_are_not_inherited(self):
        result = self.load({"BRAIN_OPENAI_API_KEY": "secret", "ADMIN_API_TOKEN": "unused",
                            "BRAIN_ENVIRONMENT": "production", "BRAIN_OPENAI_PROJECT": "obsolete"})
        self.assertEqual(result, {"BRAIN_ENVIRONMENT": "development", "BRAIN_OPENAI_PROJECT": "project",
                                  "BRAIN_OPENAI_API_KEY": "secret"})

    def test_missing_secret_stops_without_exposing_other_values(self):
        with self.assertRaises(LOCAL.EnvironmentError) as error:
            self.load({"OTHER_KEY": "do-not-print"})
        self.assertNotIn("do-not-print", str(error.exception))

    def test_production_config_is_rejected_before_reading_secrets(self):
        self.config["brain"]["settings"]["BRAIN_ENVIRONMENT"] = "production"
        with self.assertRaisesRegex(LOCAL.EnvironmentError, "development"):
            self.load({"BRAIN_OPENAI_API_KEY": "secret"})

    def test_credential_cannot_be_put_in_public_config(self):
        self.config["brain"]["settings"]["BRAIN_OPENAI_API_KEY"] = "unsafe"
        with self.assertRaises(LOCAL.EnvironmentError):
            self.load({})

    def test_production_manifest_cannot_shadow_a_secret(self):
        write_manifest(self.root, brain={"BRAIN_OPENAI_PROJECT": "project", "BRAIN_OPENAI_API_KEY": "x"})
        with self.assertRaisesRegex(LOCAL.EnvironmentError, "same name as a secret"):
            self.load({"BRAIN_OPENAI_API_KEY": "secret"})

    def test_missing_public_project_is_rejected(self):
        write_manifest(self.root, brain={"BRAIN_OUTPUT": "written"})
        with self.assertRaises(LOCAL.EnvironmentError):
            self.load({"BRAIN_OPENAI_API_KEY": "secret"})

    def test_brain_gets_every_production_setting_except_its_environment(self):
        write_manifest(self.root, brain={"BRAIN_ENVIRONMENT": "production", "BRAIN_OPENAI_PROJECT": "project",
                                         "BRAIN_OUTPUT": "written", "BRAIN_SOMETHING_NEW": "1"})
        self.assertEqual(self.load({"BRAIN_OPENAI_API_KEY": "secret"}), {
            "BRAIN_ENVIRONMENT": "development", "BRAIN_OPENAI_PROJECT": "project",
            "BRAIN_OUTPUT": "written", "BRAIN_SOMETHING_NEW": "1", "BRAIN_OPENAI_API_KEY": "secret"})

    def test_laptop_cannot_quietly_change_a_production_setting(self):
        self.config["brain"]["settings"]["BRAIN_OUTPUT"] = "text"
        with self.assertRaisesRegex(LOCAL.EnvironmentError, "environment-sync.json"):
            self.load({"BRAIN_OPENAI_API_KEY": "secret"})

    def test_missing_infra_checkout_stops_instead_of_using_defaults(self):
        (self.root / MANIFEST).unlink()
        with self.assertRaisesRegex(LOCAL.EnvironmentError, "rockygpt-infra"):
            self.load({"BRAIN_OPENAI_API_KEY": "secret"})

    def test_shared_source_cannot_replace_local_database(self):
        self.config["brain"]["sources"].insert(0, {"path": "brain/.env", "keys": ["DATABASE_URL"]})
        (self.root / "config/local-environments.json").write_text(json.dumps(self.config))
        with patch.object(LOCAL, "dotenv_values", side_effect=[
            {"DATABASE_URL": "local-db", "BRAIN_OPENAI_API_KEY": "obsolete"},
            {"DATABASE_URL": "production-db", "BRAIN_OPENAI_API_KEY": "shared-key"},
        ]):
            result = LOCAL.load_environment("brain", self.root)
        self.assertEqual(result["DATABASE_URL"], "local-db")
        self.assertEqual(result["BRAIN_OPENAI_API_KEY"], "shared-key")

    def test_duplicate_source_mapping_is_rejected(self):
        self.config["brain"]["sources"].append({"path": "other", "keys": ["BRAIN_OPENAI_API_KEY"]})
        with self.assertRaises(LOCAL.EnvironmentError):
            self.load({"BRAIN_OPENAI_API_KEY": "secret"})

    def test_one_environment_selects_local_database_and_excludes_production_secrets(self):
        self.config["brain"]["sources"] = [{"path": "all.env", "keys": {
            "DATABASE_URL": "LOCAL_DATABASE_URL", "BRAIN_OPENAI_API_KEY": "BRAIN_OPENAI_API_KEY"}}]
        result = self.load({"LOCAL_DATABASE_URL": "local-db", "PRODUCTION_DATABASE_URL": "production-db",
                            "BRAIN_OPENAI_API_KEY": "shared-key", "RENDER_API_KEY": "hosting-token",
                            "PRODUCTION_SERVICE_TOKEN": "production-token"})
        self.assertEqual(result["DATABASE_URL"], "local-db")
        self.assertEqual(result["BRAIN_OPENAI_API_KEY"], "shared-key")
        self.assertFalse({"PRODUCTION_DATABASE_URL", "RENDER_API_KEY", "PRODUCTION_SERVICE_TOKEN"} & result.keys())

    def test_missing_local_database_never_falls_back_to_production(self):
        self.config["brain"]["sources"] = [{"path": "all.env", "keys": {"DATABASE_URL": "LOCAL_DATABASE_URL"}}]
        with self.assertRaises(LOCAL.EnvironmentError):
            self.load({"DATABASE_URL": "wrong-db", "PRODUCTION_DATABASE_URL": "production-db"})

    def test_production_dev_ui_receives_only_its_token_and_address(self):
        self.config["dev-production"] = {"directory": "dev", "settings": {},
            "production_settings": {"file": MANIFEST, "target": "ui-production"},
            "sources": [{"path": "all.env", "keys": {"SERVICE_TOKEN": "PRODUCTION_SERVICE_TOKEN"}}]}
        (self.root / "config/local-environments.json").write_text(json.dumps(self.config))
        with patch.object(LOCAL, "dotenv_values", return_value={"PRODUCTION_SERVICE_TOKEN": "token",
                                                               "PRODUCTION_LEDGER_DATABASE_URL": "ledger"}):
            self.assertEqual(LOCAL.load_environment("dev-production", self.root),
                             {"BRAIN_URL": "https://brain.example", "SERVICE_TOKEN": "token"})


class LocalFileTests(unittest.TestCase):
    """The owner-only local file replaces 1Password prompts for the Brain."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "config").mkdir()
        (self.root / "brain").mkdir()
        write_manifest(self.root)
        (self.root / "config/local-environments.json").write_text(json.dumps({"brain": {
            "directory": "brain", "local_file": "brain/.env.local", "production_settings": PRODUCTION,
            "settings": {"BRAIN_ENVIRONMENT": "development"},
            "sources": [{"path": "brain/.env", "keys": ["DATABASE_URL"]},
                        {"path": ".env.shared", "keys": ["BRAIN_OPENAI_API_KEY"]}]}}))
        self.local = self.root / "brain/.env.local"

    def mount(self, path, text):
        (self.root / path).write_text(text)

    def test_local_file_is_used_without_reading_1password(self):
        self.local.write_text("DATABASE_URL='local-db'\nBRAIN_OPENAI_API_KEY='key'\n")
        self.local.chmod(0o600)
        with patch.object(LOCAL, "read_mounts", side_effect=AssertionError("read 1Password")):
            result = LOCAL.load_environment("brain", self.root)
        self.assertEqual(result["DATABASE_URL"], "local-db")
        self.assertEqual(result["BRAIN_OPENAI_API_KEY"], "key")

    def test_local_file_readable_by_others_is_rejected(self):
        self.local.write_text("DATABASE_URL='local-db'\nBRAIN_OPENAI_API_KEY='key'\n")
        self.local.chmod(0o644)
        with self.assertRaisesRegex(LOCAL.EnvironmentError, "chmod 600"):
            LOCAL.load_environment("brain", self.root)

    def test_incomplete_local_file_stops_without_exposing_values(self):
        self.local.write_text("DATABASE_URL='do-not-print'\n")
        self.local.chmod(0o600)
        with self.assertRaises(LOCAL.EnvironmentError) as error:
            LOCAL.load_environment("brain", self.root)
        self.assertNotIn("do-not-print", str(error.exception))
        self.assertIn("--seed", str(error.exception))

    def test_seed_writes_only_assigned_keys_owner_only(self):
        tricky = "user=brain password=it's\\ok dbname=dev host=127.0.0.1"
        self.mount("brain/.env", f'DATABASE_URL="{tricky}"\nADMIN_API_TOKEN=unused\n')
        self.mount(".env.shared", "BRAIN_OPENAI_API_KEY=shared-key\nDATABASE_URL=production-db\n")
        local, changed = LOCAL.seed_local_file("brain", self.root)
        self.assertEqual((local, changed), ("brain/.env.local", ["DATABASE_URL", "BRAIN_OPENAI_API_KEY"]))
        self.assertEqual(self.local.stat().st_mode & 0o777, 0o600)
        text = self.local.read_text()
        self.assertNotIn("production-db", text)
        self.assertNotIn("ADMIN_API_TOKEN", text)
        self.assertEqual(LOCAL.load_environment("brain", self.root)["DATABASE_URL"], tricky)
        self.assertEqual(LOCAL.seed_local_file("brain", self.root)[1], [])

    def test_seed_refuses_a_path_git_would_commit(self):
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)
        self.mount("brain/.env", "DATABASE_URL=local-db\n")
        self.mount(".env.shared", "BRAIN_OPENAI_API_KEY=key\n")
        with self.assertRaisesRegex(LOCAL.EnvironmentError, "gitignored"):
            LOCAL.seed_local_file("brain", self.root)
        self.assertFalse(self.local.exists())

    def test_seed_never_replaces_a_1password_mount(self):
        os.mkfifo(self.local)
        with self.assertRaisesRegex(LOCAL.EnvironmentError, "not a regular file"):
            LOCAL.seed_local_file("brain", self.root)
