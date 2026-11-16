#!/usr/bin/env python3
"""Counts from a saved test run's own records. Free: it asks nothing, it only reads the file.

  python3 rocky-run-counts.py run.json [--good good.json]

run.json is either what `rocky bulk ... --brain PORT --out run.json` saved (a `--brain` run
carries each answer's trace) or a Repeat Test export from the dev UI. good.json is optional: a
JSON object {question id: true or false} saying whether that question's FIRST try was graded
good; with it, each count of first tries also says how many were good.

It prints numbers and question ids only, never a question or an answer, so it is safe to run on
the frozen blind set. What it counts:

- the run: answers, failures, cost, time and model calls per answer;
- who wrote each answer: an answer card, other code, the read alone, the two-stage page answer,
  the one-writer page answer, or the tool loop;
- the answer cards: how often one was said, and why not;
- the three votes of the read and of each pick: how often one vote alone gives what the three
  decided, and whether the three are steadier than one from try to try of the same question.
"""

import argparse
import collections
import itertools
import json
import statistics
import sys
from pathlib import Path

AREAS = {"pp": "people", "ec": "events and clubs", "ac": "academics", "ht": "how-to"}
PATHS = ("answer card", "other code", "the read alone", "two-stage page answer",
         "one-writer page answer", "tool loop", "failed")


def load(path):
    """Every try as {id, run, seconds, body}, from either file shape."""
    data = json.loads(Path(path).read_text())
    tries = []
    if isinstance(data, dict) and isinstance(data.get("rows"), list):  # a Repeat Test export
        for row in data["rows"]:
            for run, one in enumerate(row.get("tries") or [], start=1):
                if isinstance(one, dict):
                    tries.append({"id": str(row.get("id")), "run": run, "seconds": one.get("seconds"),
                                  "body": one.get("raw") if isinstance(one.get("raw"), dict) else {}})
    elif isinstance(data, list):  # rocky bulk --out rows
        for row in data:
            tries.append({"id": str(row.get("id")), "run": int(row.get("run") or 1),
                          "seconds": row.get("seconds"),
                          "body": row.get("body") if isinstance(row.get("body"), dict) else {}})
    else:
        raise SystemExit("not a rocky bulk file or a Repeat Test export")
    for one in tries:
        metrics = one["body"].get("metrics")
        one["metrics"] = metrics if isinstance(metrics, dict) else {}
    return tries


def area_of(question_id):
    return AREAS.get(question_id.split("-")[0])


def path_of(one):
    """Who wrote a try's answer, from its trace."""
    metrics, body = one["metrics"], one["body"]
    decided = metrics.get("decidedBy")
    if not body.get("status") or decided in (None, "error"):
        return "failed"
    card = metrics.get("answerCard")
    if isinstance(card, dict) and card.get("said"):
        return "answer card"
    if decided == "code":
        return "other code"
    if decided == "one_call":
        facts = metrics.get("pageFacts")
        return ("two-stage page answer" if isinstance(facts, dict) and facts.get("writer")
                else "one-writer page answer")
    if decided == "model":
        return "tool loop"
    return "the read alone"  # read, phrase_floor, safety_fallback: a fixed or code-chosen reply


def share(count, total):
    return f"{count} of {total}" + (f" ({100 * count / total:.0f}%)" if total else "")


def labels(reading):
    """A read's labels, without its wording of the question."""
    return (reading.get("social"), reading.get("danger"), reading.get("limit"),
            tuple(sorted(reading.get("needs") or [])))


def read_votes(tries, out):
    voted = []
    for one in tries:
        read = one["metrics"].get("read")
        votes = read.get("reads") if isinstance(read, dict) else None
        if isinstance(votes, list) and len(votes) >= 2 and all(isinstance(v, dict) for v in votes):
            voted.append((one, read, votes))
    out("\nTHE READ'S VOTES (what kind of message is this?)")
    counts = collections.Counter(len(votes) for _, _, votes in voted)
    out(f"  tries with two or more votes back: {len(voted)} of {len(tries)}  "
        f"(by votes back: {dict(sorted(counts.items()))})")
    if not voted:
        return
    total = len(voted)
    same = sum(len({labels(v) for v in votes}) == 1 for _, _, votes in voted)
    first = sum(labels(votes[0]) == labels(read) for _, read, votes in voted)
    every = sum(labels(v) == labels(read) for _, read, votes in voted for v in votes)
    ballots = sum(len(votes) for _, _, votes in voted)
    out(f"  all votes gave the same labels: {share(same, total)}")
    out(f"  the first vote alone gave what was decided: {share(first, total)}")
    out(f"  any one vote gave what was decided: {share(every, ballots)} votes")
    for place, name in enumerate(("social", "danger", "limit", "needs")):
        split = sum(len({labels(v)[place] for v in votes}) > 1 for _, _, votes in voted)
        out(f"    votes split on {name}: {share(split, total)}")
    partly = sum(0 < sum(v.get("danger") not in (None, "none") for v in votes) < len(votes)
                 for _, _, votes in voted)
    out(f"  a danger only some votes found (the rule keeps it; one vote could miss it): "
        f"{share(partly, total)}")
    wording = sum(len({v.get("question") for v in votes}) == 1 for _, _, votes in voted)
    out(f"  all votes worded the question the same: {share(wording, total)}")
    by_question = collections.defaultdict(list)
    for one, read, votes in voted:
        by_question[one["id"]].append((labels(read), labels(votes[0])))
    several = {q: pairs for q, pairs in by_question.items() if len(pairs) >= 2}
    steady = sum(len({decided for decided, _ in pairs}) == 1 for pairs in several.values())
    alone = sum(len({vote for _, vote in pairs}) == 1 for pairs in several.values())
    out(f"  questions read the same on every try: {share(steady, len(several))} with the votes, "
        f"{share(alone, len(several))} with the first vote alone")


def agreed(votes):
    """The numbers more than half the votes that came back chose (the Brain's own rule)."""
    valid = [set(v) for v in votes if isinstance(v, list)]
    counts = collections.Counter(n for chosen in valid for n in chosen)
    return valid, {n for n, count in counts.items() if count > len(valid) // 2}


def jaccard(a, b):
    return len(a & b) / len(a | b) if a | b else 1.0


def pick_votes(tries, key, name, across_tries, out):
    out(f"\nTHE PICK'S VOTES: {name} (trace key {key})")
    voted = []
    for one in tries:
        votes = one["metrics"].get(key)
        if isinstance(votes, list):
            valid, kept = agreed(votes)
            voted.append((one, votes, valid, kept))
    if not voted:
        out("  no try has it")
        return
    back = collections.Counter(len(valid) for _, _, valid, _ in voted)
    late = sum(v == "late" for _, votes, _, _ in voted for v in votes)
    failed = sum(v is None for _, votes, _, _ in voted for v in votes)
    out(f"  tries with a pick step: {len(voted)} of {len(tries)}  (by votes back: "
        f"{dict(sorted(back.items()))}; late votes {late}, failed votes {failed})")
    full = [(one, valid, kept) for one, _, valid, kept in voted if len(valid) >= 2]
    if not full:
        return
    total = len(full)
    same = sum(all(chosen == valid[0] for chosen in valid) for _, valid, _ in full)
    first = sum(valid[0] == kept for _, valid, kept in full)
    ballots = [chosen for _, valid, _ in full for chosen in valid]
    every = sum(chosen == kept for _, valid, kept in full for chosen in valid)
    near = statistics.mean(jaccard(valid[0], kept) for _, valid, kept in full)
    out(f"  all votes chose the same set: {share(same, total)}")
    out(f"  the first vote alone chose the decided set: {share(first, total)}")
    out(f"  any one vote chose the decided set: {share(every, len(ballots))} votes")
    out(f"  how alike the first vote and the decided set are (1 = the same): {near:.2f}")
    out(f"  numbers chosen, on average: one vote {statistics.mean(map(len, ballots)):.1f}, "
        f"decided {statistics.mean(len(kept) for _, _, kept in full):.1f}")
    if not across_tries:
        return
    by_question = collections.defaultdict(list)
    for one, valid, kept in full:
        by_question[one["id"]].append((kept, valid[0]))
    several = {q: sets for q, sets in by_question.items() if len(sets) >= 2}
    if not several:
        return

    def alike(sets):
        return statistics.mean(jaccard(a, b) for a, b in itertools.combinations(sets, 2))
    voted_alike = statistics.mean(alike([kept for kept, _ in sets]) for sets in several.values())
    alone_alike = statistics.mean(alike([vote for _, vote in sets]) for sets in several.values())
    steady = sum(len({frozenset(kept) for kept, _ in sets}) == 1 for sets in several.values())
    alone = sum(len({frozenset(vote) for _, vote in sets}) == 1 for sets in several.values())
    out(f"  from try to try of one question ({len(several)} questions), how alike the sets are: "
        f"{voted_alike:.2f} with the votes, {alone_alike:.2f} with the first vote alone")
    out(f"  questions with the same set on every try: {share(steady, len(several))} with the "
        f"votes, {share(alone, len(several))} with the first vote alone")


def report(tries, good=None, out=print):
    questions = sorted({one["id"] for one in tries})
    for one in tries:
        one["path"] = path_of(one)
    answered = [one for one in tries if one["path"] != "failed"]
    out("THE RUN")
    out(f"  questions {len(questions)}, tries {len(tries)}, failed {len(tries) - len(answered)}")
    spent = sum(int(one["metrics"].get("committedNusd") or 0) for one in tries) / 1e9
    seconds = [float(one["seconds"]) for one in answered if isinstance(one["seconds"], (int, float))]
    calls = [int(one["metrics"].get("modelCalls") or 0) for one in answered]
    if answered:
        out(f"  spent ${spent:.3f} in all, ${spent / len(answered):.4f} an answer")
        out(f"  model calls an answer: {statistics.mean(calls):.1f} on average, "
            f"{statistics.median(calls):g} in the middle")
    if seconds:
        out(f"  seconds an answer: {statistics.median(seconds):.1f} in the middle, "
            f"{sorted(seconds)[int(0.9 * (len(seconds) - 1))]:.1f} at the 90th percentile")
    firsts = [one for one in tries if one["run"] == 1]
    graded = good is not None

    def good_of(some):
        known = [one for one in some if one["id"] in good]
        return f"; good {share(sum(bool(good[one['id']]) for one in known), len(known))}"

    if graded:
        out(f"  first tries graded: {len([one for one in firsts if one['id'] in good])} of "
            f"{len(firsts)}{good_of(firsts)}")
        for area in AREAS.values():
            some = [one for one in firsts if area_of(one["id"]) == area]
            if some:
                out(f"    {area}: {len(some)} first tries{good_of(some)}")

    out("\nWHO WROTE EACH ANSWER")
    for path in PATHS:
        some = [one for one in tries if one["path"] == path]
        if not some:
            continue
        first = [one for one in some if one["run"] == 1]
        line = f"  {path}: {share(len(some), len(tries))} tries; first tries {len(first)}"
        if graded and first:
            line += good_of(first)
        if path != "failed":
            cost = sum(int(one["metrics"].get("committedNusd") or 0) for one in some) / 1e9
            took = [float(one["seconds"]) for one in some if isinstance(one["seconds"], (int, float))]
            line += (f"; ${cost / len(some):.4f} and "
                     f"{statistics.mean(int(one['metrics'].get('modelCalls') or 0) for one in some):.1f}"
                     f" model calls an answer")
            if took:
                line += f", {statistics.median(took):.1f} s in the middle"
        out(line)
    two_stage = [one["metrics"]["pageFacts"] for one in tries if one["path"] == "two-stage page answer"]
    if two_stage:
        writers = collections.Counter(str(facts.get("writer")) for facts in two_stage)
        out(f"  two-stage answers by writer: {dict(writers)}; fell back to the template: "
            f"{sum(bool(facts.get('fell_back')) for facts in two_stage)}")

    out("\nANSWER CARDS")
    asked = [one for one in tries if isinstance(one["metrics"].get("answerCard"), dict)]
    said = [one for one in asked if one["metrics"]["answerCard"].get("said")]
    out(f"  tries that asked the cards: {share(len(asked), len(tries))}; said from a card: "
        f"{share(len(said), len(tries))}")
    if asked:
        why = collections.Counter(str(one["metrics"]["answerCard"].get("why"))
                                  for one in asked if not one["metrics"]["answerCard"].get("said"))
        out(f"  why not: {dict(why.most_common())}")
        per = collections.Counter(one["id"] for one in said)
        runs = collections.Counter(one["id"] for one in tries)
        always = sorted(q for q, count in per.items() if count == runs[q])
        out(f"  questions said from a card on every try: {len(always)}; on some tries only: "
            f"{len(per) - len(always)}")
        first_ids = sorted(one["id"] for one in said if one["run"] == 1)
        out(f"  first tries said from a card ({len(first_ids)}): {', '.join(first_ids) or 'none'}")
        for area in AREAS.values():
            some = [q for q in first_ids if area_of(q) == area]
            if some:
                line = f"    {area}: {len(some)}"
                if graded:
                    line += good_of([one for one in said if one["run"] == 1 and one["id"] in some])
                out(line)
    winners = sum(bool(one["metrics"].get("answerCardWinners")) for one in tries)
    out(f"  page answers that read a page the cards chose: {share(winners, len(tries))}")

    read_votes(tries, out)
    pick_votes(tries, "oneCallPicks", "which sections to read", True, out)
    pick_votes(tries, "pageFactPicks", "which sentences to say (two-stage)", False, out)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("run", type=Path, help="a rocky bulk --out file or a Repeat Test export")
    parser.add_argument("--good", type=Path,
                        help="JSON {question id: true/false}: was the first try graded good")
    args = parser.parse_args(argv)
    good = json.loads(args.good.read_text()) if args.good else None
    if good is not None and not isinstance(good, dict):
        raise SystemExit("--good must be a JSON object of question id to true or false")
    report(load(args.run), good)
    return 0


if __name__ == "__main__":
    sys.exit(main())
