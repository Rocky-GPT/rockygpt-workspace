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

Keep `.env.example` files as configuration templates. On this workstation,
1Password Environments supplies the Brain, data, and developer UI `.env` paths
through local file mounts. These paths are named pipes: their plaintext contents
are delivered on demand and are not stored on disk. The student UI and HTTP eval
suites use the local Brain without their own credential files.

On a new workstation, open each local Environment in the 1Password desktop app
and connect **Local .env file** to the corresponding repository's `.env` path:

| 1Password Environment | Local path |
| --- | --- |
| RockyGPT - Local - Brain | `rockygpt-brain/.env` |
| RockyGPT - Local - Data | `rockygpt-data/.env` |
| RockyGPT - Local - Developer UI | `rockygpt-dev/.env` |

Use the actual Environment names shown in 1Password. Never connect a production
Environment to these local paths. Keep 1Password running and approve its prompt
when a service first reads a mount; authorization lasts until 1Password locks.
Store `BRAIN_ENVIRONMENT` explicitly as `development`, not `${APP_ENV}`: exported
variable order can differ from the original file. Python requires
`python-dotenv` 1.2 or newer for this launcher.
Edit values in 1Password, then restart affected processes. Do not open a mounted
file in an editor while a service is reading it: simultaneous reads are not
supported. See [1Password's local file documentation](https://www.1password.dev/environments/local-env-file).

## Running the stack

    ./run-local.sh start          # brain :8000, student ui :3000, dev ui :3100
    ./run-local.sh status         # what is up, and whether it is ready
    ./run-local.sh logs brain     # or `ui`, or `dev`
    ./run-local.sh stop

`start` first reads and validates the Brain environment, then clears ports
3000, 3100 and 8000 and waits for each service to answer. The Brain reads its
1Password-mounted `.env`; both web clients are pointed at the
local Brain automatically and share its optional `STAGING_SERVICE_TOKEN`.
The Brain uses its own `DATABASE_URL`. Its validated variables are passed through
an in-memory pipe and inherited by reload workers, so workers do not compete to
read the 1Password mount. Both `start` and `restart` reject incomplete or
production Brain settings before stopping the current services.

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
