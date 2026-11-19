# AESTHETIC — Development Handoff

## Repository & State
- **Repository**: electrichobo/AestheticApp @ `main` (latest pushed release tag `v0.2.5`)
- **Architecture**: Rust Core Engine (Ground-Up Rebuild)
- **Active Target**: Windows x64 (Live Production Environment)

---

## Current Status: Auto-Backup, Still-Frame & Additive Baseline Ingest, Browse UI & Live Job Graph
- **Automatic Baseline Backup, Rollback & Additive Engine** (`crates/aesthetic-core/src/baseline_store.rs`):
  - `save_to_dir` uses atomic `.tmp` write-flush-rename; `load_from_dir` strictly errors on malformed `shots.json`/`signatures.json` instead of defaulting empty.
  - `create_backup`, `list_backups`, and `restore_backup` manage snapshots in `assets/baseline_backups/<backup_id>/` (retaining oldest original + 9 newest).
  - `ingest_reference_film`, `ingest_reference_film_shots`, `ingest_reference_still`, `ingest_reference_directory_with_limit`, and unified `scan_and_ingest_golden_baseline` are strictly additive (no destructive `retain` or count overwrites) and support movies, still-frame directories, and single stills.
- **Live Job Status Bar Graph** (`baseline_store.rs`, `pipeline.rs`, `aesthetic-ui/`):
  - Global thread-safe `JobStatusSnapshot` (`get_job_status`, `/api/job_status`) tracks multi-stage bar columns (`JobStageBar`) and `active_task_point` across Baseline Ingest, Pass-1/Pass-2 Video Analysis, and Batch Folder Queue, rendered in `#global-job-bar` and `#ingest-job-graph`.
- **Native Browse Controls & CLI** (`crates/aesthetic-ui/`, `crates/aesthetic-cli/src/main.rs`):
  - Added `Browse Folder` & `Browse File` buttons inside `#server-ingest-modal`, native folder browse on `Open Cached Sidecars Folder`, plus CLI `baseline-backups`, `backup-baseline`, `restore-baseline`, and still-frame additive reporting.
- **Verification & Packaging**:
  - `cargo clippy --workspace --all-targets -- -D warnings`: 0 code warnings; `cargo test --workspace`: 35/35 passed (including `test_baseline_backup_and_restore_cycle` and `test_additive_baseline_stills_and_films_never_replace`); `cargo build --release` clean; `dist/Aesthetic-v0.2.5-windows-x64.zip` refreshed.

---

## Next Immediate Step
1. User review (`git diff --stat`) and explicit approval before `git commit` and `git push`.

---

## Safety & Invariants
- Live production machine: zero system alterations; no unapproved crates.
- Keep `HANDOFF.md` under 50 lines; `AGENTS.md` under 12,000 characters.
