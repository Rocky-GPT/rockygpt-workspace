#!/usr/bin/env python3
"""Run a local service command with production's public settings and local secrets.

Use the Brain virtualenv's Python. A service whose config names a `local_file`
reads its secrets from that owner-only, gitignored file, so unattended runs
never wait on a 1Password prompt; `--seed` copies them there from the 1Password
mounts. Other services read the mounts directly.

--snapshot is an internal launcher interface; its output contains secrets and
must only be consumed by another process.
"""

import argparse
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import time

from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parent
# Public settings come from production's manifest (rockygpt-infra/config/environment-sync.json),
# so the laptop and production cannot drift apart. These are the only names the laptop may
# change, each on purpose: the local Brain must run as development.
LOCAL_OVERRIDES = {"BRAIN_ENVIRONMENT"}
# Production's Brain follows the shared release graph in the file store by itself. The laptop's
# copy changes only when Dan syncs it (service `graph-sync`, pull-production-graph.py), so the
# laptop Brain gets no store settings and serves the folder run-local.sh names.
BRAIN_ONLY_IN_PRODUCTION = ("BRAIN_GRAPH_ONLY_DIR", "BRAIN_GRAPH_STORE_")


class EnvironmentError(Exception):
    """Safe diagnostic with no environment values."""


def source_mapping(source):
    """Map each service variable to its explicitly named 1Password variable."""
    keys = source["keys"]
    if isinstance(keys, list):
        if len(keys) != len(set(keys)):
            raise EnvironmentError("Duplicate local secret mapping.")
        keys = {key: key for key in keys}
    if not isinstance(keys, dict) or not keys or any(
        not isinstance(key, str) or not re.fullmatch(r"[A-Z][A-Z0-9_]*", key)
        for key in [*keys, *keys.values()]
    ):
        raise EnvironmentError("Invalid local secret mapping.")
    return keys


def production_settings(root, reference):
    """The public settings production runs with, read from rockygpt-infra's sync manifest."""
    if not reference:
        return {}
    path = root / reference["file"]
    try:
        targets = json.loads(path.read_text())["targets"]
    except FileNotFoundError:
        raise EnvironmentError(f"{reference['file']} is missing; clone rockygpt-infra beside this "
                               "workspace so the laptop uses production's settings.") from None
    except (ValueError, KeyError, TypeError):
        raise EnvironmentError(f"{reference['file']} could not be read.") from None
    matches = [t for t in targets if isinstance(t, dict) and t.get("name") == reference["target"]]
    settings = matches[0].get("settings") if len(matches) == 1 else None
    if not isinstance(settings, dict) or not settings or any(
        not isinstance(key, str) or not re.fullmatch(r"[A-Z][A-Z0-9_]*", key)
        or not isinstance(value, str) or not value for key, value in settings.items()
    ):
        raise EnvironmentError(f"Production settings for {reference['target']} are missing or invalid.")
    return settings


def service_config(service, root=ROOT):
    config = json.loads((root / "config/local-environments.json").read_text())[service]
    overrides, sources = config["settings"], config["sources"]
    keys = [key for source in sources for key in source_mapping(source)]
    if set(overrides) - LOCAL_OVERRIDES:
        raise EnvironmentError("Local settings may only override " + ", ".join(sorted(LOCAL_OVERRIDES))
                               + "; put shared settings in rockygpt-infra/config/environment-sync.json.")
    settings = production_settings(root, config.get("production_settings")) | overrides
    if service == "brain":
        settings = {key: value for key, value in settings.items()
                    if not key.startswith(BRAIN_ONLY_IN_PRODUCTION)}
    if set(settings) & set(keys):
        raise EnvironmentError("A public setting has the same name as a secret.")
    if service == "brain" and settings.get("BRAIN_ENVIRONMENT") != "development":
        raise EnvironmentError("The local stack requires BRAIN_ENVIRONMENT=development.")
    if service == "brain" and not settings.get("BRAIN_OPENAI_PROJECT"):
        raise EnvironmentError("The local Brain OpenAI project is not configured.")
    if not keys or len(keys) != len(set(keys)):
        raise EnvironmentError("The local secret list is invalid.")
    if any(not isinstance(value, str) or not value for value in settings.values()):
        raise EnvironmentError("A local setting is missing or empty.")
    return config | {"settings": settings}, keys


def read_mounts(root, sources):
    values = {}
    for source in sources:
        mapping = source_mapping(source)
        for attempt in range(5):
            mounted = dotenv_values(root / Path(source["path"]).expanduser(), interpolate=False)
            if mounted or attempt == 4:
                break
            time.sleep(0.2)
        if any(not isinstance(mounted.get(key), str) or not mounted[key] for key in mapping.values()):
            raise EnvironmentError("Local secrets are incomplete. Open 1Password and authorize its .env mount.")
        values.update({destination: mounted[key] for destination, key in mapping.items()})
    return values


def read_local_file(path, name, keys):
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
        raise EnvironmentError(f"{name} must be a regular file readable only by you (chmod 600).")
    stored = dotenv_values(path, interpolate=False)
    if any(not isinstance(stored.get(key), str) or not stored[key] for key in keys):
        raise EnvironmentError(f"{name} is incomplete. Run local-env.py --seed with 1Password unlocked.")
    return {key: stored[key] for key in keys}


def load_environment(service, root=ROOT):
    config, keys = service_config(service, root)
    values = dict(config["settings"])
    local = config.get("local_file")
    if local and os.path.lexists(root / local):
        values.update(read_local_file(root / local, local, keys))
    else:
        values.update(read_mounts(root, config["sources"]))
    return values


def gitignored(path, root):
    # Both the service repository and this workspace must ignore the file;
    # 128 means the directory is not in a repository, so nothing can commit it.
    for repository, name in ((path.parent, path.name), (root, path.relative_to(root))):
        result = subprocess.run(["git", "-C", str(repository), "check-ignore", "-q", str(name)],
                                capture_output=True)
        if result.returncode not in (0, 128):
            return False
    return True


def quoted(value):
    return "'" + value.replace("\\", "\\\\").replace("'", "\\'") + "'"


def seed_local_file(service, root=ROOT):
    """Copy the service's assigned secrets from 1Password into its local file."""
    config, keys = service_config(service, root)
    local = config.get("local_file")
    if not local:
        raise EnvironmentError(f"The {service} service reads 1Password directly and has no local file.")
    path = root / local
    if os.path.lexists(path) and not stat.S_ISREG(path.lstat().st_mode):
        raise EnvironmentError(f"{local} exists and is not a regular file; it was left unchanged.")
    if not gitignored(path, root):
        raise EnvironmentError(f"{local} is not gitignored; no secrets were written.")
    values = read_mounts(root, config["sources"])
    previous = dotenv_values(path, interpolate=False) if path.exists() else {}
    temporary = path.with_name(path.name + ".tmp")
    temporary.unlink(missing_ok=True)
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w") as handle:
        handle.write(f"# Copied from 1Password by local-env.py --seed {service}. Owner-only; never commit.\n")
        handle.writelines(f"{key}={quoted(values[key])}\n" for key in keys)
    if dotenv_values(temporary, interpolate=False) != {key: values[key] for key in keys}:
        temporary.unlink()
        raise EnvironmentError("A secret did not survive the round trip; nothing was replaced.")
    os.replace(temporary, path)
    return local, [key for key in keys if previous.get(key) != values[key]]


def main():
    parser = argparse.ArgumentParser(description="Run a service with its assigned RockyGPT secrets.")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--snapshot", action="store_true", help=argparse.SUPPRESS)
    mode.add_argument("--seed", action="store_true",
                      help="copy the service's secrets from 1Password into its local file, then exit")
    parser.add_argument("service", choices=["brain", "data", "dev-production", "graph-sync"])
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    if args.seed:
        local, changed = seed_local_file(args.service)
        print(f"Saved {args.service} secrets to {local} (owner-only). "
              + (f"Changed: {', '.join(changed)}." if changed else "No values changed."))
        return
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
        for key in ("SERVICE_TOKEN", "STAGING_SERVICE_TOKEN", "OPENAI_CHAT_MODEL", "BRAIN_EXPECTED_CONFIG_HASH"):
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
