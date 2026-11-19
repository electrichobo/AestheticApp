# AESTHETIC — Development Handoff

## Repository & State
- **Repository**: electrichobo/AestheticApp @ `main` (pushed `20f084f`, tagged `v0.2.5` at `a92c70a`)
- **Architecture**: Rust Core Engine (Ground-Up Rebuild)
- **Active Target**: Windows x64 (Live Production Environment)

---

## Current Status: Multi-Format Stills, E2E Verified Server & Docs Synced
- **Multi-Format Still-Image Decoding (`crates/aesthetic-core/src/video.rs`, `baseline_store.rs`, `aesthetic-ui/src/main.rs`)**:
  - Added `decode_still_image_rgb` trying fast native PNG/JPEG decode with automatic bundled FFmpeg (`image2pipe` -> PNG) fallback for `.tiff`, `.tif`, `.webp`, `.bmp`, `.exr`, and 16-bit stills without adding unapproved crates.
  - Wired across `ingest_reference_still`, `ingest_reference_directory_with_limit`, UI `/api/open_media`, `/api/analyze` (updating `#global-job-bar`), and `get_or_extract_frame`.
- **Verification (All Checks Run Cleanly)**:
  - `cargo clippy --workspace --all-targets -- -D warnings`: 0 code warnings.
  - `cargo test --workspace`: 36/36 passed (including `test_decode_still_image_tiff_and_bmp_fallback`, `test_additive_baseline_stills_and_films_never_replace`, and `test_baseline_backup_and_restore_cycle`).
  - `cargo build --release`: clean; isolated headless `aesthetic-ui.exe --headless --port 63529` E2E test verified static assets, `/api/baseline_backups`, `/api/backup_baseline`, additive PNG+TIFF `/api/ingest_server` (`1112 + 2 = 1114`), `/api/job_status` (`Complete 100.0%`), TIFF `/api/analyze`, and `/api/restore_baseline` rollback back to `1112`.
- **Docs & Packaging Sync**:
  - Updated `README.md` & `STATUS.md` (added M33 & M34), updated `README_RELEASE.txt`, and refreshed `dist/Aesthetic-v0.2.5-windows-x64.zip`.

---

## Next Immediate Step
1. Review working tree (`git status -s` / `git diff --stat`) and commit/push on user approval (plus optional new tag e.g. `v0.2.6`).

---

## Safety & Invariants
- Live production machine: zero system alterations; no unapproved crates.
- Keep `HANDOFF.md` under 50 lines; `AGENTS.md` under 12,000 characters.
