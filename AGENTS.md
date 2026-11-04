# UM research working instructions

This repository studies electric-truck charging capacity and scheduling. Read these files at the start of each task:
1. README.md
2. docs/research/STATUS.md
3. docs/research/DECISIONS.md
4. docs/model/FORMULATION.md and docs/model/IMPLEMENTATION_MAP.md when changing a model
5. docs/workflow/STORAGE.md before recording or publishing runs

## Evidence and scope
- Distinguish proposed, implemented, previously reported, and reproduced-in-this-session. Never upgrade a claim because an earlier assistant or CV said it was done.
- Verify current code, inputs, and outputs when they conflict with documentation. Record the discrepancy and update the status; do not silently change the research question.
- Existing evidence covers German DT-CARGO / SimBench preprocessing. The port-drayage proposal is a separate proposed application. Never relabel German data as Guangdong or equate an artificial grid mapping with an actual connection.
- Keep transport and operations research central. First model: fixed tasks, fixed service order and primary routes, charging scheduling and capacity investment. Routing flexibility is a later extension. No automatic addition of RL, V2G, storage, swapping, or full power flow.
- Preserve infeasibility and zero-benefit results. Do not manufacture charging demand with arbitrary low initial energy.
- Keep input provenance and units explicit: observed, derived, assumed, simulated. kW is not kWh; charger count is not connection capacity.
- Each implemented constraint needs a stable ID, code location, meaningful verification and evidence link. A solver success status alone is insufficient.
- Data verification uses Python without -O: the existing verifier relies on assert.

## Continuity
Before acting, inspect git status and the relevant history; preserve existing uncommitted work. Work on an isolated branch for substantial changes.
At each completed work unit, update STATUS.md (verified findings, limits, next task) and append substantive decisions to DECISIONS.md. Record facts, assumptions, commands and observations, not private reasoning transcripts.
Keep STATUS.md short. Read detailed histories only as needed; do not load every PDF or raw CSV into context.
Use prompts/RESUME.md for subsequent sessions and prompts/BOOTSTRAP.md for recovery.
Use existing code when sound. Do not rename or delete legacy directories merely to match a template.
Consult other repositories only for general engineering practices. Do not create framework-comparison documents, method mappings, imitation narratives, copied prose or borrowed result targets.

## Runs and results
Full runtime records belong in a separate local Git repository OUTSIDE this repository, with no remotes. They must never be committed to any branch that will be pushed here.
The main repository stores code, model, research decisions, reproducible configurations and curated results with provenance. Results are also committed locally before pushing.
A result package must identify source commit, input/config hashes, seed if applicable, environment and solver, termination status, objective/bound/gap when meaningful, independent feasibility checks and rerun command.
If source was dirty, retain the patch locally and its hash; do not claim the base commit alone reproduces the run. Commit exact source before a canonical rerun.
Never publish raw chat exports, solver logs or private source records by accident. Do not change repository visibility or reuse another project's publication authorization.

## Checks
Run only checks appropriate to the change. Documentation changes need link/state consistency checks, not invented solver tests.
Never report old validation JSON as a fresh successful run.
When local-only run records are unavailable in a cloud session, use versioned summaries and state the missing evidence.
