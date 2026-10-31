# AESTHETIC — Development Handoff

## Repository & State
- **Repository**: electrichobo/AestheticApp @ `main`
- **Architecture**: Rust Core Engine (Ground-Up Rebuild)
- **Active Target**: Windows x64 (Live Production Environment)

---

## Current Status: M10 (Stage 1 Showreel Assembly & Stage 2 Forensic Overlays)
- Ed Lachman, ASC EL Zone System: 10-stop calibrated false color engine (18% Middle Gray Zone V = 0 EV).
- Pretrained Shipped Baseline: 174 calibrated reference shots across 58 Master Cinematographers active out-of-the-box.
- Stage 1 Showreel Selects Assembly: Dynamic candidates bin, interactive In/Out timeline handle trimming, one-click export (EDL, FCPXML, CSV, contact sheet).
- Stage 2 Forensic Overlays: Real-time toggling between Picture, EL Zone false color heatmap, Focus Peaking, 3D Volumetric Light compass, and Eyeline & Gaze poise HUD.
- 22/22 tests passing, zero clippy warnings, verified on local loopback server.

---

## Next Immediate Step (User Verification & Release Readiness)
1. **Interactive Review**: Review candidate takes, EL Zone false color heatmaps, and 3D light vector HUD in UI.
2. **Release Preparation (On User Approval)**: When user is fully satisfied with feature behavior, proceed with standalone distribution packaging.

---

## Safety & Invariants
- Live production machine: never install software/services/Docker; no system changes.
- Never add a crate without explicit user approval.
- Keep `HANDOFF.md` under 50 lines; `AGENTS.md` under 12,000 characters.
- Commit/push only when requested by the user.
