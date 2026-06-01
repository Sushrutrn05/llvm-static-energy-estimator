# Design Document

## Problem Statement

Modern software energy consumption is a growing concern in data centers, embedded systems, and battery-powered devices. Developers lack tooling to understand **which parts of their code consume the most energy** at the instruction level. Existing profiling tools measure time, not energy, and hardware power monitors require specialized equipment.

We need a **static analysis framework** that:
1. Estimates relative energy consumption from LLVM IR without running the program
2. Identifies energy hotspots at function, block, and source-line granularity
3. Provides actionable optimization suggestions
4. Integrates into existing CI/developer workflows

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                   C/C++ Source Code                      │
└──────────────────────┬──────────────────────────────────┘
                       │ clang -S -emit-llvm -g
                       ▼
┌─────────────────────────────────────────────────────────┐
│                   LLVM IR (.ll)                          │
│              (with debug metadata)                       │
└──────────────────────┬──────────────────────────────────┘
                       │ opt -load EnergyPass.so
                       ▼
┌─────────────────────────────────────────────────────────┐
│                EnergyPass (FunctionPass)                  │
│                                                          │
│  ┌─────────────┐  ┌──────────────┐  ┌────────────────┐   │
│  │ Block       │  │ Opcode       │  │ Source Line     │   │
│  │ Frequency   │  │ Energy       │  │ Accumulator     │   │
│  │ (BFI)       │  │ Lookup       │  │ (DebugLoc)      │   │
│  └──────┬──────┘  └──────┬───────┘  └───────┬────────┘   │
│         │                │                   │            │
│         ▼                ▼                   ▼            │
│  ┌──────────────────────────────────────────────────┐    │
│  │              Energy Aggregator                    │    │
│  │  Per-block · Per-function · Per-source-line       │    │
│  └──────────────────────┬───────────────────────────┘    │
│                         │                                │
│                         ▼                                │
│  ┌──────────────────────────────────────────────────┐    │
│  │    Analysis Pipeline                              │    │
│  │  ┌─────────┐  ┌──────────┐  ┌─────────────────┐  │    │
│  │  │Hotspot  │  │Optim.    │  │Source Heatmap    │  │    │
│  │  │Detector │  │Advisor   │  │Generator         │  │    │
│  │  └────┬────┘  └────┬─────┘  └───────┬─────────┘  │    │
│  └───────┼────────────┼────────────────┼────────────┘    │
└──────────┼────────────┼────────────────┼─────────────────┘
           │            │                │
           ▼            ▼                ▼
┌─────────────────────────────────────────────────────────┐
│                   Outputs                                 │
│  ┌────────────┐  ┌──────────┐  ┌────────────────────┐    │
│  │Terminal    │  │JSON      │  │HTML Dashboard       │    │
│  │(stdout)    │  │Report    │  │(via visualize.py)   │    │
│  └────────────┘  └──────────┘  └────────────────────┘    │
│  ┌──────────────────────────────────────────────────┐    │
│  │Optimization Remarks (via OptimizationRemarkEmitter)│   │
│  └──────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────┘
```

### Data Flow

1. **LLVM IR Input** — The pass receives a compiled `.ll` file with `-g` debug metadata
2. **Block Frequency Analysis** — BFI provides execution frequency estimates for each basic block, normalized against the function entry frequency
3. **Instruction Iteration** — Each instruction is classified by opcode, looked up in the energy model, and its contribution is `cost × normalized_frequency`
4. **Three Accumulators** — Energy is accumulated per-block, per-opcode (for breakdown), and per-source-line (via DebugLoc)
5. **Analysis Pipeline** — Hotspots are computed (sorted descending), optimization advisories are generated (rule-based thresholds), and source line data is prepared
6. **Output Generation** — Terminal output is formatted, JSON report is serialized, and the Python script generates the HTML dashboard

## Design Decisions

### 1. Static Analysis vs. Dynamic Measurement

**Decision:** Static analysis on LLVM IR.

**Rationale:**
- No runtime overhead — can analyze any program path
- Works with cross-compilation — no target hardware needed
- Reproducible — same IR always produces same results
- CI-friendly — integrates with existing compilation pipelines

**Trade-off:** Block frequency estimation relies on heuristics (branch probabilities) rather than actual execution profiles. Energy costs are relative, not absolute.

### 2. Legacy Pass Manager vs. New PM

**Decision:** Legacy pass manager (`-enable-new-pm=0`).

**Rationale:**
- LLVM 14 ships with both PMs; legacy PM is simpler for single-purpose passes
- No need for pass pipeline integration complexities
- `RegisterPass` static registration is straightforward

### 3. JSON Energy Model vs. Hardcoded Costs

**Decision:** External JSON file loaded via `doInitialization()`.

**Rationale:**
- Users can add new opcodes without recompiling the pass
- Different architectures (ARM, RISC-V) can have separate model files
- JSON parsing uses LLVM's built-in `llvm/Support/JSON.h` — no external dependencies
- Model validation can be done separately from the pass

### 4. Block Frequency Weighting

**Decision:** Use `BlockFrequencyInfo` for weighted energy, not simple instruction count.

**Rationale:**
- Loop bodies execute many times — unweighted counts underestimate their contribution
- BFI provides LLVM's best static frequency estimate using branch probabilities and loop trip counts
- Enables hotspot detection that correctly prioritizes hot loop bodies over cold prologue code

### 5. Relative vs. Absolute Energy

**Decision:** Report relative energy (unitless, normalized to `add = 1.0`).

**Rationale:**
- Absolute energy depends on hardware, voltage, frequency, and process node
- Relative costs are portable across microarchitectures (mul is always more expensive than add)
- Users can calibrate against real measurements by measuring a reference program

### 6. Source Heatmap via Debug Metadata

**Decision:** Use DWARF debug info (`DebugLoc`), not a separate source parser.

**Rationale:**
- No need for a C preprocessor or parser
- Direct mapping from IR instructions to source lines via existing LLVM infrastructure
- Handles inlining, macro expansion, and header files correctly
- Zero additional setup — just compile with `-g`

## Alternatives Considered

### Alternative 1: LLVM MachineInstr Pass (Post-ISel)

**Rejected because:**
- Requires a target backend (X86, ARM, etc.) — not portable
- Machine instructions are target-specific and much more numerous
- Pass runs later in the pipeline, making integration harder
- Would need separate implementations for each target

### Alternative 2: Dynamic Binary Instrumentation (Pin/Valgrind)

**Rejected because:**
- Requires the program to run to completion — not suitable for all code
- Runtime overhead of 2-10×
- Cannot analyze compilation errors or unreachable code
- Requires the target hardware or emulator

### Alternative 3: External Energy Estimation Tool (e.g., pTop, PowerAPI)

**Rejected because:**
- These tools measure system-level power, not per-function granularity
- Require running the program and monitoring in real time
- No source-level attribution
- Limited to x86 Linux

### Alternative 4: Hardcoded Cost Table in C++

**Rejected because:**
- Adding new opcodes requires recompilation
- No easy way to support multiple target architectures
- Mixing data and code violates separation of concerns
- Testing model updates requires rebuilding the pass

### Alternative 5: Separate Python Analyzer (parsing LLVM IR text)

**Rejected because:**
- Duplicates LLVM's analysis infrastructure (BFI, loop analysis)
- Slow for large IR files
- Fragile — LLVM IR text format changes between versions
- Cannot use LLVM's optimization remark system
