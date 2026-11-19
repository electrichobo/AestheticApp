# AESTHETIC — Development Handoff

## Repository & State
- **Repository**: electrichobo/AestheticApp @ `main` (pushed `cb5c99b`, tagged `v0.2.5` at `a92c70a`)
- **Architecture**: Rust Core Engine (Ground-Up Rebuild)
- **Active Target**: Windows x64 (Live Production Environment)

---

## Current Status: Empirical Baseline Target Calibration & ELI5 Scoring Guide Modal
- **Pure Empirical Golden Baseline Targets (`crates/aesthetic-core/src/baseline_store.rs`, `crates/aesthetic-ui/src/main.rs`)**:
  - Added `BaselineStore::key_fill_quantiles()` and removed artificial hardcoded target floors (`.max(13.5)`, `.max(88.0)`, `.max(110.0)`, `3.8:1`) in `/api/evaluate`.
  - Benchmark rows now display true measured corpus medians and IQRs (`p50 | p25–p75`: Dynamic Range `9.98` stops, Roll-Off `100.0%`, Laplacian Acutance `48.4`, Key-to-Fill `6.4:1`), plus Within-Style-Cluster rows (`n=239` etc.) and empirical `quantiles_summary`.
- **ELI5 Scoring & Target Guide Modal (`crates/aesthetic-ui/ui/index.html`, `app.css`, `app.js`)**:
  - Added `? ELI5 Scoring` and `? How Targets Work` triggers opening `#scoring-guide-modal`, explaining pillar formulas, percentile mapping (`p10–p90`), scene-by-scene MMR ranking, 6 showreel heads, advisory forensics, and displaying live `quantiles_summary` targets.
- **Verification & Packaging**:
  - `cargo clippy --workspace --all-targets -- -D warnings`: 0 code warnings; `cargo test --workspace`: 36/36 passed; `cargo build --release` clean.
  - Headless E2E check on `aesthetic-ui.exe` verified `Award-Winning Cinema Golden Baseline (199 Films / 1112 Shots)`, empirical `p50`/`IQR` rows, and `#scoring-guide-modal` HTML/JS delivery.
  - Refreshed `dist/Aesthetic-v0.2.5-windows-x64.zip`.

---

## Next Immediate Step
1. Review working tree (`git diff --stat`) and commit/push on user approval.

---

## Safety & Invariants
- Live production machine: zero system alterations; no unapproved crates.
- Keep `HANDOFF.md` under 50 lines; `AGENTS.md` under 12,000 characters.
