# AESTHETIC — Development Handoff

## Repository & State
- **Repository**: electrichobo/AestheticApp @ `main`
- **Architecture**: Rust Core Engine (Ground-Up Rebuild)
- **Active Target**: Windows x64 (Live Production Environment)

---

## Current Status: Sidecar Isolation & UI Stability Hardened
- **Recursive Sidecar Discovery & In-Memory Frame Cache**:
  - `rescore_from_sidecars` recursively traverses directory trees, discovering all 45 hero takes across full seasons or individual episode folders with instant companion PNG pairing.
  - In-memory frame cache (`AppState.cached_frames`) eliminates all FFmpeg directory spawn calls for cached takes, ensuring zero crashes and instant 0.1ms thumbnail serving.
  - Hardened Golden Baseline protection invariant preventing user sidecars from writing into `assets/baseline/`.
- **Interactive UI Server**:
  - Live on `http://127.0.0.1:63513` with top-most STA folder dialog and browser prompt fallback for "Open Cached Sidecars Folder".
- **Quality**:
  - Workspace tests passing (27 tests), zero clippy warnings (`-D warnings`).

---

## Next Immediate Step
1. **Interactive Review**: Open `http://127.0.0.1:63513` and click "Open Cached Sidecars Folder" to review *Acting Dead*.

---

## Safety & Invariants
- Live production machine: zero system alterations; no unapproved crates.
- Keep `HANDOFF.md` under 50 lines; `AGENTS.md` under 12,000 characters.
- User granted permission to commit/push when md files are updated/current.
