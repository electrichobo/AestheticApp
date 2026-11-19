# AESTHETIC — Development Handoff

## Repository & State
- **Repository**: electrichobo/AestheticApp @ `main`
- **Architecture**: Rust Core Engine (Ground-Up Rebuild)
- **Active Target**: Windows x64 (Live Production Environment)

---

## Current Status: Exhaustive Scene Scanner, Title Card Elimination & Top-N Control
- **Multi-Signal Title Card & Credits Elimination** (`pipeline.rs`, `export.rs`):
  - `detect_title_card_or_graphic` + `is_proxy_title_card_or_blank`: 4-corner bilinear background fitting + horizontal typography row detection across dark, white, colored, and gradient backdrops, avoiding low-key chiaroscuro false positives.
  - `apply_reel_diversity_ranking` & `rescore_from_sidecars`: Completely strip title cards when photographic footage exists and prioritize unrepresented scenes (`+10` diversity weight).
- **Exhaustive Two-Pass Scene-by-Scene Scanner** (`video.rs`, `scene.rs`, `pipeline.rs`):
  - Pass 1 (`scan_video_scenes`): Single fast `160x90` FFmpeg rawvideo stream across 100% of timeline detecting shot boundaries, stripping title cards, and grouping shots into photographic scenes.
  - Pass 2 (`analyze_video_file`): Concurrent 4-worker full-res evaluation guaranteeing every photographic scene gets evaluated.
- **User-Configurable Top N** (`ui/index.html`, `app.js`, `main.rs`, `aesthetic-cli`):
  - Header `Top N` input + `All` button with live `/api/set_top_n` re-slicing (no re-decode), `localStorage` persistence, and `-n / --top` CLI flag (`0 = All`).
- **Verification & Distribution**:
  - JS syntax check: OK; `cargo test --workspace`: 33/33 passed; `cargo clippy --workspace --all-targets -- -D warnings`: 0 warnings.
  - Release binaries & standalone ZIP refreshed at `dist/Aesthetic-v0.1.0-windows-x64.zip`.

---

## Next Immediate Step
1. User review of changes (`git diff --stat`) and commit/push on explicit approval.
2. Interactive verification via `Start_Aesthetic.bat` / `http://127.0.0.1:63513` with multi-scene video + `Top N` controls.

---

## Safety & Invariants
- Live production machine: zero system alterations; no unapproved crates.
- Keep `HANDOFF.md` under 50 lines; `AGENTS.md` under 12,000 characters.
