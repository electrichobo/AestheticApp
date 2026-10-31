# AESTHETIC — Development Handoff

## Repository & State
- **Repository**: electrichobo/AestheticApp @ `main`
- **Architecture**: Rust Core Engine (Ground-Up Rebuild)
- **Active Target**: Windows x64 (Live Production Environment)

---

## Current Status: M11 (Motion Dynamics & Deduplicated Server Ingest)
- Cinematography Awards Registry: 184 Oscar, ASC, and BSC award-winning & landmark titles (1995–2025+) with fuzzy normalization matcher.
- Motion Dynamics Recorded: True multi-threaded block matching optical flow (`motion_optical_flow`, `camera_motion_ratio`) stored on all baseline reference setups.
- Deduplication & Force Controls: Automatic skip of already-ingested films in both CLI (`--force`) and Desktop UI modal (`#server-ingest-force` checkbox).
- 24/24 tests passing, zero clippy warnings, rustfmt compliant.

---

## Next Immediate Step (Corpus Expansion & Full Server Ingestion)
1. **Full/Batch Ingestion**: Run `aesthetic-cli ingest-server M:\movies --limit 55 --shots 5` (or desired subset) to expand Golden Baseline with all matched films.
2. **Interactive UI Review**: Launch desktop UI (`aesthetic-ui`) to test live candidate evaluation against the real cinema corpus.

---

## Safety & Invariants
- Live production machine: never install software/services/Docker; no system changes.
- Never add a crate without explicit user approval.
- Keep `HANDOFF.md` under 50 lines; `AGENTS.md` under 12,000 characters.
- Commit/push only when requested by the user.
