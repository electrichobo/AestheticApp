# AGENTS.md — Agent Governance & Takeover Protocol

## 1. Project Mission & Identity
AESTHETIC is a high-performance local desktop application for cinematographers and editors to discover, rank, and extract their best shots, comparing work against a Golden Baseline of award-winning cinema.
The architecture is rebuilt from the ground up as a **Rust Core Engine** prioritizing computational precision, zero-cost abstractions, multi-threaded SIMD image processing, and rock-solid platform stability.

---

## 2. Production Safety & Environment Invariants
This Windows development system is a **live production machine**. The following rules are non-negotiable:
1. **Zero System Alterations**: Never install system software, runtimes, background services, startup items, Docker, WSL, or Hyper-V. Never alter OS settings or registry keys.
2. **Showtime Immediate Abort**: If the user indicates a show or live event is starting, immediately terminate all background jobs, subprocesses, and tasks.
3. **Dependency Lockdown**: **Never add a crate or package without explicit user permission.** No unapproved dependencies.
4. **Credential & Privacy Firewall**: Never commit or log personal details, absolute user paths with usernames, IP addresses, hostnames, or credentials.
5. **Controlled Git Actions**: Commit or push **only** when explicitly requested by the user. Only one agent works on `main` at a time.
6. **UTF-8 File Integrity**: Never use PowerShell 5.1 `Get-Content`/`Set-Content` (which corrupts UTF-8 without BOM). Always use agent file editing tools or Python scripts configured for strict UTF-8 without BOM.
7. **Document Limits**: Keep `HANDOFF.md` under 50 lines. Keep `AGENTS.md` under 12,000 characters.

---

## 3. Session Continuity & Constrained Takeover Protocol
At the start of **every session**, before modifying any file:
1. **Pull Latest Changes**: Run `git pull --ff-only` (sandboxed or bypass if network required). If it does not fast-forward cleanly, halt immediately and notify the user.
2. **Read Handover Documents**: Read `AGENTS.md`, `START_HERE.md`, `HANDOFF.md`, and `STATUS.md`.
3. **Inspect Repository State**: Run `git status`, `git diff`, and `git diff --staged`.
4. **Halt & Await Approval**: Stop and summarize for the user:
   - Any uncommitted changes.
   - The Next Immediate Step specified in `HANDOFF.md`.
   - The exact plan for the first edit.
   - **Wait for explicit user go-ahead before executing edits.**

When concluding work or passing the baton:
- Update `HANDOFF.md` (keep strictly under 50 lines).
- Synchronize `README.md` (status, roadmap, milestone tables).
- Notify the user so changes can be committed and pushed.

---

## 4. Rust Toolchain & Execution Protocol
- **Rust Toolchain**: Use Rust 1.99+ located at `~/.cargo/bin/` (`cargo`, `rustc`).
- **Sandbox Compliance**: Run cargo commands sandboxed first.
- **Path Hygiene**: Always refer to project paths relative to repository root (`E:\Antigravity\aesthetic`).

---

## 5. Architectural Pillars & Metrics Classification
The rebuild enforces a clean separation across five evaluation layers:
1. **Objective Physics**: Mathematical pixel analysis (exposure zones, highlight roll-off gradients, true dynamic range stops, MTF/spatial frequency, SNR).
2. **Model-Inferred Craft**: Deep perception (lighting geometry/key-fill azimuth, 3D depth separation, gaze vectors, focus breathing/hunting, camera movement vs subject movement).
3. **Subjective & Aesthetic**: Perceptual narrative appeal (compositional balance, silhouette readability, tension, style-family cluster similarity).
4. **Temporal & Editorial**: Video in motion (usable-window duration, move-settle quality, cut-point stability, visual fatigue index across edits).
5. **Forensic Diagnostics**: Non-punitive technical flags (sensor dust, flickering practicals, rolling shutter wobble, clipping persistence, dead pixels). These provide warnings and metadata without blindly penalizing artistic intent.
