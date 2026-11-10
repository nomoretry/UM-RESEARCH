# UM research working instructions

This repository studies electric-truck charging capacity and scheduling. Read these files at the start of each task:
0. docs/PROGRESS.md, conversations/INDEX.md and docs/workflow/CONVERSATIONS.md; confirm the explicit binding for this chat and read its STATUS.md and, for a branch, the parent STATUS.md. A machine-local last binding is a convenience, never proof that a different chat is the same conversation.
1. README.md
2. docs/research/STATUS.md
3. docs/research/DECISIONS.md
4. docs/model/FORMULATION.md and docs/model/IMPLEMENTATION_MAP.md when changing a model
5. docs/workflow/STORAGE.md before recording or publishing runs

## Evidence and scope
- The UM question governs scope: under identical port transport tasks and service requirements, jointly configure port/warehouse interfaces and available connection capacity and schedule charging; explain when coordination reduces total facility/operating cost and when interfaces, parking eligibility or supply capacity bind.
- Application emails, CVs and motivation letters are claim-audit/display material, not authorization to add research modules or borrow another project's achievements. Mark unsupported UM claims as unverified. Do not read or modify the semiconductor logistics project during UM work unless separately instructed.
- Distinguish proposed, implemented, previously reported, and reproduced-in-this-session. Never upgrade a claim because an earlier assistant or CV said it was done.
- Verify current code, inputs, and outputs when they conflict with documentation. Record the discrepancy and update the status; do not silently change the research question.
- Existing evidence covers German DT-CARGO / SimBench preprocessing. The port-drayage proposal is a separate proposed application. Never relabel German data as Guangdong or equate an artificial grid mapping with an actual connection.
- Keep transport and operations research central. First model: fixed tasks, fixed service order and primary routes, charging scheduling and capacity investment. Routing flexibility is a later extension. No automatic addition of RL, V2G, storage, swapping, or full power flow.
- Development order: deterministic facility planning and applicability boundaries, then fixed-facility operating stress tests, then a scenario model only if evidence warrants it. Sensitivity/stress tests are not uncertainty planning. A scenario model must specify information timing, common prior investment and permitted operational recourse. Do not add electricity markets or multi-agent methods without a specific UM research need and later authorization.
- Preserve infeasibility and zero-benefit results. Do not manufacture charging demand with arbitrary low initial energy.
- Keep input provenance and units explicit: observed, derived, assumed, simulated. kW is not kWh; charger count is not connection capacity.
- Each implemented constraint needs a stable ID, code location, meaningful verification and evidence link. A solver success status alone is insufficient.
- Retain infeasibility, zero benefits and all tied optimal facility configurations. Compare charging scopes under the same connection policy and service requirements. An incumbent at a time limit is not proven optimal. Synthetic cost differences, site-capacity checks and observed schedule peaks are not real savings rates, power-flow feasibility or minimum-peak results.
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

## Conversation records and checkpoints
- One main chat has one stable numbered directory; branch chats are nested under its branches/. Register other chats only on first explicit access. Do not scan chats or infer their relationship from research files. Ask only for the parent when it is unknown.
- Platform IDs and titles must come from an actual API response or the user. Otherwise use a stable local number, identify the title as local, and keep platform_id null. Renaming a chat never renames its directory.
- Use scripts/conversation_records.py (or scripts/records.ps1) for registration, binding, action logs, explicit-file checkpoints and status checks. Read its --help; do not guess argument or JSON field names.
- Log observable actions throughout the task, including failures, verification and artifact locations; record substantive research decisions in DECISIONS.md. Do not write private reasoning transcripts, raw chat exports or secret values.
- After each meaningful work unit, inspect the diff and commit only reviewed, explicitly named files. Before interruption, save a checkpoint and state verified, unverified and failed work in the chat STATUS.md, with the next step and exact rerun commands.
- Full actions.jsonl and runs/ live only in the external local Git record repository without remotes. Keep the absolute records path and current binding in ignored .um-records.local.json. Verify that detailed evidence is actually tracked there; a broad *.log ignore must not discard it.
- For experiments record exact source commit, dirty patch and necessary untracked source where applicable, configuration/data hashes, random seed or nonrandom reason, metrics, validation and artifact paths. Mark incomplete provenance rather than implying reproducibility. Commit exact source before a canonical run.
- Chat artifacts belong in that chat's artifacts/. Shared code/data stay in existing shared paths and are linked relatively. Index existing files first; do not move, rename, merge or duplicate datasets for organization.
- A chat folder is not a Git branch. Concurrent shared-code work requires separate worktrees and branches; do not switch branches in a shared checkout. Registration alone creates no Git branch.
- Summarize a branch's supported conclusions into its main chat with evidence links and provenance. Preserve earlier conclusions and explain changes.
- Push only the explicit authorized branch after local checks; verify its exact remote SHA with git ls-remote. Never claim synchronization solely because a commit exists or cached refs agree. Do not auto-merge into main.
- Complete small implementation/experiment milestones with explicit local commits and publish their curated code/configuration/results once validated; do not accumulate all work until the whole research program ends. Never commit full logs to pushable history and then rely on deletion or .gitignore. Do not upload personal applications, credentials or unrelated files, change visibility, alter global configuration, or migrate disks.
- This mechanism records explicitly invoked helper operations; the App tool surface does not provide a verified universal tool-call hook or automatic complete-chat export. AGENTS.md is an execution rule, not an event listener. State manual or assistant-triggered gaps honestly.

## Collaboration and user-facing research evidence
- Codex owns research continuity, task boundaries, integration, validation and publication. Claude may discuss models, implement bounded modules/checkers, review code or improve necessary structure. Do not restructure the whole repository merely to enable collaboration.
- Every delegated task names an exact base commit, input/output contract, owned files, acceptance checks and scope exclusions. Concurrent edits use independent branches/worktrees. Integrate with commit provenance and rerun affected checks; do not overwrite another worktree.
- A technical subtask of this same explicitly bound chat does not require a new user-chat registration or a duplicate record system. The root records its work in the existing conversation. Separate user chats still follow the explicit registration rules above.
- If Claude cannot actually run, record the limitation, prepare a directly usable task with commit/file entry points and continue independent work. Never label other agents or a prepared prompt as completed Claude collaboration.
- Keep an evidence-bounded capability checklist: implemented and verified, implemented awaiting verification, not implemented. A category may be empty. Deliver an understandable problem/input/decision summary, a task/charging-window diagram, actual facility/cost/feasibility comparisons, an explained bottleneck, formula-to-code links and copyable Windows commands with expected outputs.
