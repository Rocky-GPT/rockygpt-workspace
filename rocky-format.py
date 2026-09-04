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


if __name__ == "__main__":
    main()
