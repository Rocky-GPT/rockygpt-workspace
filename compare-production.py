#!/usr/bin/env python3
"""Ask the laptop Brain and the production Brain the same questions and list what differs.

    rockygpt-brain/.venv/bin/python compare-production.py            # config/compare-questions.txt
    rockygpt-brain/.venv/bin/python compare-production.py --limit 3
    rockygpt-brain/.venv/bin/python compare-production.py --questions my-list.txt

Each question is asked once on each side, at the same time. A turn costs a few cents on each
side (production's spend goes to production's ledger), so the default list is ten questions.

What is compared, because it should match exactly when code, data and settings match:
  - the answer status (complete, partial, not_found, ...)
  - the published dataset version the answer was read from
  - the fact packet (the facts the code worked out), ignoring the clock fields
  - the links the answer cites
The written wording is shown but not judged: the writer model can phrase the same facts
differently from run to run. A facts mismatch can also be the model choosing a different lookup;
ask that one question again before calling it a gap.

The production token comes from 1Password through local-env.py (the dev-production service);
the laptop Brain is the one run-local.sh starts. A report is saved under .local-logs/.
"""

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent
# Fields that hold the turn's own clock or id, which differ between any two turns.
VOLATILE = {"asOf", "now", "requestId", "freshness"}
TOKEN_HEADER = "x-rockygpt-environment-token"


def read_questions(path, limit):
    questions = [line.strip() for line in Path(path).read_text().splitlines()
                 if line.strip() and not line.lstrip().startswith("#")]
    if not questions:
        raise SystemExit(f"{path} has no questions.")
    return questions[:limit] if limit else questions


def production_target(root=ROOT):
    """Production's Brain URL and service token, read the way the production-connected dev UI is."""
    spec = importlib.util.spec_from_file_location("local_env", root / "local-env.py")
    launcher = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(launcher)
    values = launcher.load_environment("dev-production", root)
    return values["BRAIN_URL"].rstrip("/"), values["STAGING_SERVICE_TOKEN"]


def ask(url, question, token=None, timeout=90):
    headers = {"Content-Type": "application/json", "User-Agent": "RockyGPT-compare/1.0"}
    if token:
        headers[TOKEN_HEADER] = token
    body = json.dumps({"messages": [{"role": "user", "content": question}]}).encode()
    started = time.monotonic()
    try:
        with urlopen(Request(url + "/v1/chat", data=body, headers=headers, method="POST"),
                     timeout=timeout) as response:
            reply = json.loads(response.read())
    except HTTPError as error:
        code = error.code
        try:
            reply = json.loads(error.read() or b"{}")
        except ValueError:
            reply = {}
        error.close()
        reply = {"status": f"http_{code}", **{k: v for k, v in reply.items() if k != "status"}}
    except (URLError, TimeoutError, ValueError) as error:
        reply = {"status": "unreachable", "error": type(error).__name__}
    reply["_seconds"] = round(time.monotonic() - started, 1)
    return reply


def strip_volatile(value):
    if isinstance(value, dict):
        return {k: strip_volatile(v) for k, v in value.items() if k not in VOLATILE}
    if isinstance(value, list):
        return [strip_volatile(v) for v in value]
    return value


def first_difference(a, b, path="facts"):
    """The first place two JSON values differ, as a readable path."""
    if type(a) is not type(b):
        return path
    if isinstance(a, dict):
        for key in sorted(set(a) | set(b)):
            if key not in a or key not in b:
                return f"{path}.{key}"
            found = first_difference(a[key], b[key], f"{path}.{key}")
            if found:
                return found
        return None
    if isinstance(a, list):
        if len(a) != len(b):
            return f"{path} (length {len(a)} vs {len(b)})"
        for index, (x, y) in enumerate(zip(a, b)):
            found = first_difference(x, y, f"{path}[{index}]")
            if found:
                return found
        return None
    return None if a == b else path


def cited_urls(reply):
    urls = set()
    for citation in reply.get("citations") or []:
        if isinstance(citation, dict):
            for key in ("url", "urls"):
                value = citation.get(key)
                urls.update(value if isinstance(value, list) else [value] if value else [])
    return sorted(urls)


def compare(laptop, production):
    """Mismatches between two replies to the same question, most telling first."""
    found = []
    if laptop.get("status") != production.get("status"):
        found.append(f"status: laptop {laptop.get('status')}, production {production.get('status')}")
    if laptop.get("datasetVersion") != production.get("datasetVersion"):
        found.append(f"data: laptop {laptop.get('datasetVersion')}, "
                     f"production {production.get('datasetVersion')}")
    facts = first_difference(strip_volatile(laptop.get("facts")), strip_volatile(production.get("facts")))
    if facts:
        found.append(f"facts differ at {facts}")
    if cited_urls(laptop) != cited_urls(production):
        only_laptop = sorted(set(cited_urls(laptop)) - set(cited_urls(production)))
        only_production = sorted(set(cited_urls(production)) - set(cited_urls(laptop)))
        found.append(f"links: laptop only {only_laptop or '-'}, production only {only_production or '-'}")
    return found


def report(rows):
    lines = [f"# Laptop vs production, {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC", ""]
    same = sum(1 for row in rows if not row["mismatches"])
    lines += [f"{same} of {len(rows)} questions matched.", ""]
    for number, row in enumerate(rows, 1):
        verdict = "same" if not row["mismatches"] else "DIFFERENT"
        lines += [f"## {number}. {row['question']} ({verdict})", ""]
        lines += [f"- {m}" for m in row["mismatches"]]
        for side in ("laptop", "production"):
            reply = row[side]
            text = (reply.get("answer") or reply.get("error") or reply.get("message") or "").strip()
            lines += ["", f"**{side}** ({reply.get('status')}, {reply['_seconds']} s):", "",
                      "> " + text.replace("\n", "\n> ") if text else "> (no answer text)"]
        lines.append("")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Compare laptop and production answers.")
    parser.add_argument("--questions", default=str(ROOT / "config/compare-questions.txt"))
    parser.add_argument("--limit", type=int, default=0, help="ask only the first N questions")
    parser.add_argument("--local", default="http://127.0.0.1:8000", help="the laptop Brain")
    args = parser.parse_args()
    questions = read_questions(args.questions, args.limit)
    production_url, token = production_target()
    local = args.local.rstrip("/")
    print(f"Asking {len(questions)} questions on the laptop ({local}) and production ({production_url}).")
    rows = []
    with ThreadPoolExecutor(max_workers=2) as pool:
        for question in questions:
            laptop_future = pool.submit(ask, local, question)
            production_future = pool.submit(ask, production_url, question, token)
            laptop, production = laptop_future.result(), production_future.result()
            mismatches = compare(laptop, production)
            rows.append({"question": question, "laptop": laptop, "production": production,
                         "mismatches": mismatches})
            print(("  same       " if not mismatches else "  DIFFERENT  ") + question)
            for mismatch in mismatches:
                print("               " + mismatch)
    logs = ROOT / ".local-logs"
    logs.mkdir(exist_ok=True)
    path = logs / f"compare-{datetime.now(timezone.utc):%Y%m%d-%H%M%S}.md"
    path.write_text(report(rows))
    same = sum(1 for row in rows if not row["mismatches"])
    print(f"\n{same} of {len(rows)} matched. Full answers: {path.relative_to(ROOT)}")
    return 0 if same == len(rows) else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(130)
