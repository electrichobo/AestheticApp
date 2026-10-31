# START HERE — AESTHETIC Developer Guide

Welcome to **AESTHETIC**. This repository hosts the ground-up rebuild of AESTHETIC as a high-performance **Rust Core Engine** targeting Windows x64 first, followed by Linux and macOS.

---

## 1. Prerequisites
- **Rust Toolchain**: 1.80+ (Installed at `~/.cargo/bin/`)
  - Verify with: `cargo --version` and `rustc --version`
- **FFmpeg**: Required on PATH or bundled in `tools/` for video decode/demux.
- **Hardware Acceleration**: Vendor-agnostic GPU acceleration for NVIDIA GeForce/RTX, AMD/ATI Radeon, and Intel Arc/Iris Xe via DirectML (Windows) and Vulkan/Metal (Linux/macOS); CPU fallbacks provided for all core metrics.

---

## 2. Rebuild Architecture
The ground-up Rust architecture is structured as a Cargo workspace:
- `crates/aesthetic-models`: Core data contracts, score models, timeline intervals, candidate definitions.
- `crates/aesthetic-metrics`: Objective physics, SIMD color/exposure/sharpness algorithms, optical flow proxies.
- `crates/aesthetic-core`: Video ingest pipeline, scene & transition analysis, window scoring, clustering, and export.
- `crates/aesthetic-cli`: Headless CLI driver for benchmarking, testing, and batch analysis.

---

## 3. Five-Layer Metric Philosophy
Unlike naive frame-average scorers, AESTHETIC evaluates cinema across five distinct layers:
1. **Objective Physics**: Precise pixel mathematics (false color zones, highlight roll-off gradients, true dynamic range).
2. **Model-Inferred Craft**: Staging, gaze vectors, depth layering, focus pulls, and camera vs. subject movement.
3. **Subjective & Aesthetic**: Perceptual narrative appeal, visual tension, and style-family baseline affinity.
4. **Temporal & Editorial**: Sustained quality windows, move-settle stability, entry/exit trim quality, and visual fatigue.
5. **Forensic Diagnostics**: Non-punitive flags (flicker, dead pixels, sensor dust, rolling shutter wobble) that guide the editor without depressing creative scores.

---

## 4. Build & Test Commands
```powershell
# Build all workspace crates
cargo build

# Run unit and integration tests
cargo test

# Check formatting and lints
cargo fmt --check
cargo clippy --all-targets -- -D warnings
```
