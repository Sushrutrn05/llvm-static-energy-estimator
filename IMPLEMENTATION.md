# Implementation Guide

## LLVM APIs Used

The pass relies on the following LLVM 14 APIs:

| API | Header | Purpose |
|-----|--------|---------|
| `FunctionPass` | `llvm/Pass.h` | Base class for the pass |
| `ModulePass::doInitialization` / `doFinalization` | `llvm/Pass.h` | Load JSON model, write JSON report |
| `BlockFrequencyInfoWrapperPass` | `llvm/Analysis/BlockFrequencyInfo.h` | Block execution frequency |
| `BlockFrequencyInfo::getBlockFreq` | `llvm/Analysis/BlockFrequencyInfo.h` | Per-block frequency count |
| `BlockFrequencyInfo::getEntryFreq` | `llvm/Analysis/BlockFrequencyInfo.h` | Entry-block reference frequency |
| `OptimizationRemarkEmitterWrapperPass` | `llvm/Transforms/Utils.h` | Emit LLVM optimization remarks |
| `OptimizationRemarkAnalysis` | `llvm/Transforms/Utils.h` | Construct analysis remarks |
| `json::parse` | `llvm/Support/JSON.h` | Parse the cost model JSON file |
| `MemoryBuffer::getFile` | `llvm/Support/MemoryBuffer.h` | Read JSON model from disk |
| `raw_fd_ostream` | `llvm/Support/FileOutput.h` | Write JSON report to disk |
| `Instruction::getOpcodeName` | `llvm/IR/Instruction.h` | Get opcode string for cost lookup |
| `DebugLoc` | `llvm/IR/DebugLoc.h` | Source line mapping for heatmap |
| `DIScope` / `dyn_cast<DIScope>` | `llvm/IR/DebugInfoMetadata.h` | Recover source filename |
| `cl::opt` | `llvm/Support/CommandLine.h` | Command-line options |
| `errs()` / `outs()` | `llvm/Support/raw_ostream.h` | Terminal output |

The pass declares its analysis dependencies in `getAnalysisUsage`:

```cpp
void getAnalysisUsage(AnalysisUsage &AU) const override {
    AU.addRequired<BlockFrequencyInfoWrapperPass>();
    AU.addRequired<OptimizationRemarkEmitterWrapperPass>();
    AU.setPreservesAll();
}
```

`setPreservesAll()` is correct because the pass only reads IR.

## Pass Lifecycle

```
doInitialization(Module&)
  └── Load energy model JSON
       └── llvm::json::parse() → std::unordered_map<string, double>

runOnFunction(Function&)          ← once per function
  ├── Get BFI, ORE analysis passes
  ├── For each basic block:
  │    ├── Get normalized frequency from BFI
  │    ├── For each instruction:
  │    │    ├── Lookup cost in OpcodeEnergy (default 1.0 if missing)
  │    │    ├── Accumulate block energy: cost × frequency
  │    │    ├── Count opcode types for breakdown
  │    │    └── Accumulate source-line energy via DebugLoc
  │    ├── Store BlockReport
  │    └── Emit per-block optimization remark
  ├── Compute hotspots (top 3 blocks by energy)
  ├── Generate optimization advisories (rule-based opcode thresholds)
  ├── Print instruction breakdown table
  └── Return false (pass is read-only)

doFinalization(Module&)
  └── Serialize AllReports to JSON via raw_fd_ostream
```

## Build and Execution Workflow

The build and run process is:

1. **Compile source to LLVM IR with debug info:**
   ```
   clang-14 -S -emit-llvm -g -O0 test.c -o test.ll
   ```

2. **Run the energy estimation pass:**
   ```
   opt-14 -load ./EnergyPass.so -energy \
       -energy-model models/x86_energy.json \
       -energy-report reports/energy_report.json \
       -disable-output test.ll
   ```

3. **Generate HTML visualization (optional):**
   ```
   python3 scripts/visualize.py
   ```

The `scripts/build.sh` script handles compilation of `EnergyPass.cpp` with the
correct LLVM include and library flags obtained from `llvm-config-14`.

Command-line options exposed by the pass:

| Option | Default | Description |
|--------|---------|-------------|
| `-energy-model <path>` | `models/x86_energy.json` | JSON file with opcode→cost map |
| `-energy-report <path>` | `reports/energy_report.json` | Output JSON report path |
| `-pass-remarks-analysis=energy` | off | Enable per-block / per-function remarks |

## Data Structures

```cpp
struct BlockReport {
    std::string Name;       // BB_0, BB_1, ... or named label
    double Frequency;       // Normalized block execution frequency
    double Energy;          // cost × frequency, summed for block
};

struct FuncReport {
    std::string Name;
    double TotalEnergy;
    std::vector<BlockReport> Blocks;
    std::vector<HotspotReport> Hotspots;     // top 3
    std::vector<AdvisoryReport> Advisories;  // rule-based
    std::string SourceFile;                  // from DebugLoc scope
    std::vector<SourceLineEnergy> SourceLines;
};
```

`AllReports` is a `std::vector<FuncReport>` populated by `runOnFunction` and
serialized in `doFinalization`.

## Block Frequency Analysis (BFI) Integration

Block frequency analysis is the core mechanism for weighting instruction
costs. LLVM's BFI pass provides estimated execution counts for each basic
block based on branch probabilities and loop trip counts.

```cpp
BlockFrequencyInfo &BFI =
    getAnalysis<BlockFrequencyInfoWrapperPass>().getBFI();

uint64_t Freq = BFI.getBlockFreq(&BB).getFrequency();
uint64_t EntryFreq = BFI.getEntryFreq();
double NormalizedFreq = (double)Freq / EntryFreq;
```

`Energy = cost × NormalizedFreq` for each instruction. BFI integrates with
`LoopInfo` and `BranchProbabilityInfo` to estimate trip counts. The pass
declares BFI as a required analysis pass so LLVM automatically computes it
before the energy pass runs.

The normalized frequency represents how many times a block is expected to
execute relative to the function entry. A block with `NormalizedFreq = 1000`
(inside a loop that runs 1000 times) contributes 1000× the per-instruction
cost to the total energy. A block with `NormalizedFreq = 1.0` (executed once
per call) contributes 1× the per-instruction cost.

### Per-block retrieval

```cpp
for (auto &BB : F) {
    double NormalizedFreq = (double)BFI.getBlockFreq(&BB).getFrequency()
                          / (double)BFI.getEntryFreq();
    // ... walk instructions, accumulate energy using NormalizedFreq
}
```

### BFI edge cases

- **Functions with infinite loops** — BFI will produce extreme frequency
  values. The pass does not clamp them; users should interpret results
  carefully for such inputs.
- **Functions with no loops** — every block's `NormalizedFreq` is 1.0, so
  the pass degenerates to per-instruction cost. The hotspots table still
  works but is less informative.
- **Recursive functions** — BFI estimates recursion depth using a fixed-point
  computation. The frequency of the recursive block reflects the depth
  estimate, which is usually conservative.

## Energy Model Implementation

The energy model is a JSON file mapping LLVM opcode names to relative cost
values. The model is loaded once in `doInitialization()`:

```cpp
// In doInitialization
auto Buffer = MemoryBuffer::getFile(ModelPath);
auto Json = json::parse(Buffer->get()->getMemBufferRef());
// Walk JSON object, populate std::unordered_map<std::string, double>
```

A small example model:

```json
{
    "add": 1.0,
    "mul": 3.0,
    "load": 3.0,
    "store": 3.0,
    "call": 3.0,
    "phi": 0.5
}
```

The full model in `models/x86_energy.json` covers 41 opcodes with values
calibrated to give memory and multiplication operations higher cost than
simple integer adds and phi nodes.

For each instruction, the cost is looked up by `Inst.getOpcodeName()`:

```cpp
double cost = 1.0;  // safe default
auto it = OpcodeEnergy.find(I.getOpcodeName());
if (it != OpcodeEnergy.end())
    cost = it->second;
```

Missing opcodes default to a cost of 1.0, which prevents crashes on
unexpected instructions but means the model's accuracy depends on opcode
coverage. The default is documented and a warning can be added for unknown
opcodes in a future revision.

### Loading with `MemoryBuffer`

`MemoryBuffer::getFile` is used (rather than `std::ifstream`) so the pass
inherits LLVM's error-handling conventions and works on platforms where the
LLVM file API is more reliable than the C++ standard library.

## JSON Report Generation

After processing all functions, `doFinalization()` serializes the
accumulated reports to a JSON file. The report structure is:

```json
{
  "functions": [
    {
      "name": "compute",
      "total_energy": 1150.0,
      "blocks": [
        { "name": "entry", "frequency": 1.0, "energy": 50.0 },
        { "name": "BB_1", "frequency": 1000.0, "energy": 1100.0 }
      ],
      "hotspots": [
        { "name": "BB_1", "energy": 1100.0, "percent": 95.6 }
      ],
      "advisories": [],
      "source_lines": [
        { "line": 7, "energy": 500.0 },
        { "line": 8, "energy": 600.0 }
      ]
    }
  ]
}
```

The JSON output is written using `raw_fd_ostream`:

```cpp
std::error_code EC;
raw_fd_ostream Out(ReportPath, EC);
if (EC) { /* log and skip */ return; }
// serialize each FuncReport as a JSON object
// write to Out
```

`raw_fd_ostream` is preferred over `std::ofstream` because it integrates with
LLVM's error reporting and avoids mixing C++ stream and C FILE* I/O on
Windows.

The JSON is suitable for:

- Programmatic consumption (CI, dashboards, custom scripts)
- Feeding into the HTML visualization step
- Diffing across commits to spot regressions in the energy profile

## HTML Visualization Generation

The HTML report is generated by a separate Python script
(`scripts/visualize.py`) that reads the JSON report and produces a
self-contained HTML file. The report includes:

- **Function summary table** — total energy, instruction count, hotspot
  percentage for each function
- **Block-level detail** — energy and frequency for every basic block
- **Hotspot ranking** — top 3 blocks with their contribution percentage
- **Optimization advisories** — rule-based suggestions (see below)
- **Source code heatmap** — lines colored from green (low) to red (high)
  energy, with tooltips showing exact values

The heatmap uses `DebugLoc` line numbers to map energy back to source lines.
In the C++ pass:

```cpp
if (DebugLoc DL = Inst.getDebugLoc()) {
    unsigned Line = DL.getLine();
    if (FR.SourceFile.empty())
        if (DIScope *Scope = dyn_cast<DIScope>(DL.getScope()))
            FR.SourceFile = Scope->getFilename().str();
    LineEnergy[Line] += Cost * NormalizedFreq;
}
```

The Python script:

1. Reads the JSON report from `reports/energy_report.json`.
2. For each function, reads the corresponding `SourceFile` if available.
3. Computes a per-line energy value (the max across all functions that
   contribute to that line, or the sum — implementation detail).
4. Picks a color from a green→yellow→red scale based on each line's
   normalized energy.
5. Embeds the source code, the per-line colors, and the summary tables into
   a single self-contained HTML file with no external dependencies.

The output HTML has no external CSS or JS — it works offline and is safe to
share as a build artifact.

## OptimizationRemarkEmitter

```cpp
OptimizationRemarkEmitter &ORE =
    getAnalysis<OptimizationRemarkEmitterWrapperPass>().getORE();

// Per block
ORE.emit(OptimizationRemarkAnalysis("energy", "BlockEnergy", &*BB.begin())
    << "block energy: " << fmtDouble(BlockEnergy)
    << " (frequency: " << fmtDouble(NormalizedFreq) << ")");

// Per function
ORE.emit(OptimizationRemarkAnalysis("energy", "EstimatedEnergy", &F)
    << "estimated energy: " << fmtDouble(TotalEnergy));
```

Enabled with `-pass-remarks-analysis=energy`. Useful for integrating with
LLVM's standard remark-based tooling (`-fsave-optimization-record`).

## Hotspot Detection

Sort blocks by energy descending, take top 3, compute percentage of function
total:

```cpp
std::sort(Blocks.begin(), Blocks.end(),
          [](const BlockReport &a, const BlockReport &b) {
              return a.Energy > b.Energy;
          });
Hotspots.assign(Blocks.begin(),
                Blocks.begin() + std::min<size_t>(3, Blocks.size()));
for (auto &H : Hotspots) {
    H.Percent = (TotalEnergy > 0.0) ? 100.0 * H.Energy / TotalEnergy : 0.0;
}
```

## Optimization Advisor

Rule-based, fixed thresholds on instruction mix percentages:

| Pattern | Threshold | Suggestion |
|---------|-----------|------------|
| `mul`/`fmul` | ≥8% | Vectorization or strength reduction |
| `sdiv`/`udiv`/`fdiv` | ≥5% | Multiply-by-inverse |
| `load` | ≥30% | Improve cache locality |
| `store` | ≥20% | Reduce memory writes |
| `load` + `store` | ≥40% | Tiling / data reuse |
| `call` | ≥20% | Consider inlining |

Each advisory has three fields: observation (percentage + raw cost),
recommendation, potential benefit.

The thresholds are intentionally conservative so the advisor fires only on
workloads where the pattern is genuinely dominant, not on incidental
occurrences.
