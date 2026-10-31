# AESTHETIC — Development Handoff

## Repository & State
- **Repository**: electrichobo/AestheticApp @ `main`
- **Architecture**: Rust Core Engine (Ground-Up Rebuild)
- **Active Target**: Windows x64 (Live Production Environment)

---

## Current Status: M11 (Awards Registry & Shot-Separated Server Ingest)
- Cinematography Awards Registry: 184 Oscar, ASC, and BSC award-winning & landmark films (1995–2025+) with fuzzy normalization matcher.
- Shot-Separated Temporal Ingestion: `compute_motion_dynamics` and cut-boundary segmentation (`ingest_reference_film_shots`) isolating clean camera setups without cut artifacts.
- Media Server Scanner (`aesthetic-cli ingest-server`): Auto-detects and matches award films on `M:\movies` (55 award films matched on dry run).
- 23/23 tests passing, zero clippy warnings, rustfmt compliant.

---

## Next Immediate Step (Media Server Ingestion Run)
1. **Execute Ingestion**: Run `aesthetic-cli ingest-server M:\movies --limit <N>` to ingest real reference shots from target films into `assets/baseline/`.
2. **Interactive UI Review**: Launch desktop UI to view expanded baseline comparisons and real-time overlays.

---

## Safety & Invariants
- Live production machine: never install software/services/Docker; no system changes.
- Never add a crate without explicit user approval.
- Keep `HANDOFF.md` under 50 lines; `AGENTS.md` under 12,000 characters.
- Commit/push only when requested by the user.
