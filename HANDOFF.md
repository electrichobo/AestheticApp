# AESTHETIC — Development Handoff

## Repository & State
- **Repository**: electrichobo/AestheticApp @ `main`
- **Architecture**: Rust Core Engine (Ground-Up Rebuild)
- **Active Target**: Windows x64 (Live Production Environment)

---

## Current Status: M2 Complete → M3 In Progress
- Protocol initialized: `AGENTS.md`, `CLAUDE.md`, `GEMINI.md`, `START_HERE.md`, `STATUS.md`.
- Workspace crates complete: `aesthetic-models`, `aesthetic-metrics`, `aesthetic-core`.
- 4-Output architecture operational: Tangible 0-100 scores, auto style discovery, raw 79 physics metrics, technical concerns.
- Active picture matte detection: Letterbox/pillarbox auto-crop with native resolution zero-crop pass-through.
- Cut detection: Hard cuts, dissolves, fades, directional wipes, and match cuts.
- Continuous usable window (1.5s - 4.0s) optimizer with handle clamping operational.
- All 8 integration tests passing, zero clippy warnings, rustfmt compliant.

---

## Next Immediate Step (M3: Inference & Baseline Embeddings)
1. **GPU Acceleration**: Implement vendor-agnostic DirectML execution (supporting NVIDIA, AMD/ATI, Intel).
2. **Scaffold Model Inference Module**: Integrate SigLIP (1152-dim embeddings) and Depth-Anything-V2 ONNX models into `aesthetic-core`.
3. **Golden Baseline Corpus Store**: High-speed binary storage and Cosine Similarity search against ingested reference films (*Skyfall*, etc.).
4. **Cinematographer Fingerprint Matching**: Distance clustering against named master DP signatures.

---

## Safety & Invariants
- Live production machine: never install software/services/Docker; no system changes.
- Never add a crate without explicit user approval.
- Keep `HANDOFF.md` under 50 lines; `AGENTS.md` under 12,000 characters.
- Commit/push only when requested by the user.
