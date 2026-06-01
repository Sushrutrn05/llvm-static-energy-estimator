# Implementation Guide

## Pass Lifecycle

```
doInitialization(Module&)
  └── Load energy model JSON
       └── llvm::json::parse() → OpcodeEnergy map

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

## BlockFrequencyInfo Usage

```cpp
BlockFrequencyInfo &BFI =
    getAnalysis<BlockFrequencyInfoWrapperPass>().getBFI();

uint64_t Freq = BFI.getBlockFreq(&BB).getFrequency();
uint64_t EntryFreq = BFI.getEntryFreq();
double NormalizedFreq = (double)Freq / EntryFreq;
```

`Energy = cost × NormalizedFreq` for each instruction. BFI integrates with `LoopInfo` and `BranchProbabilityInfo` to estimate trip counts.

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

Enabled with `-pass-remarks-analysis=energy`.

## Energy Model

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

Loaded in `doInitialization()`: `MemoryBuffer::getFile → llvm::json::parse → unordered_map<string, double>`. Missing opcodes default to 1.0.

## Hotspot Detection

Sort blocks by energy descending, take top 3, compute percentage of function total:

```cpp
double Pct = BR.Energy / TotalEnergy * 100.0;
// sort descending, keep top 3
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

Each advisory has three fields: observation (percentage + raw cost), recommendation, potential benefit.

## Source Heatmap

In the pass:

```cpp
if (DebugLoc DL = Inst.getDebugLoc()) {
    unsigned Line = DL.getLine();
    if (FR.SourceFile.empty())
        if (DIScope *Scope = dyn_cast<DIScope>(DL.getScope()))
            FR.SourceFile = Scope->getFilename().str();
    LineEnergy[Line] += Cost * NormalizedFreq;
}
```

In `visualize.py`, the JSON report is matched against the original source file lines. Each line gets a background color from dark green (low energy) to dark red (very high), plus a hover tooltip.
