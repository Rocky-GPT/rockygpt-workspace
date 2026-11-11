"""Print a public Brain JSON response without assuming internal stages."""

import json
import sys


def main():
    payload = json.load(sys.stdin)
    if "--raw" in sys.argv or not isinstance(payload, dict) or "answer" not in payload:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return

    metadata = [payload.get("status"), payload.get("model"), payload.get("requestId")]
    print(" · ".join(str(value) for value in metadata if value))
    print(payload["answer"])
    for citation in payload.get("citations") or []:
        if isinstance(citation, dict) and citation.get("url"):
            print(f"  Source: {citation.get('title') or citation['url']} — {citation['url']}")
    line = card_line(payload)
    if line:
        print(line)


# Why a question was not answered from an answer card, as a development Brain's trace says it.
CARD_REASONS = {
    "not_clear": "no one card clearly matches the question",
    "needs_look": "the matching card needs a look first",
    "date_changed": "the matching card's date passed after the cards were built",
    "no_steps": "the matching card has no steps",
    "too_long": "the matching card is a list of more than 12 lines",
    "no_page": "the matching card's page has no address",
    "check": "the card's answer held something its facts do not",
    "unreadable": "the matching card's page could not be read",
    "no_cards": "this release has no answer cards",
}


def card_line(payload):
    """What the answer cards did for this reply, when a development Brain was asked to use them
    (its trace's answerCard); nothing otherwise."""
    metrics = payload.get("metrics")
    note = metrics.get("answerCard") if isinstance(metrics, dict) else None
    if not isinstance(note, dict):
        return None
    best = ""
    if note.get("card"):
        task = f"\"{note['task']}\", " if note.get("task") else ""
        best = f" Best card: {task}score {note.get('score')}, lead {note.get('lead')}."
    if note.get("said"):
        return f"  Answer card: code answered from a card, with no AI call.{best}"
    why = CARD_REASONS.get(note.get("why"), note.get("why") or "not said")
    return f"  Answer card: not used ({why}).{best}"


if __name__ == "__main__":
    main()
