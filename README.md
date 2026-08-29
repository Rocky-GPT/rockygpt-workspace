# RockyGPT

The workspace root: the tooling that spans the services, and nothing else.

Each service is its own repository, cloned as a sibling directory here and
ignored by this one. What lives here is the handful of things that only make
sense across all of them — bringing the stack up, and driving it from a
terminal.

## The stack

```
Student UI :3000 ──→ Brain :8000 ──→ Neon
Dev UI     :3100 ──→ Brain :8000 ──→ Neon
Data                 ingestion only ──→ Neon
```

Two front-end products over one backend. `rockygpt-ui` is only what a student
should ever see; `rockygpt-dev` is everything needed to understand, debug, test
and operate the thing. Neither holds campus data, and neither connects to the
database — every fact arrives over HTTP from the brain.

## Getting the services

    git clone git@github.com:Rocky-GPT/rockygpt-ui.git
    git clone git@github.com:Rocky-GPT/rockygpt-brain.git
    git clone git@github.com:Rocky-GPT/rockygpt-data.git
    git clone git@github.com:Rocky-GPT/rockygpt-evals.git
    git clone git@github.com:Rocky-GPT/rockygpt-infra.git
    # rockygpt-dev has no remote yet

Each needs its own `.env`; see the `.env.example` in each repository.

## Running the stack

    ./run-local.sh start          # brain :8000, student ui :3000, dev ui :3100
    ./run-local.sh status         # what is up, and whether it is ready
    ./run-local.sh logs brain     # or `ui`, or `dev`
    ./run-local.sh stop

`start` clears ports 3000, 3100 and 8000 first, then waits for each service to
answer. It reads the brain's `.env` for `ADMIN_API_TOKEN` and exports it to the
dev UI, so the two sides always match — the most common cause of an empty logs
dashboard is starting that app by hand instead.

## Asking from a terminal

    ./rocky ask "when is the next shuttle"      # print the six stages
    ./rocky ask "..." --raw                     # print the whole turn
    ./rocky bulk short [delayMs]                # run a sample set
    ./rocky bulk full  [delayMs]                # run the capability suite
    ./rocky bulk file <path> [delayMs]          # one question per line

Goes through `rockygpt-dev`, which proxies the brain and stamps each turn `dev`
so it stays out of the student rows in the logs dashboard. `rocky-format.py`
does the printing; `rocky` does not work without it.

This used to drive an open browser tab through the student app's `/api/remote`,
so that a command ran through the page rather than around it. That page no
longer carries dev tooling, and the dev app has its own bulk runner and
inspector, so the round trip bought nothing but a "no chat page is listening"
failure mode.

## What is deliberately not here

No service source, no `.env`, and no deployment configuration — deployment
lives in `rockygpt-infra`. If a change belongs to one service, it belongs in
that service's repository.
