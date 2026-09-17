# RockyGPT AI Agent Instructions (Codex)

Welcome to RockyGPT. This root `AGENTS.md` is the master instruction guide for AI agents working across the workspace.

---

## 1. Git Branching Rules (Strictly Enforced)

- **NEVER create new git branches** (no `git checkout -b`, no `codex/...`, `feature/...`, or `chore/...` branches).
- Work must always be committed and pushed directly to:
  - **`dev`** for all service repositories (`rockygpt-brain`, `rockygpt-ui`, `rockygpt-data`, `rockygpt-dev`, `rockygpt-evals`, `rockygpt-infra`).
  - **`main`** for the root workspace repository (`RockyGPT`).
- Always remain on the active branch. Do not switch branches unless explicitly requested by the user.

---

## 2. Workspace Architecture

The workspace consists of 6 standalone services coordinated by this root tooling repo:

| Directory | Role | Stack | Active Branch | Primary Test Command |
| :--- | :--- | :--- | :--- | :--- |
| **`rockygpt-brain`** | Core engine, evidence gating, budget accounting | Python 3.13, FastAPI, Postgres | `dev` | `.venv/bin/pytest` |
| **`rockygpt-ui`** | Student-facing chat UI | Next.js, React, TypeScript | `dev` | `npm run lint` |
| **`rockygpt-dev`** | Internal developer inspection UI | Next.js, React, TypeScript | `dev` | `npm run dev` |
| **`rockygpt-data`** | Campus data ingestion and database schemas | Node.js, TypeScript, PostgreSQL | `dev` | `npm run build` |
| **`rockygpt-evals`** | Evaluation benchmarks and acceptance suites | Node.js / Python | `dev` | `npm run test:all` |
| **`rockygpt-infra`** | Deployment manifests, operational storage | Docker, Terraform | `dev` | — |

---

## 3. Core Development Principles

- **Zero Hallucination / Evidence Grounding**: The brain must strictly answer based on retrieved verified database evidence. Do not extrapolate unverified claims, ranks, or official campus authority.
- **First Principles**: Keep architectures simple and modular. Do not introduce premature abstractions, complex agent graphs, or extra layers until a concrete measured failure demands it.
- **Do what is asked, then stop**: Focus strictly on the user's immediate request without gratuitous refactoring.

### Service-Specific Rules:

#### `rockygpt-brain` (Clean-Room Implementation)
- Do not read, inspect, copy, reference, or reuse old RockyGPT v1 branches, commits, tags, tests, prompts, or architecture unless explicitly asked.
- Build one small step at a time from first principles.

#### `rockygpt-ui` & `rockygpt-dev` (Next.js Framework Guidance)
- The Next.js version in this workspace has breaking changes and updated conventions compared to older training data.
- Read the bundled documentation in `node_modules/next/dist/docs/` before writing frontend code.

---

## 4. Running the Local Environment

- **Run the full stack locally**:
  ```bash
  ./run-local.sh
  ```
- **CLI orchestration tool**:
  ```bash
  ./rocky --help
  ```
- **Testing the Brain**:
  ```bash
  cd rockygpt-brain && .venv/bin/pytest
  ```
