import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location("local_env", Path(__file__).resolve().parents[1] / "local-env.py")
LOCAL = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(LOCAL)


class LocalEnvironmentTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "config").mkdir()
        self.config = {"brain": {"directory": "brain", "settings": {
            "BRAIN_ENVIRONMENT": "development", "BRAIN_OPENAI_PROJECT": "project"},
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

    def test_missing_public_project_is_rejected(self):
        del self.config["brain"]["settings"]["BRAIN_OPENAI_PROJECT"]
        with self.assertRaises(LOCAL.EnvironmentError):
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
