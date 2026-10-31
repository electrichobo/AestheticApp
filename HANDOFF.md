# AESTHETIC — Development Handoff

## Repository & State
- **Repository**: electrichobo/AestheticApp @ `main`
- **Architecture**: Rust Core Engine (Ground-Up Rebuild)
- **Active Target**: Windows x64 (Live Production Environment)

---

## Current Status: M9 (EL Zone Exposure & Pretrained Baseline Integration)
- Ed Lachman, ASC EL Zone System: 10-stop calibrated false color engine (18% Middle Gray Zone V = 0 EV).
- Pretrained Shipped Baseline: 174 calibrated reference shots across 58 Master Cinematographers active out-of-the-box.
- Brand Assets & In-App UI: Wide header branding and viewport diagnostic toolbar for forensic overlays.
- 22/22 tests passing, zero clippy warnings, rustfmt compliant.

---

## Next Immediate Step (In-App Showreel Assembly & Forensic Overlays)
1. **Frontend Interactivity & Styling**: Complete Stage 1 showreel assembly (candidate scrubbing & handle trimming) and Stage 2 forensic overlays (EL Zone, focus peaking, 3D light vector compass, eyeline/gaze grid) in `app.css` & `app.js`.
2. **End-to-End Verification**: Verify `/api/frame_el_zone`, `/api/frame_peaking`, and `/api/selects` headless UI endpoints.
3. **Packaging Hold**: Hold release packaging until full functional verification is approved.

---

## Safety & Invariants
- Live production machine: never install software/services/Docker; no system changes.
- Never add a crate without explicit user approval.
- Keep `HANDOFF.md` under 50 lines; `AGENTS.md` under 12,000 characters.
- Commit/push only when requested by the user.
