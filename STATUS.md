# AESTHETIC — Development Status

## Current Milestone: M3 — Inference & Baseline Embeddings
- **Phase**: Ground-Up Rebuild in Rust
- **Target**: Windows x64 (primary), Linux, macOS
- **Active Focus**: ONNX/DirectML inference runtime, Depth-Anything-V2, SigLIP 1152-dim embeddings, Golden Baseline reference store.

---

## Milestone Roadmap

| Milestone | Scope | Status | Notes |
| :--- | :--- | :---: | :--- |
| **M0: Protocol & Clean Rebuild** | Protocol initialization, AGENTS.md, HANDOFF.md, purge legacy Python code | ✅ Done | Clean Rust Cargo workspace established |
| **M1: Data Models & Objective Metrics** | `aesthetic-models`, `aesthetic-metrics` (SIMD/rayon exposure, optics, color physics) | ✅ Done | Pure Rust math verified with passing unit tests |
| **M2: Temporal Engine & Windowing** | `aesthetic-core` video probe, transition cut detection, 1.5s-4.0s window optimizer, active matte detection | ✅ Done | 4-Output architecture implemented & tested |
| **M3: Inference & Baseline Embeddings** | ONNX/DirectML runtime, SigLIP visual embeddings, Depth-Anything-V2, reference corpus clustering | 🔄 In Progress | Moving from mathematical physics to perceptual craft |
| **M4: CLI Driver & Packaging** | `aesthetic-cli`, benchmark harness, standalone Windows binary | 🔲 Planned | Full pipeline headless verification |
| **M5: Desktop UI Integration** | High-performance desktop UI (scopes, timeline scrub, sidecar metadata) | 🔲 Planned | Native UI bound to Rust core engine |

---

## Completed in M2
- Scaffolded `crates/aesthetic-core` as a high-performance orchestration engine.
- Implemented **Active Picture Area (Matte) Detection** (`detect_active_picture`) to auto-crop letterbox/pillarbox bars while natively passing through native aspect ratio files with zero cropping.
- Built **Transition & Cut Detector** (`compute_frame_difference`, `detect_directional_wipe`, `classify_transition`) classifying hard cuts, dissolves, fades, directional wipes, and match cuts.
- Multi-GPU strategy defined: DirectML for vendor-agnostic hardware acceleration across NVIDIA, AMD/ATI, and Intel on Windows.
- Built **Sliding Window Optimizer** (`find_best_usable_window`) finding optimal 1.5s - 4.0s takes and clamping handles to cut boundaries.
- Built **Automatic Style Discovery** (`evaluate_candidate_frame`) classifying lighting key (High-Key, Mid-Key, Low-Key) without manual user presets.
- Built **Empirical Quantile Calibration** (`MetricQuantiles`) converting raw physical values into tangible 0.0 - 100.0 percentile scores.
- Comprehensive integration testing: 7/7 tests passing across the workspace. Zero clippy warnings.
