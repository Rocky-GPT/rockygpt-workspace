#!/usr/bin/env python3
"""Run a local service command with repository settings and 1Password secrets.

Use the Brain virtualenv's Python. --snapshot is an internal launcher interface;
its output contains secrets and must only be consumed by another process.
"""

import argparse
import json
import os
from pathlib import Path
import sys
import time

from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parent
PUBLIC_SETTINGS = {"BRAIN_ENVIRONMENT", "BRAIN_OPENAI_PROJECT", "BRAIN_ROUTING_MODE", "BRAIN_ROUTING_PROVIDER"}


class EnvironmentError(Exception):
    """Safe diagnostic with no environment values."""


def load_environment(service, root=ROOT):
    config = json.loads((root / "config/local-environments.json").read_text())[service]
    settings, sources = config["settings"], config["sources"]
    keys = [key for source in sources for key in source["keys"]]
    if set(settings) - PUBLIC_SETTINGS or set(settings) & set(keys):
        raise EnvironmentError("Local settings contain an unapproved or conflicting variable.")
    if service == "brain" and settings.get("BRAIN_ENVIRONMENT") != "development":
        raise EnvironmentError("The local stack requires BRAIN_ENVIRONMENT=development.")
    if service == "brain" and not settings.get("BRAIN_OPENAI_PROJECT"):
        raise EnvironmentError("The local Brain OpenAI project is not configured.")
    if not keys or len(keys) != len(set(keys)):
        raise EnvironmentError("The local secret list is invalid.")
    if any(not isinstance(value, str) or not value for value in settings.values()):
        raise EnvironmentError("A local setting is missing or empty.")
    values = dict(settings)
    for source in sources:
        for attempt in range(5):
            mounted = dotenv_values(root / source["path"])
            if mounted or attempt == 4:
                break
            time.sleep(0.2)
        if any(not isinstance(mounted.get(key), str) or not mounted[key] for key in source["keys"]):
            raise EnvironmentError("Local secrets are incomplete. Open 1Password and authorize its .env mount.")
        # Select from each source independently: a shared DATABASE_URL must
        # never replace the local Brain database from its own source.
        values.update({key: mounted[key] for key in source["keys"]})
    return values


def main():
    parser = argparse.ArgumentParser(description="Run a Brain or data command using local 1Password secrets.")
    parser.add_argument("--snapshot", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("service", choices=["brain", "data"])
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    values = load_environment(args.service)
    if args.snapshot:
        print(json.dumps(values))
        return
    command = args.command
    if command[:1] == ["--"]:
        command = command[1:]
    if not command:
        parser.error("provide a command after the service name")
    config = json.loads((ROOT / "config/local-environments.json").read_text())[args.service]
    os.chdir(ROOT / config["directory"])
    os.environ.update(values)
    if args.service == "brain":
        for key in ("STAGING_SERVICE_TOKEN", "OPENAI_CHAT_MODEL", "BRAIN_EXPECTED_CONFIG_HASH"):
            os.environ.pop(key, None)
        os.environ["PYTHON_DOTENV_DISABLED"] = "1"
    os.execvp(command[0], command)


if __name__ == "__main__":
    try:
        main()
    except EnvironmentError as error:
        sys.exit(str(error))
    except (OSError, ValueError, KeyError):
        sys.exit("Local environment setup failed; details withheld to protect secrets.")
