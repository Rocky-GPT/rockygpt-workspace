# AI Agent Instructions

## Git Branching Rules
- **NEVER create new git branches** (no `git checkout -b`, no feature branches, no `codex/...`, `feature/...`, or `chore/...` branches).
- All work must be committed and pushed directly to:
  - **`dev`** for all service repositories (`rockygpt-brain`, `rockygpt-ui`, `rockygpt-data`, `rockygpt-dev`, `rockygpt-evals`, `rockygpt-infra`).
  - **`main`** for the root workspace repository (`RockyGPT`).
- Always remain on the active branch (`dev` or `main`). Do not switch branches unless explicitly requested by the user.
