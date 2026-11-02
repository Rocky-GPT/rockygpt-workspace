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

Keep `.env.example` files as configuration templates. 1Password stores active
credentials. Public settings have one home, production's manifest
`rockygpt-infra/config/environment-sync.json`: the local Brain gets every setting
the production Brain gets, and the production-connected dev UI gets the student
UI's `BRAIN_URL`. `config/local-environments.json` points at that manifest and may
override only `BRAIN_ENVIRONMENT` (always `development` locally). A setting added
to production reaches the laptop on its next start; to try a new setting, add it to
the manifest on rockygpt-infra's `dev` branch. Without a rockygpt-infra checkout
beside this workspace the launcher stops rather than guessing.
All project credentials live in one 1Password Environment, **RockyGPT**. Local
and production database connections have explicit names; each launcher maps
only the assigned values into the variable names its service expects.

| Stored variable | Consumers / service variable |
| --- | --- |
| `LOCAL_DATABASE_URL` | Local Brain → `DATABASE_URL` |
| `LOCAL_LEDGER_DATABASE_URL` | Local Brain → `BRAIN_LEDGER_DATABASE_URL` |
| `PRODUCTION_DATABASE_URL` | Data and production Brain → `DATABASE_URL` |
| `PRODUCTION_LEDGER_DATABASE_URL` | Production Brain → `BRAIN_LEDGER_DATABASE_URL` |
| `PRODUCTION_SERVICE_TOKEN` | Production Brain, student UI, production-connected dev UI → `SERVICE_TOKEN` |
| `BRAIN_OPENAI_API_KEY` | Local and production Brain |
| `TYPESAFE_API_KEY` | Data page check, evals grader, dev Feedback page (Jev) |
| `ABUSE_HASH_KEY` | Production student UI |
| `RAW_ARTIFACT_ACCESS_KEY_ID`, `RAW_ARTIFACT_SECRET_ACCESS_KEY` | Data publishing |
| `RENDER_API_KEY`, `VERCEL_TOKEN`, `GITHUB_SECRETS_TOKEN` | Production environment sync only |

Connect one **Local .env file** destination in 1Password:
`~/.config/rockygpt/rockygpt.env`. This is a named pipe in an owner-only directory,
not a plaintext credential file. `local-env.py` selects variables using
`config/local-environments.json`; each `keys` object maps a service variable to
its stored 1Password name. No service imports the whole environment.

`./run-local.sh` keeps both web clients on the local Brain. To run the dev UI
against production instead, stop its existing process on port 3100, use Node 22,
and run from this workspace:

    rockygpt-brain/.venv/bin/python local-env.py dev-production -- npm run dev -- --hostname 127.0.0.1

This loads only the production service token into the dev UI's server process.
Running `./run-local.sh restart` returns both web clients to the local Brain.
The ordinary local student UI and dev UI need no credential file.

Reading a mount needs 1Password unlocked and a click on its prompt, which stops
unattended runs such as Remote Control sessions. So the local Brain keeps its five
secrets in `rockygpt-brain/.env.local`, a plain file readable only by you and
ignored by both repositories. Copy them there once, with 1Password unlocked:

    rockygpt-brain/.venv/bin/python local-env.py --seed brain

`--seed` refuses to write unless git ignores the file, writes it owner-only, and
prints only key names. While the file exists, `run-local.sh`, `local-env.py brain`
and the dev Brain deploy script read it and never touch 1Password. Rerun `--seed`
after rotating a Brain credential in 1Password; it also resets `DATABASE_URL` to
1Password's value. Delete the file to read 1Password directly again.

Run credential-dependent Data commands through `local-env.py data -- <command>`;
this selects its production campus database and artifact credentials. Local-only
data commands can supply their database directly:

    DOTENV_CONFIG_PATH=/dev/null DATABASE_URL=postgresql://postgres@127.0.0.1:55434/<db> npm run data:publish

Keep 1Password running and approve its prompt when a mount is first read;
authorization lasts until 1Password locks. Data's storage keys are used by artifact
publishing when its bucket is configured.
Environment names, project IDs and Brain switches belong in rockygpt-infra's manifest.
The model comes from the Brain's versioned release, not an environment override.
Python requires `python-dotenv` 1.2 or newer for this launcher.
Edit credentials in 1Password or settings in the manifest, then restart affected
processes. Do not open a mounted
file in an editor while a service is reading it: simultaneous reads are not
supported. See [1Password's local file documentation](https://www.1password.dev/environments/local-env-file).

## Comparing the laptop with production

    rockygpt-brain/.venv/bin/python compare-production.py           # 10 questions
    rockygpt-brain/.venv/bin/python compare-production.py --limit 3

Asks the laptop Brain (:8000) and the production Brain the same questions at the
same time and lists every question whose status, dataset version, facts or cited
links differ; wording is shown but not judged. The question list is
`config/compare-questions.txt`. Each question costs a few cents on each side, and
production's share is charged to production's ledger. The production token is read
through `local-env.py dev-production`. Full answers go to `.local-logs/compare-*.md`.
A facts mismatch can be the model picking a different lookup: ask that question again
before treating it as a gap.

## Running the stack

    ./run-local.sh start          # brain :8000, student ui :3000, dev ui :3100
    ./run-local.sh start --like-prod   # the student ui built and served as Vercel serves it
    ./run-local.sh status         # what is up, and whether it is ready
    ./run-local.sh logs brain     # or `ui`, or `dev`
    ./run-local.sh stop

`start` first checks the Brain's virtualenv against production: the Python version the
Dockerfile names and every package in `rockygpt-brain/requirements.lock`. Different
packages are installed from the lock on the spot; a different Python stops the start with
the command that recreates `.venv`. `--like-prod` runs `next build` and `next start` for the
student UI instead of `next dev`, so it has production's React, security headers, splash and
saved chats; use plain `start` while editing UI code, since a build does not reload.

`start` then combines and validates the Brain's settings and secrets, then clears ports
3000, 3100 and 8000 and waits for each service to answer. The Brain reads
`rockygpt-brain/.env.local`, or its 1Password sources when that file is absent; both web clients are pointed at the
local Brain automatically. The local Brain is bound to loopback and does not
use a staging token.
The Brain uses its own `DATABASE_URL`. Its validated variables are passed through
an in-memory pipe and inherited by reload workers, so workers do not compete to
read the 1Password mount. Both `start` and `restart` reject incomplete or
production Brain settings before stopping the current services.

For standalone Brain tools, use the same loader so public settings and secrets
are combined without creating a plaintext file:

    rockygpt-brain/.venv/bin/python local-env.py brain -- .venv/bin/python scripts/evaluate_routing.py --help
    rockygpt-brain/.venv/bin/python local-env.py data -- npm run data:quality

The loader runs the command from that service's directory. Never print or log
the loader's internal `--snapshot` output; it contains credentials.

## Asking from a terminal

    ./rocky ask "when is the next shuttle"      # answer, status, and sources
    ./rocky ask "..." --raw                     # complete response JSON
    ./rocky ask "..." --history /tmp/rocky.json  # start or continue a conversation
    ./rocky bulk short [delayMs]                # run sample questions independently
    ./rocky bulk full  [delayMs]                # run the larger sample set
    ./rocky bulk file <path> [delayMs]          # one question per line

Goes through `rockygpt-dev` at `http://localhost:3100`; set `ROCKY_DEV_UI` to use
another address. Python 3 is required. `rocky-format.py` prints the response.

Every request contains only `messages`: the ordered user and assistant messages
for that conversation. There is no server conversation ID or hidden memory.
Without `--history`, each CLI question is independent. With `--history`, the
CLI reads a JSON array of `{ "role": "user" | "assistant", "content": "..." }`
messages and updates the file after each successful response. A missing file
starts an empty conversation. Bulk commands accept the same option to test
follow-ups. History files contain the conversation text; keep them outside the
repository.

The Brain returns an answer, its status (`answered`, `partial`, `clarification`,
or `unavailable`), citations, model and request identifiers, the dataset version,
and a compact tool trace. Student and developer clients both use this JSON
contract; no streaming or internal pipeline-stage contract is required.

## What is deliberately not here

No service source, no `.env`, and no deployment configuration — deployment
lives in `rockygpt-infra`. If a change belongs to one service, it belongs in
that service's repository.
