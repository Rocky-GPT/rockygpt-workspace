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
credentials, while `config/local-environments.json` stores public local settings.
The production equivalent is `rockygpt-infra/config/environment-sync.json`.
Matching credentials are stored once. Five 1Password Environments contain eleven
credentials, with explicit source mappings controlling which service receives each:

| 1Password Environment | Contents | Consumers |
| --- | --- | --- |
| RockyGPT - Shared | OpenAI key, Typesafe/Jev key, campus database connection | API keys: local and production Brain; database: Data and production Brain |
| RockyGPT - Local Brain | Local campus and ledger database connections | Local Brain only |
| RockyGPT - Data Storage | Artifact storage access key and secret | Data publishing |
| RockyGPT - Production | Production ledger connection and UI hash key | Render Brain and Vercel UI respectively |
| RockyGPT - Automation | Render and Vercel API tokens | Environment sync |

On this workstation, 1Password supplies three named pipes. Their plaintext
contents are delivered on demand and are not stored on disk. On a new workstation,
connect **Local .env file** in the desktop app to these workspace-relative paths:

| 1Password Environment | Local path |
| --- | --- |
| RockyGPT - Shared | `.env.shared` |
| RockyGPT - Local Brain | `rockygpt-brain/.env` |
| RockyGPT - Data Storage | `rockygpt-data/.env` |

Use `./run-local.sh` or `local-env.py` to combine these sources in memory. Each
service receives only its assigned keys. In particular, Local Brain uses its own
campus database, never the shared production/Data connection. The production
ledger is not mounted locally. The student UI, Developer UI, and HTTP eval suites
need no credential files.

Keep 1Password running and approve its prompt when a mount is first read;
authorization lasts until 1Password locks. Data's storage keys are used by artifact
publishing when its bucket is configured.
Environment names, project IDs, and routing settings belong in the JSON config.
The model comes from the Brain's versioned release, not an environment override.
Python requires `python-dotenv` 1.2 or newer for this launcher.
Edit credentials in 1Password or settings in the config, then restart affected
processes. Do not open a mounted
file in an editor while a service is reading it: simultaneous reads are not
supported. See [1Password's local file documentation](https://www.1password.dev/environments/local-env-file).

## Running the stack

    ./run-local.sh start          # brain :8000, student ui :3000, dev ui :3100
    ./run-local.sh status         # what is up, and whether it is ready
    ./run-local.sh logs brain     # or `ui`, or `dev`
    ./run-local.sh stop

`start` first combines and validates the Brain's settings and secrets, then clears ports
3000, 3100 and 8000 and waits for each service to answer. The Brain reads its
1Password-mounted sources; both web clients are pointed at the
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
