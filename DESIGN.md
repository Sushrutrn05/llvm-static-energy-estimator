# Design Document

## Why This Project

Energy profiling tools are either hardware-based (power monitors) or
runtime-based (RAPL, perf). Both require the program to actually run. This
pass exists to give developers a quick, no-setup estimate of which parts of
their code are energy-heavy without needing special hardware or running the
program.

The tool targets the common developer workflow:

1. Write or modify C/C++ code.
2. Get a fast signal of which functions, blocks, and source lines are
   expensive *without* executing the binary.
3. Decide where to focus optimization effort.

It is a **static, relative** profiler — it answers "where is the energy
budget going?" rather than "how many joules did this program consume?".

## Architecture

### High-Level Pipeline

```
   ┌─────────┐    ┌──────────────┐    ┌──────────────┐    ┌──────────────┐
   │  C src  │ →  │  LLVM IR     │ →  │  EnergyPass  │ →  │ Terminal +   │
   │ (clang) │    │ (.ll, -g)    │    │  (this tool) │    │ JSON + HTML  │
   └─────────┘    └──────────────┘    └──────────────┘    └──────────────┘
                                          │
                                          ├── BlockFrequencyInfo (BFI)
                                          │     (loop trip counts, branch probs)
                                          │
                                          ├── OpcodeEnergy model (JSON)
                                          │     (per-opcode relative cost)
                                          │
                                          └── DebugLoc
                                                (instruction → source line)
```

The pass sits between the LLVM IR producer (`clang -emit-llvm`) and any
downstream pass manager consumer (the JSON/HTML reports and the terminal
table). It does not modify the IR — it only reads it.

### Pass Internals

```
   doInitialization(Module&)
     └── Load energy model JSON
          └── json::parse → std::unordered_map<string, double>

   runOnFunction(Function&)        ← once per function
     ├── Get BFI + ORE analyses
     ├── For each basic block:
     │    ├── NormalizedFreq = BFI.getBlockFreq() / BFI.getEntryFreq()
     │    ├── For each instruction I:
     │    │    ├── cost = OpcodeEnergy[I.getOpcodeName()]   (default 1.0)
     │    │    ├── block_energy  += cost × NormalizedFreq
     │    │    ├── opcode_class  += cost × NormalizedFreq
     │    │    └── if (DebugLoc DL = I.getDebugLoc())
     │    │         line_energy[DL.getLine()] += cost × NormalizedFreq
     │    └── emit per-block optimization remark
     ├── Compute hotspots: sort blocks desc, take top 3
     ├── Compute advisories: rule scan over opcode percentages
     ├── Print per-function summary table
     └── return false                                   (read-only pass)

   doFinalization(Module&)
     └── Serialize AllReports to JSON via raw_fd_ostream
```

### Three Pipeline Stages

1. **IR Processing.** Each function is visited by the pass. Block frequencies
   are obtained from LLVM's Block Frequency Info (BFI) analysis pass. For
   every instruction, the opcode name is used as a key to look up an energy
   cost in a JSON model file.

2. **Aggregation.** Energy is accumulated at three levels:
   - per basic block (the hotspot unit)
   - per opcode category (the advisor unit)
   - per source line via `DebugLoc` (the heatmap unit)

   This produces a multi-resolution picture of energy distribution.

3. **Reporting.** Results are printed to terminal (function summary, hotspot
   table, instruction breakdown), written to a JSON file for programmatic
   consumption, and rendered into a self-contained HTML report with a source
   code heatmap by a separate Python script.

### Data Flow

```
   Instruction I
     │  getOpcodeName()
     ▼
   OpcodeEnergy[opcode] ──→ cost
     │  BFI.getBlockFreq(BB) / BFI.getEntryFreq()
     ▼
   NormalizedFreq
     │  DebugLoc.getLine()
     ▼
   LineEnergy[line]
     │
     ▼
   ┌─────────────────────────────────┐
   │ BlockReport (per basic block)   │
   │ FuncReport (per function)       │
   │ AllReports (per module)         │
   └─────────────────────────────────┘
            │              │            │
            ▼              ▼            ▼
       Terminal        JSON file    HTML report
       (stdout)        (via opt)    (via visualize.py)
```

## Design Decisions

### Static analysis over dynamic measurement
No runtime needed. Same input always produces the same numbers, which is
important for reproducible CI checks. The trade-off is that BFI frequencies
are heuristic and energy is relative.

### Legacy pass manager
Simpler to set up for a single-pass tool. LLVM 14 supports both legacy and
new PM. The new PM would require more boilerplate (pass registration,
analysis manager wiring) without adding capability that this tool needs.

### JSON energy model
Adding opcodes or swapping architectures does not require recompiling the
pass. Different architectures can use separate JSON files (e.g.,
`x86_energy.json`, `arm_energy.json`). LLVM has built-in JSON support via
`llvm/Support/JSON.h`.

### Block frequency weighting
A loop body with 5 instructions running 1000 iterations matters more than
20 instructions in a prologue block. BFI integrates with `LoopInfo` and
`BranchProbabilityInfo` to estimate trip counts, which is the key mechanism
for producing meaningful relative energy numbers.

### Relative energy (unitless)
Absolute energy depends on CPU, voltage, temperature, and process node.
Relative costs transfer across microarchitectures much better than absolute
numbers would. The tool reports unitless weighted energy, and the
documentation is explicit that this is *not* joules.

### DebugLoc for source mapping
The debug info already maps back to source lines. No extra setup is needed
beyond compiling with `-g`. The pass extracts the line number from each
instruction's `DebugLoc` and aggregates by line.

### Three-level accumulation
Block, opcode, and source-line granularity covers most developer questions:

- "Which **function** is hot?" → per-function totals
- "Which **block** is hot?" → top-3 hotspot table
- "Which **line** is hot?" → HTML heatmap
- "What **kind of work** is expensive?" → opcode category breakdown

### Rule-based advisor (not ML)
The advisor uses fixed thresholds on opcode mix percentages. This is
predictable, easy to debug, and gives the same advice for the same input.
An ML-based advisor would be harder to explain and require training data.

### Separate Python visualization step
The HTML report and heatmap are produced by a Python script reading the
JSON output. This keeps the LLVM pass focused on analysis (C++ + LLVM
toolchain) and the visualization focused on presentation (Python + browser
HTML). Either side can be improved independently.

## Alternative Approaches

### LLVM MachineInstr pass (rejected)
Would give actual target instructions, but requires a specific backend and
runs late in the pipeline. Not portable across architectures, and the IR-level
view is sufficient for a relative profiler. The IR pass works pre-codegen and
on any target that LLVM supports.

### Python-based IR parser (rejected)
Could parse LLVM IR text directly, but that is fragile across LLVM versions
and duplicates the BFI logic that is already available in the C++ API. A
Python pass also cannot hook into LLVM's analysis manager cleanly.

### Runtime instrumentation — perf / RAPL (rejected)
Accurate hardware-level measurement, but requires running the program,
specific hardware support (RAPL is Intel-only, perf is Linux-only), and is
not portable across platforms. The whole point of this tool is to avoid the
runtime requirement.

### Hardcoded cost table in C++ (rejected)
No external file needed, but every change to the model requires
recompilation, the table would be buried in C++ source, and swapping
architectures would mean rebuilding. The JSON model file is the better
boundary.

### New pass manager (rejected)
More modern API, but more boilerplate and dependency requirements for a
simple analysis pass. The legacy PM works fine for a single-function visitor
that needs BFI as a required analysis.

### Per-instruction cost only, no BFI (rejected)
Would dramatically underweight loop bodies and would not produce a useful
ordering across the five benchmarks. BFI is the key to producing numbers
that span orders of magnitude.

### Call-graph-aware modeling (considered, deferred)
Could weight calls by the callee's own cost (e.g., a call to `memcpy` is
more expensive than a call to `noop`). The current pass accounts for the
call instruction itself but not the called function's cost. This is left as
future work because it requires walking the call graph and resolving
callees, which is non-trivial when the callee is in another translation
unit.
