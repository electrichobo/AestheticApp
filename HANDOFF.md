# AESTHETIC — Development Handoff

## Repository & State
- **Repository**: electrichobo/AestheticApp @ `main`
- **Architecture**: Rust Core Engine (Ground-Up Rebuild)
- **Active Target**: Windows x64 (Live Production Environment)

---

## Current Status: Scopes Hardened, Multi-Ethnic Skin Cone, Bulletproof FFmpeg
- **Broadcast Vectorscope & Multi-Ethnic Skin Tone Cone**:
  - Zoomable graticule (click to cycle 1.0×, 2.0×, 2.5×, 4.0×) with 2.5× broadcast gain for natural cinema chroma.
  - Inclusive 48°–66° Skin Tone Cone covering Fitzpatrick I–VI spectrum with central 57° I-line and graduation markers.
- **Bulletproof FFmpeg Inclusion & Path Resolution**:
  - `find_binary` returns absolute, canonicalized paths (UNC prefix stripped), searching executable-adjacent first, repo tools, and system PATH (`where.exe`).
  - Automatic quote/whitespace trimming across backend HTTP routes and frontend dialog inputs.
- **Concurrent UI & Zero-Crash Sidecar Ingest**:
  - Multi-threaded HTTP listener with per-connection worker threads.
  - In-memory frame cache (`cached_frames`) serving companion PNGs in < 0.1ms.
  - Golden Baseline (`assets/baseline`) strictly isolated from user clip sidecars.
- **Verification & Code Audit**:
  - Full code audit completed across all 4 crates (79 metrics, ingest, pipeline, export, UI).
  - All 27 workspace tests pass; zero Clippy warnings (`-D warnings`).

---

## Next Immediate Step
1. **Interactive Verification**: Test `http://127.0.0.1:63513` in browser:
   - Click Vectorscope to cycle zoom levels (1×, 2×, 2.5×, 4×) and inspect Skin Tone Cone (48°–66°).
   - Click "Open Media File" or "Open Cached Sidecars Folder" to verify robust ingest and analysis.

---

## Safety & Invariants
- Live production machine: zero system alterations; no unapproved crates.
- Keep `HANDOFF.md` under 50 lines; `AGENTS.md` under 12,000 characters.
