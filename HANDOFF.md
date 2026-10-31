# AESTHETIC — Development Handoff

## Repository & State
- **Repository**: electrichobo/AestheticApp @ `main`
- **Architecture**: Rust Core Engine (Ground-Up Rebuild)
- **Active Target**: Windows x64 (Live Production Environment)

---

## Current Status: M5 (58 Master Cinema Signatures & Automated Baseline Ingest)
- Protocol initialized: `AGENTS.md`, `CLAUDE.md`, `GEMINI.md`, `START_HERE.md`, `STATUS.md`.
- Workspace crates complete: `aesthetic-models`, `aesthetic-metrics`, `aesthetic-core`, `aesthetic-cli`, `aesthetic-ui`.
- 58 Master DP Signatures: 50 masters specified by user + 8 canonical masters (Nykvist, Lubezki, Willis, Vierny, Storaro, Nakai, Doyle, Rotunno, Deakins, Alcott, Toland, Idziak, Zsigmond, Atsuta, Richardson, Burks, Coutard, Metty, Yeoman, Chapman, Di Venanzo, Matras, Delli Colli, Urusevsky, Young, Elswit, Miyagawa, Hoch, Maté, Cardiff, Martelli, Fischer, Delbonnel, Müller, Ballhaus, Kamiński, Garmes, Tovoli, Decaë, di Palma, Tisse, Prieto, Suschitzky, Unsworth, Lang, Krasker, Khondji, Almendros, Ping-Bing, van Hoytema, Fraser, Dryburgh, Hall, Deschanel, Dod Mantle, Mukdeeprom, Libatique, Kuras).
- Automated Baseline Ingest: `ingest_reference_film` and `aesthetic-cli ingest-baseline` break down full films to continuously grow dataset and recalibrate quantiles.
- End-to-End Batch Engine: `analyze_video_file` demuxes, evaluates 4 outputs, matches masters, and exports CMX 3600 EDL, CSV manifest, and trimmed clips.
- 5 Broadcast Scopes Deck: Luma Waveform, RGB Parade, Vectorscope (57° I-line), Histograms, CIE 1931 xy Gamut.
- Real-Time Scrub & Pipeline: Interactive timeline scrubber wired to frame demuxing and 4-output matrix updates.
- Inference Engine: Depth-Anything-V2 depth separation & SigLIP 1152-dim vision embeddings with DirectML acceleration.
- All 16 integration tests passing, zero clippy warnings, rustfmt compliant.

---

## Next Immediate Step (M5 Validation & Release Packaging)
1. **Validation & Verification**: Run batch probe on local reference mezzanine media or YouTube URL.
2. **Release Build Optimization**: Verify `--release` artifacts for `aesthetic-cli` and `aesthetic-ui`.

---

## Safety & Invariants
- Live production machine: never install software/services/Docker; no system changes.
- Never add a crate without explicit user approval.
- Keep `HANDOFF.md` under 50 lines; `AGENTS.md` under 12,000 characters.
- Commit/push only when requested by the user.
