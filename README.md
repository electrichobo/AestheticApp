# AESTHETIC

AESTHETIC is a local desktop application and high-performance video intelligence engine designed for cinematographers and editors. It analyses raw footage, finds the strongest candidate shots and continuous usable sequences, and exports hero stills, trimmed clips, contact sheets, EDLs, and scoring diagnostics — comparing cuts against a Golden Baseline of award-winning cinema.

It runs entirely locally on your machine: no external servers, no cloud APIs, zero subscription overhead.

---

## The Ground-Up Rust Rebuild

AESTHETIC is currently undergoing a complete ground-up rebuild as a **Rust Core Engine**, prioritizing:
1. **Computational Speed & Multi-GPU**: Multi-threaded SIMD pixel pipelines for real-time video evaluation with vendor-agnostic hardware acceleration (DirectML for NVIDIA, AMD/ATI, Intel on Windows; Metal/Vulkan on macOS/Linux).
2. **Deterministic Objective Physics**: Exact mathematical measurements across false-color exposure zones, highlight roll-off curves, true dynamic range stops, MTF spatial frequencies, and optical metrics.
3. **Temporal Take Intelligence**: Evaluating sustained usable-window intervals, move-settle stability, and edit trim points rather than naive single-frame averaging.
4. **Clean Separation of Concerns**: Strict boundary between objective physical measurements, model-inferred staging, subjective preference, temporal editorial quality, and non-punitive forensic diagnostics.
5. **Cross-Platform Target**: Windows x64 first, with direct portability to Linux and macOS.

---

## Documentation & Governance

| Document | Purpose |
| :--- | :--- |
| [AGENTS.md](AGENTS.md) | Agent takeover protocol, live machine safety rules, and workspace invariants |
| [START_HERE.md](START_HERE.md) | Developer quickstart, Cargo workflow, and build instructions |
| [STATUS.md](STATUS.md) | Active milestone tracker and rebuild roadmap |
| [HANDOFF.md](HANDOFF.md) | Current session state and immediate next step baton |
| [docs/AESTHETIC_Metrics.md](docs/AESTHETIC_Metrics.md) | Complete mathematical specification for all metric calculations |

---

## Rebuild Roadmap & Progress

| Milestone | Description | Status |
| :--- | :--- | :---: |
| **M0: Protocol & Rebuild Setup** | Repository protocol initialization, legacy Python purge, clean Rust workspace | ✅ Done |
| **M1: Data Models & Objective Metrics** | `aesthetic-models`, `aesthetic-metrics` (SIMD exposure, color, focus, sharpness) | ✅ Done |
| **M2: Temporal Engine & Usable Windows** | `aesthetic-core` video demux, cut classification, continuous take evaluation | ✅ Done |
| **M3: Baseline Vector Store & DP Match** | `BaselineStore` vector similarity, master DP fingerprint matching, empirical calibration | ✅ Done |
| **M4: Headless CLI & Benchmark Harness** | `aesthetic-cli`, 4K SIMD physics benchmark (1.70s 4K pass), demo take evaluation | ✅ Done |
| **M5: Desktop UI Integration** | High-performance desktop UI (waveform, parade, CIE scopes, timeline scrub) | 🔄 In Progress |

---

## Five Evaluation Layers

1. **Objective Physics**: Mathematical pixel analysis (exposure zones, highlight roll-off gradients, true dynamic range stops, MTF/spatial frequency, SNR).
2. **Model-Inferred Craft**: Deep perception (lighting geometry/key-fill azimuth, 3D depth separation, gaze vectors, focus breathing/hunting, camera movement vs subject movement).
3. **Subjective & Aesthetic**: Perceptual narrative appeal (compositional balance, silhouette readability, tension, style-family cluster similarity).
4. **Temporal & Editorial**: Video in motion (usable-window duration, move-settle quality, cut-point stability, visual fatigue index across edits).
5. **Forensic Diagnostics**: Non-punitive technical flags (sensor dust, flickering practicals, rolling shutter wobble, clipping persistence, dead pixels). These provide warnings and metadata without blindly penalizing artistic intent.
