# Design Document

## Why This Project

Energy profiling tools are either hardware-based (power monitors) or runtime-based (RAPL, perf). Both require the program to actually run. This pass exists to give developers a quick, no-setup estimate of which parts of their code are energy-heavy without needing special hardware or running the program.

## Architecture

```
Source → LLVM IR → EnergyPass → Terminal + JSON + HTML
            │
       BFI (block frequencies)
       JSON model (opcode costs)
       DebugLoc (source line mapping)
```

The pass iterates each function, gets block frequencies from BFI, looks up instruction costs from the JSON model, and accumulates `cost × frequency` per block, per opcode, and per source line. After processing, hotspots are sorted and advisory rules are checked.

The pipeline has three stages:
1. **IR Processing** — Each function is visited by the pass. Block frequencies are obtained from LLVM's Block Frequency Info (BFI) analysis pass. For every instruction, the opcode name is used as a key to look up an energy cost in a JSON model file.
2. **Aggregation** — Energy is accumulated at three levels: per basic block, per opcode category, and per source line (using `DebugLoc`). This produces a multi-resolution picture of energy distribution.
3. **Reporting** — Results are printed to terminal (function summary, hotspot table, instruction breakdown), written to a JSON file for programmatic consumption, and rendered into a self-contained HTML report with a source code heatmap.

## Design Decisions

**Static analysis over dynamic measurement.** No runtime needed. Same input always produces same numbers. Downside: BFI frequencies are heuristic, energy is relative.

**Legacy pass manager.** Simpler to set up for a single-pass tool. LLVM 14 supports both legacy and new PM.

**JSON energy model.** Adding opcodes doesn't need recompilation. Different architectures can use separate files. LLVM has built-in JSON support.

**Block frequency weighting.** A loop body with 5 instructions running 1000 iterations matters more than 20 instructions in a prologue block.

**Relative energy (unitless).** Absolute energy depends on CPU, voltage, temperature. Relative costs transfer across microarchitectures.

**DebugLoc for source mapping.** The debug info already maps back to source lines. Zero extra setup with `-g`.

**Three-level accumulation.** Block, opcode, and source-line granularity covers most developer questions: "which function/block/line is hot?"

## Alternatives Considered

**LLVM MachineInstr pass.** Would give actual target instructions, but requires a specific backend and runs late in the pipeline. Not portable across architectures.

**Python-based IR parser.** Could parse LLVM IR text directly, but that's fragile across LLVM versions and duplicates BFI logic already available in the C++ API.

**Runtime instrumentation (perf/RAPL).** Accurate hardware-level measurement, but requires running the program, specific hardware support, and is not portable across platforms.

**Hardcoded cost table in C++.** No external file needed, but every change requires recompilation and the table would be buried in source.

**New pass manager.** More modern API, but more boilerplate and dependency requirements for a simple analysis pass.