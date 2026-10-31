# AESTHETIC — Development Handoff

## Repository & State
- **Repository**: electrichobo/AestheticApp @ `main`
- **Architecture**: Rust Core Engine (Ground-Up Rebuild)
- **Active Target**: Windows x64 (Live Production Environment)

---

## Current Status: M8 (Scoring Matrix & DP Comparison UI Complete)
- Protocol initialized: `AGENTS.md`, `CLAUDE.md`, `GEMINI.md`, `START_HERE.md`, `STATUS.md`.
- Workspace crates complete: `aesthetic-models`, `aesthetic-metrics`, `aesthetic-core`, `aesthetic-cli`, `aesthetic-ui`.
- Master DP Benchmark Comparison: Side-by-side diagnostic table in desktop UI comparing shot DR, roll-off, key-to-fill, split-toning, gaze poise, and catchlights directly against matched DP.
- Forensic Improvement Action Cards: Concrete recommendations generated from empirical deltas.
- Benchmark Harness: 4K frame physics (1.73s), 4K depth/craft inference (45ms), vector similarity search (1.31ms).
- 21/21 tests passing, zero clippy warnings, rustfmt compliant.

---

## Next Immediate Step (Production Packaging & DirectML Acceleration)
1. **Commit & Push M8 Updates**: Push scoring matrix UI and benchmark harness.
2. **DirectML Acceleration Option**: Profile DirectML on Windows vs Rayon SIMD CPU on 4K/8K media.
3. **End-to-End Media Ingest Test**: Run sample video through `aesthetic-cli analyze` and inspect exported selects.

---

## Safety & Invariants
- Live production machine: never install software/services/Docker; no system changes.
- Never add a crate without explicit user approval.
- Keep `HANDOFF.md` under 50 lines; `AGENTS.md` under 12,000 characters.
- Commit/push only when requested by the user.
