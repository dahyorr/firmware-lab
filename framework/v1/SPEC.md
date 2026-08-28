SPEC.md
├── 1. What this document is
├── 2. Project at a glance
├── 3. Hard rules (do / do not)
├── 4. Architecture
├── 5. Per-module specifications
├── 6. Data contracts (file formats, schemas)
├── 7. Configuration and conventions
├── 8. Operational procedures
├── 9. Known issues and workarounds
├── 10. Open questions
├── 11. Glossary
└── 12. Changelog

# IoT Firmware Security Assessment Framework — Specification

**Project:** Automated IoT Firmware Security Assessment through Virtualisation and Dynamic Analysis
**Author:** Adebanjo Adedayo (77591559), MSc Cybersecurity, Leeds Beckett University
**Last updated:** 2026-06-07
**Status:** Active development. v1 of framework exists; v2 is being designed against this spec.

## 1. What this document is

This is the single source of truth for the framework. If something here conflicts with anything elsewhere (lab notebook, code comments, conversation history), this document wins until updated.

**Read this first if you are:**
- A new AI assistant being asked to work on the framework
- The author returning after time away
- Anyone reviewing the project's technical decisions

**Order of authority** (highest first):
1. This spec
2. The lab notebook (in `~/project/notes/lab-notebook.md`)
3. The MSc proposal (in `~/project/77591559_MSc_Proposal.docx`)
4. Code comments
5. Conversation history with any AI assistant

**This document is not the dissertation.** The dissertation is written separately and tells the academic story. This spec is operational: it describes what to build, what not to build, and how the parts fit together.

**Update protocol:**
- Any design decision that changes architecture, contracts, or rules → update this document in the same commit
- Add a one-line entry in section 12 (Changelog) with date and what changed
- Don't delete past decisions — strike them through and note the new direction, so the history is auditable
- For major changes, add a note in section 10 (Open questions) if it raises new uncertainties to be resolved


## 2. Project at a glance

**Goal:** Take a firmware image as input, produce a structured security assessment report as output, automated.

**Pipeline:**
firmware image → acquisition (validate, identify, hash) → virtualisation (emulate via FirmAE) → analysis (probe running emulation: services, CVEs, credentials, web, Possible light web vulnrabilities testing) → reporting (write structured JSON + human-readable report)

**What this framework IS (current scope):**
- A wrapper around FirmAE that adds consolidation, dynamic analysis, and reporting
- A research artefact for the MSc dissertation
- A CLI tool, operated by the researcher
- Designed so its modules can be invoked from a future web layer without changes

**What this framework is NOT (current scope):**
- A production security scanner for real-world use against unauthorised firmware
- A replacement or improvement of FirmAE itself
- A hosted service or graphical interface — though see section 4.5

**What this framework will become (post-dissertation):**
- A web-uploadable system with a Next.js frontend
- S3-compatible object storage for firmware (self-hosted, home lab)
- Valkey-based pub/sub for module status, metadata, and inter-module messaging
- PDF reports served back to the frontend after worker processing

These post-dissertation plans inform v1 design but are not delivered as part of the MSc submission. They are scoped at roughly one week of work after the core framework and evaluation are complete.

## 4.5 Future architecture (post-dissertation, ~1 week scope)

Once the core framework is complete and the dissertation submitted, the framework will be wrapped in a self-hosted web interface. The infrastructure runs entirely in the home lab.
[Browser]
│ upload firmware
▼
[Next.js frontend]
│ multipart upload
▼
[Self-hosted S3 (MinIO or similar)]
│ trigger event
▼
[Worker]
│ pulls firmware, runs framework
│ publishes module status to Valkey pub/sub
│ writes structured + PDF report back to S3
▼
[Frontend polls / subscribes to Valkey for status updates]
▼
[User downloads PDF]



**Why this is documented but not built in v1:**

- The dissertation's contribution is the analysis framework itself, not its deployment wrapper
- Building it consumes time better spent on CVE matching, credential testing, evaluation, and writing
- It does not change the framework's analysis behaviour — only how it is invoked and presented

**v1 design discipline to enable v2 without rework:**

- Module entry points take explicit inputs and return explicit outputs — no implicit CLI context
- No module reads `sys.argv` or environment-specific paths directly; configuration is passed in
- Reports are written as files to a configurable output directory (S3-uploadable later)
- Long-running operations expose status hooks (for v2: Valkey publishes; for v1: log lines)
- No global mutable state that would break worker isolation

**Out of scope even for v2:**

- Multi-user authentication and access control
- Cloud deployment (AWS, GCP, Azure)
- Production-grade security hardening of the web layer
- Anything that exposes the home lab to the public internet

## 3. Hard rules

Rules anyone working on this framework must follow. Numbered for reference (R-1, R-2, etc.) so changes can be discussed precisely.

### 3.1 Safety

**R-1. Validate every inferred IP is RFC1918 private or loopback before any probing.**
FirmAE can infer publicly-routable IPs for some firmware (observed: D-Link IP camera firmware inferring 2.65.87.199, a Swedish mobile network address). If the framework probes such an IP, even when FirmAE's tap routing keeps the traffic local, the framework's safety guarantee depends on FirmAE behaving correctly rather than on its own invariants. The framework must impose this check independently. Non-private inferred IPs reclassify the run as `emulation_failed`.

**R-2. Do not perform any action against an IP not validated under R-1.**
Includes nmap, curl, HTTP requests, default credential attempts, anything network-touching. No exceptions for "I know this one is safe."

**R-3. Do not attempt exploitation.**
The framework reports CVE matches; it does not weaponise them. Default credential testing logs whether credentials are accepted; it does not perform post-authentication actions. Web vulnerability probing identifies presence of vulnerabilities; it does not exfiltrate data or modify state.

**R-4. Do not use aggressive scanning that may crash fragile firmware.**
- No nmap `--script=vuln` or other NSE scripts that mutate state
- No `-A` (aggressive) mode
- Comprehensive profile maxes at `-T4 --min-rate 1000`; stealth profile uses `-T2`
- Treat emulated firmware as a fragile dependency: it can crash silently and stop responding

**R-5. The framework operates only on emulated firmware, never on real devices.**
No real-world device probing, even when the operator claims authorisation. Authorised real-world testing is a different research design with different ethics approval.

### 3.2 Scope

**R-6. Do not modify FirmAE.**
The framework wraps FirmAE; it does not patch it. Quirks in FirmAE are handled by the wrapper, not by editing upstream code. If FirmAE behaviour blocks the framework, the spec is updated to acknowledge the limitation; FirmAE is not changed.

**R-7. Do not add firmware-specific logic.**
No hardcoded ports, IPs, paths, or credentials specific to one device or vendor. Vendor and image variation is data (loaded from config or dataset), not code.

**R-8. Do not implement out-of-scope analysis techniques.**
Excluded: binary decompilation, disassembly, coverage-guided fuzzing, symbolic execution, manual exploit development. If a future analysis is genuinely required, it gets a spec amendment and a new in-scope rule.

**R-9. Do not build deployment infrastructure as part of v1.**
The Next.js frontend, S3 storage, worker queue, PDF-to-frontend pipeline are v2 work. v1 design enables v2 without rework but does not include it.

### 3.3 Reproducibility and determinism

**R-10. Same input must produce the same finding set.**
No LLM calls at runtime. No randomised behaviour. No time-of-day-dependent logic. If a non-deterministic component is unavoidable (e.g., nmap's port scan order), the framework records enough metadata for the output to be interpreted consistently.

**R-11. Every firmware submitted produces exactly one report.**
Success, emulation failure, timeout, or error — every case writes a report file. No silent drops, no "skipped" without an artefact recording the skip.

**R-12. Cached and fresh runs are distinguished in outputs.**
The `from_cache` flag is preserved end-to-end. Headline processing-time measurements use fresh runs only; cached runs are reported separately.

**R-13. Do not retry failures more than once per image per batch run.**
Repeated retries inflate batch timing and hide systematic failure modes. If a single image needs multiple attempts to characterise, that is a separate manual investigation, not batch behaviour.
These were not defects that could be repaired in isolation, because they were symptoms of the code having grown without a governing design.
### 3.4 Engineering discipline

**R-14. Modules expose explicit function signatures, not implicit CLI context.**
A module's entry point takes its inputs as arguments and returns its outputs as values. No `sys.argv` reads, no global config dicts, no "the orchestrator sets this up before calling."

**R-15. All paths are configurable.**
No hardcoded `~/project/...` paths inside modules. Paths are passed in. Default values live in one constants module or the orchestrator.

**R-16. Module status events are published to Valkey.**
Every module emits `start`, `progress` (where meaningful), `success`, and `failure` events to a per-module topic. v1 may run without a subscriber; v2's web layer subscribes for live UI updates.

**R-17. Do not introduce global mutable state.**
Each invocation of `analyse_firmware()` is self-contained. The only shared state is FirmAE's own database and scratch directories, which are accessed but not mutated outside FirmAE's own operations.

**R-18. Do not parallelise FirmAE invocations.**
FirmAE manipulates host networking and PostgreSQL state in ways unsafe under concurrency. Sequential only. Future parallelism is a research project of its own.

**R-19. Do not store firmware binaries in version control.**
Code, scripts, notes, and small artefacts only. Firmware images live on the lab VM and (in v2) in object storage. `.gitignore` enforces this.

### 3.5 Ethics and disclosure

**R-20. Report any inferred-public-IP incident to the supervisor.**
Even with R-1 in place, any case where the framework would have probed a non-private IP without the check is recorded in the lab notebook and disclosed to Mo. This is a verification of the safety mechanism, not an incident report.

**R-21. Coordinated disclosure for any undisclosed vulnerabilities found.**
If the framework identifies vulnerabilities not already covered by a public CVE, follow coordinated disclosure: notify the manufacturer privately, allow 90 days for remediation, no public details until disclosure complete.

**R-22. Do not analyse firmware whose analysis has not been authorised.**
The dissertation's ethics approval covers consumer IoT firmware obtained from manufacturer public download portals and academic research datasets. Firmware obtained otherwise is out of scope and not to be analysed under this project.

