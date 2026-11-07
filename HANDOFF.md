# AESTHETIC — Development Handoff

## Repository & State
- **Repository**: electrichobo/AestheticApp @ `main`
- **Architecture**: Rust Core Engine (Ground-Up Rebuild)
- **Active Target**: Windows x64 (Live Production Environment)

---

## Current Status: M31 Viewport Shaders & M32 Unified Deliverables Package (v0.1.0-alpha)
- **Standalone Distribution ZIP**: `dist/Aesthetic-v0.1.0-windows-x64.zip` packaged and ready to run with adjacent `ffmpeg.exe` and Golden Baseline corpus.
- **M31: Viewport Forensic Diagnostic & False Color Shaders**:
  - `compute_focus_peaking_map`: Multi-threaded Rayon Laplacian & Sobel edge detector highlighting in-focus planes with neon green (`#00ff80`) on desaturated bases (`/api/frame_peaking`).
  - `compute_el_zone_map`: Calibrated Ed Lachman, ASC 10-stop false-color exposure raster (`/api/frame_el_zone`).
  - Interactive Viewport Overlays: 3D volumetric light vector sphere (key/fill azimuth & contrast ratio) and eyeline Rule-of-Thirds grid with directional gaze corridor.
- **M32: Unified Deliverables ZIP Export Packaging**:
  - `build_unified_deliverables_package`: Pure Rust zero-dependency PKZIP 2.0 generator packaging `EDL/`, `XML/`, `Scripts/`, `Reports/`, `ContactSheet/`, `Grades/` (ASC CDL & 3D LUT .cube), and `Stills/` into a single-click archive (`/api/export_package`).
  - UI integration: Primary `[Export Deliverables Package (.ZIP)]` in Export dropdown.
  - CLI integration: `--package [dir]` flag in `aesthetic-cli analyze`.
- **Quality & Invariants**:
  - 31/31 workspace tests passing (`cargo test --workspace`).
  - Zero Clippy warnings (`cargo clippy --workspace -- -D warnings`).
  - Standalone release binaries built (`aesthetic-ui.exe`, `aesthetic-cli.exe`).
  - Offline local execution; zero external internet access; production invariant preserved.

---

## Next Immediate Step
1. **Interactive Verification**: Refresh `http://127.0.0.1:63513`:
   - Toggle "EL Zone", "Peaking", "3D Light", and "Eyeline & Gaze" buttons in Viewport toolbar.
   - Click "Export" -> "Export Deliverables Package (.ZIP)" to download complete deliverables archive.
2. Tag release `v0.1.0-alpha`.

---

## Safety & Invariants
- Live production machine: zero system alterations; no unapproved crates.
- Keep `HANDOFF.md` under 50 lines; `AGENTS.md` under 12,000 characters.
