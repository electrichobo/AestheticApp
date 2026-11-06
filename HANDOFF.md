# AESTHETIC — Development Handoff

## Repository & State
- **Repository**: electrichobo/AestheticApp @ `main`
- **Architecture**: Rust Core Engine (Ground-Up Rebuild)
- **Active Target**: Windows x64 (Live Production Environment)

---

## Current Status: Batch Season Pipeline & NLE Exports Active
- **Acting Dead Season 1 Ingested & Evaluated**:
  - Processed all 9 files (8 full episodes + trailer, 45 hero takes) under `assets/curated/acting_dead/`.
  - Exported per-episode and unified season-wide CMX 3600 standard EDLs (`season_all_hero_selects.edl`), Final Cut Pro XMLs (`season_all_hero_selects.xml`), CSV manifests, Resolve Python scripts (`season_all_hero_selects.py`), and visual contact sheets with embedded lossless PNG stills.
- **Interactive UI Server**:
  - Active on `http://127.0.0.1:63513` with multi-tier FFmpeg discovery and content-disposition NLE download attachments.
- **Quality**:
  - Workspace tests passing (27 tests), zero clippy warnings (`-D warnings`).

---

## Next Immediate Step
1. **Interactive Review**: Open `http://127.0.0.1:63513` in browser or import `season_all_hero_selects.xml` into DaVinci Resolve or Premiere.

---

## Safety & Invariants
- Live production machine: zero system alterations; no unapproved crates.
- Keep `HANDOFF.md` under 50 lines; `AGENTS.md` under 12,000 characters.
- User granted permission to commit/push when md files are updated/current.
