"""Prints one remote `ask` result: the whole turn, or the stages compactly."""

import json
import os
import sys

payload = json.load(sys.stdin).get("value") or {}
turn = payload.get("turn")

if os.environ.get("ROCKY_RAW") == "--raw":
    print(json.dumps(turn or payload, indent=2))
    raise SystemExit

if not turn:
    if payload.get("stopped"):
        answer = (payload.get("answer") or "").strip()
        print("  STOPPED   from the UI" + (f" — partial: {answer[:120]}" if answer else ""))
    else:
        print(payload.get("error") or "no turn — it failed, or the tab is not in Dev View")
    raise SystemExit


def show(label: str, value: object, limit: int = 300) -> None:
    if not value:
        return
    text = value if isinstance(value, str) else json.dumps(value)
    print(f"  {label:9} {text[:limit]}")


show("QUESTION", turn["question"].get("question"))
show("CONTEXT", turn.get("context"))
show("BRAIN #1", turn.get("understanding"))
show("BRAIN #2", turn.get("plan"))
show("PYTHON", turn.get("execution"))
show("BRAIN #3", turn["answer"].get("answer"), 400)
