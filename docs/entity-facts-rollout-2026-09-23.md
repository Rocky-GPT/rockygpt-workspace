# Shared entity facts rollout — 23 September 2026

Normal applications now resolve an entity and obtain its facts through one shared
backend contract. Matching values retain every supporting assertion, while source
records remain independently inspectable evidence. This is implemented in the
Brain and used by model tools, public entity APIs, the developer graph and the
student directory. It is not just browser grouping.

## FOUND

- Contact lookup used a directory-specific SQL path; profiles and the graph exposed
  separate source values. The browser previously owned grouping semantics.
- Scalar/list phone and office representations exposed duplicate paths. Faculty
  email notes, room-code formatting, explicit retirement suffixes and Unicode
  whitespace also created differences between original profiles and their derived
  contact rows.
- Rikki's two matching email evidence records represent one faculty capture, not
  two independent confirmations.
- The student directory pointed to a missing current-Brain endpoint. Its former
  client fallback rebuilt contact values and inferred unsupported assistance tags.

## FIXED

- Shared `EntityFacts` / `canonical_properties` in Brain resolves explicit property
  mappings after exact identity binding. All mapped entity kinds are covered,
  including catalog courses. No new persistent facts table or fuzzy identity joins.
- Contact/profile reads and the new model-facing `lookup_entity` use that resolver.
  Discovery provides canonical IDs; citations retain original source records.
  Review sees fact status/support, and budget trimming withholds unsupported summaries.
- Public pinned `/v1/entities/{id}/facts` and developer `/projection/v3` share the
  resolver. Release/hash/cursor guards and contextual record boundaries remain.
- Equal values group with evidence IDs. Conflicts, unknown values and distinct
  validity intervals stay explicit. Source cleanup, phone/office representation,
  retirement status and event date precision are backend-owned rules. Raw assertions
  stay inspectable. Preference flags no longer imply a preference without explicit
  source wording.
- Dev UI consumes backend groups; student directory discovers canonical entities
  and loads selected facts lazily. Legacy source-oriented directory API is deprecated.
- Program-panel embedded person contact snapshots were removed. That unbuilt
  current-Brain program-data endpoint remains unavailable, with an explicit message
  and guidance to the Directory / official program source.
- New ingestion captures use nullable email preference. Migration 022 removes the
  default/NOT NULL restriction without rewriting immutable historical values.
- Root `AGENTS.md` requires the shared fact contract for future consumers.

## NOT FIXED / DELIBERATE LIMITS

- Original source tables, identity links and audit/compatibility APIs remain. They
  retain provenance and are not alternative authorities for normal fact reads.
- Source freshness, incomplete source coverage and unclear source claims are not
  cured by agreement/grouping. Existing caveats remain visible.
- Canonical contact answers use normal evidence review instead of the former
  directory-only deterministic shortcut. This can add model latency/cost; a future
  shortcut must validate shared facts and all relevant evidence.
- No production deployment or new program-data browsing API was part of this rollout.
  Student UI was built and tested; its normal localhost service was not running.

## NEEDS REBUILD

No rebuild is needed for the shared reader: it is live against the existing active
dataset. Historical raw preference values remain unchanged and are interpreted
conservatively by the read model. Migration 022 and nullable publication behavior
apply to future data publication; the active dataset was not republished.

## NEEDS SOURCE REVIEW

No new source-review decision blocks this design. The system preserves actual
disagreements instead of choosing a winner; those require source review when they
occur. Evidence counts are explicitly record counts, not independent votes.

## Verification and runtime

- Brain: **801 passed, 41 skipped** (opt-in suites); scoped Ruff/mypy passed.
- Data: **233 passed, 5 skipped**, build/typecheck/lint passed. An isolated temporary
  PostgreSQL test verified migration idempotency and preservation of old values.
- Student UI: **4 browser tests**, TypeScript, scoped lint, and production build
  passed. Cases include lazy entity loading, conflicts, stale pins, extension-only
  phones and retirement of embedded program emails.
- Dev UI: graph contract/presentation tests, TypeScript and lint passed; live browser
  verified Rikki's single email and expandable original evidence.
- Read-only active-data checks covered all 12 entity kinds and all **231 people**.
  The known formatting-only people conflicts resolve; synthetic conflict regressions
  still retain competing values. This is not a fresh verification of campus truth.
- Live API: **245 directory entries**; Rikki one email, phone and office value each
  with two evidence records and explicit derivation; incorrect release pin returns
  **409**. All **874** Birch menu and **21** dining-hours record IDs survive pagination.
- Graph remains **3,758 entities / 4,320 relationships**.

Active local Brain revision: `5e8260e821f5e253ba2e1a839271378f586d3018`.
Active dataset: `dev-profiles-ingestion-20260923-r2`.
Identity hash: `00de9d4548cee04550431b5b66446213d8d38ac205543a3dece39030807b006f`.
Runtime configuration hash: `b2cea8f0723dbd5c98fd514595fe37f29034219b0bf04d86e292e6dad6201485`.

The read-only API check output is retained locally at
`.local-logs/profile-feature/entity-facts-20260923/live-checks.json`.
Contract and extension rules: `rockygpt-brain/docs/entity-facts.md`.

Changes are on the existing service `dev` branches and workspace `main`; no new
branches were created. Brain functional commits: `3ceff14`, `00e14ef`, `cbc749d`,
`5e8260e`. Data: `c7436ad`, `afb8194`. Student UI: `438db58`, `3ef2c1c`.
