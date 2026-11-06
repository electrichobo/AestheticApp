# AESTHETIC — Development Handoff

## Repository & State
- **Repository**: electrichobo/AestheticApp @ `main`
- **Architecture**: Rust Core Engine (Ground-Up Rebuild)
- **Active Target**: Windows x64 (Live Production Environment)

---

## Current Status: Vectorscope I-Line Calibrated to 10:30 Position
- **Broadcast Skin Tone I-Line Positioned at 10:30 (123.0°)**:
  - Rotated 33° counter-clockwise from the +V (90°) axis into Quadrant II between Red (104°) and Yellow (167°), matching the exact NTSC/Rec.709 I-axis ($I = -0.27(B-Y) + 0.74(R-Y)$).
  - Aligned with the ~10:30 clock face position with graduation markers at 25%, 50%, and 75% saturation ticks and a ±2.5° broadcast tolerance guide.
  - Removed wide multi-ethnic cone shading in favor of the uniform human skin tone locus.
- **Dynamic Asset Serving & Bulletproof FFmpeg**:
  - Live asset reloading on disk with embedded `include_str!` fallback.
  - Absolute canonical path resolution with automated quote/whitespace sanitization.
- **Verification**:
  - All 27 workspace tests passing (`cargo test --workspace`).
  - Zero Clippy warnings (`-D warnings`).

---

## Next Immediate Step
1. **Interactive Verification**: Refresh `http://127.0.0.1:63513` in browser:
   - Inspect the Vectorscope tab to verify the golden I-Line sits at 10:30 between Red and Yellow.
   - Click canvas to test zoom cycles (1.0×, 2.0×, 2.5×, 4.0×).

---

## Safety & Invariants
- Live production machine: zero system alterations; no unapproved crates.
- Keep `HANDOFF.md` under 50 lines; `AGENTS.md` under 12,000 characters.
