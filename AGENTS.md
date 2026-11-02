# RockyGPT AI Agent Instructions

This root `AGENTS.md` is the instruction guide for AI agents working across the workspace.

---

## 1. Git Branching Rules (Laptop)

- On the laptop, **don't create new git branches**.
- Commit and push directly to:
  - **`dev`** for the service repos (`rockygpt-brain`, `rockygpt-ui`, `rockygpt-data`, `rockygpt-dev`, `rockygpt-evals`, `rockygpt-infra`).
  - **`main`** for this root workspace repo (`rockygpt-workspace`).
- Stay on the active branch unless asked to switch.

---

## 2. Workspace Architecture

This root tooling repo coordinates 6 service repos:

| Directory | Role | Stack | Branch | Check |
| :--- | :--- | :--- | :--- | :--- |
| **`rockygpt-brain`** | Answer engine, campus graph, budget ledger | Python 3.13, FastAPI, Postgres | `dev` | `.venv/bin/pytest` |
| **`rockygpt-ui`** | Student-facing chat UI | Next.js, React, TypeScript | `dev` | `npm run lint` |
| **`rockygpt-dev`** | Internal developer UI | Next.js, React, TypeScript | `dev` | `npm run lint` |
| **`rockygpt-data`** | Campus data collection and publishing | Node.js, TypeScript, PostgreSQL | `dev` | `npm run build` |
| **`rockygpt-evals`** | Evaluation sets and runners | Python / Node.js | `dev` | `brain-reset/run.py` |
| **`rockygpt-infra`** | Docker files, settings sync, deploy scripts | Docker, Python | `dev` | — |

---

## 3. Core Development Principles

- **Graph-only campus facts**: the Brain may answer campus questions only from facts in the campus graph. Never make up a fact. Non-campus replies (greetings, the date, emergency numbers, "which office?") may be fixed code.
- **Code writes answers where it can**: prefer code-written answers over AI-written ones, so the same question gets the same answer every time.
- **First Principles**: keep the design simple. Don't add abstractions or extra layers until a real measured failure needs them.
- **Entity Facts Are Shared**: Brain and app fact reads resolve a canonical entity and use the shared reader in `rockygpt-brain/src/rockygpt_brain/retrieval/entity_facts.py`. Don't reconcile fact values separately in a UI. See `rockygpt-brain/docs/entity-facts.md`.
- **Do what is asked, then stop**: no extra refactoring beyond the request.

### `rockygpt-ui` & `rockygpt-dev` (Next.js)
- This Next.js version has breaking changes compared to older training data. Read `node_modules/next/dist/docs/` before writing frontend code.

---

## 4. Running and Testing Locally

- Run the full stack: `./run-local.sh`
- Ask the Brain a question (use this for testing): `./rocky ask "question"` (laptop) or `./rocky ask "question" --prod` (live website). See `./rocky --help`.
- Brain unit tests: `cd rockygpt-brain && .venv/bin/pytest`
