#include "llvm/Pass.h"
#include "llvm/IR/Function.h"
#include "llvm/IR/Instructions.h"
#include "llvm/IR/InstIterator.h"
#include "llvm/IR/LLVMContext.h"
#include "llvm/Support/raw_ostream.h"
#include "llvm/Support/Format.h"
#include "llvm/Support/CommandLine.h"
#include "llvm/Support/JSON.h"
#include "llvm/Support/MemoryBuffer.h"
#include "llvm/Support/FileSystem.h"
#include "llvm/Support/Path.h"
#include "llvm/Analysis/BlockFrequencyInfo.h"
#include "llvm/Analysis/BranchProbabilityInfo.h"
#include "llvm/Analysis/LoopInfo.h"
#include "llvm/Analysis/OptimizationRemarkEmitter.h"
#include "llvm/IR/DebugInfoMetadata.h"
#include <unordered_map>
#include <map>
#include <vector>
#include <algorithm>
#include <cstdio>

using namespace llvm;

namespace {

// Helper: right-aligns text within a fixed width by prepending spaces.
static std::string rightAlign(const std::string &S, unsigned Width) {
  if (S.size() >= Width) return S;
  return std::string(Width - S.size(), ' ') + S;
}

// Helper: left-aligns text within a fixed width by appending spaces.
static std::string leftAlign(const std::string &S, unsigned Width) {
  if (S.size() >= Width) return S;
  return S + std::string(Width - S.size(), ' ');
}

// Helper: format a double through llvm::format and return as std::string.
static std::string fmtDouble(double Val, const char *Fmt = "%.2f") {
  std::string Buf;
  llvm::raw_string_ostream(Buf) << llvm::format(Fmt, Val);
  return Buf;
}

// Command-line option for the energy model JSON path.
// Default: looks for models/x86_energy.json relative to CWD.
static cl::opt<std::string> EnergyModelPath(
    "energy-model",
    cl::desc("Path to JSON energy model file"),
    cl::value_desc("filename"),
    cl::init("models/x86_energy.json"));

// Command-line option for the JSON report output path.
static cl::opt<std::string> ReportPath(
    "energy-report",
    cl::desc("Path for JSON energy report file"),
    cl::value_desc("filename"),
    cl::init("reports/energy_report.json"));

class EnergyPass : public FunctionPass {
private:
  // Dynamic energy model loaded from JSON: maps opcode name -> cost.
  std::unordered_map<std::string, double> OpcodeEnergy;

  // Flag to load the model exactly once across all functions.
  bool ModelLoaded = false;

  // Per-function report data for JSON output.
  struct BlockReport {
    std::string Name;
    double Frequency;
    double Energy;
  };
  struct FuncReport {
    std::string Name;
    double TotalEnergy;
    std::vector<BlockReport> Blocks;

    struct HotspotReport {
      std::string Name;
      double Energy;
      double Percent;
    };
    std::vector<HotspotReport> Hotspots;

    struct AdvisoryReport {
      std::string Observation;
      std::string Recommendation;
      std::string Benefit;
    };
    std::vector<AdvisoryReport> Advisories;

    struct SourceLineEnergy {
      unsigned Line;
      double Energy;
    };
    std::string SourceFile;
    std::vector<SourceLineEnergy> SourceLines;
  };
  std::vector<FuncReport> AllReports;

  /// Load the energy model from a JSON file at \p Path.
  ///
  /// Expected JSON format:
  ///   { "add": 1.0, "mul": 2.5, "load": 3.0, "store": 3.0 }
  ///
  /// LLVM APIs used:
  ///   - MemoryBuffer::getFile()   -- reads a file into an owned buffer
  ///   - json::parse()             -- parses a JSON string into a json::Value tree
  ///   - json::Value::getAsObject()-- casts the root to a JSON object
  ///   - json::Object iteration    -- iterates key-value pairs
  ///   - json::Value::getAsDouble()- extracts a double from a JSON value
  Error loadEnergyModel(StringRef Path) {
    // --- File I/O ---
    // MemoryBuffer::getFile maps or reads the entire file into memory.
    // Returns an ErrorOr<std::unique_ptr<MemoryBuffer>>.
    auto BufOrErr = MemoryBuffer::getFile(Path);
    if (!BufOrErr)
      return createStringError(inconvertibleErrorCode(),
                               "Cannot open energy model: " + Path);

    StringRef Content = BufOrErr.get()->getBuffer();

    // --- JSON parsing ---
    // json::parse() returns Expected<json::Value>.
    // If the input is malformed, it returns a parse error.
    auto ValOrErr = json::parse(Content);
    if (!ValOrErr)
      return ValOrErr.takeError();

    json::Value &Root = *ValOrErr;

    // --- Extract top-level object ---
    // getAsObject() returns nullptr if the root is not a JSON object.
    json::Object *Obj = Root.getAsObject();
    if (!Obj)
      return createStringError(inconvertibleErrorCode(),
                               "JSON root is not an object");

    // --- Iterate key-value pairs ---
    // Each key is an opcode name (e.g. "add"),
    // each value must be a number (the energy cost).
    for (const auto &[Key, Val] : *Obj) {
      if (auto Cost = Val.getAsNumber())
        OpcodeEnergy[Key.str()] = *Cost;
      // Non-numeric values are silently skipped.
    }

    return Error::success();
  }

public:
  static char ID;
  EnergyPass() : FunctionPass(ID) {}

  void getAnalysisUsage(AnalysisUsage &AU) const override {
    AU.addRequired<BlockFrequencyInfoWrapperPass>();
    AU.addRequired<BranchProbabilityInfoWrapperPass>();
    AU.addRequired<LoopInfoWrapperPass>();
    AU.addRequired<OptimizationRemarkEmitterWrapperPass>();
    AU.setPreservesAll();
  }

  bool doInitialization(Module &M) override {
    // Load the energy model once before processing any function.
    // This runs before the first call to runOnFunction().
    if (!ModelLoaded) {
      Error Err = loadEnergyModel(EnergyModelPath);
      if (Err) {
        // On failure, log a diagnostic and fall back to an empty map
        // so that all opcodes get the default cost of 1.0.
        logAllUnhandledErrors(std::move(Err), errs(),
                              "[EnergyPass] Warning: ");
        errs() << "[EnergyPass] Using default cost (1.0) for all opcodes.\n";
      }
      ModelLoaded = true;
    }
    return false;
  }

  bool doFinalization(Module &M) override {
    // --- Build JSON report ---
    // Construct a json::Array of all functions processed.
    json::Array FuncArray;
    for (const auto &FR : AllReports) {
      json::Array BlockArray;
      for (const auto &BR : FR.Blocks) {
        BlockArray.push_back(json::Object({
            {"name", BR.Name},
            {"frequency", BR.Frequency},
            {"energy", BR.Energy},
        }));
      }
      json::Array HotspotArray;
      for (const auto &HR : FR.Hotspots) {
        HotspotArray.push_back(json::Object({
            {"name", HR.Name},
            {"energy", HR.Energy},
            {"percent", HR.Percent},
        }));
      }
      json::Array AdvisoryArray;
      for (const auto &AR : FR.Advisories) {
        AdvisoryArray.push_back(json::Object({
            {"observation", AR.Observation},
            {"recommendation", AR.Recommendation},
            {"benefit", AR.Benefit},
        }));
      }
      json::Array SourceLineArray;
      for (const auto &SL : FR.SourceLines) {
        SourceLineArray.push_back(json::Object({
            {"line", SL.Line},
            {"energy", SL.Energy},
        }));
      }
      FuncArray.push_back(json::Object({
          {"name", FR.Name},
          {"total_energy", FR.TotalEnergy},
          {"source_file", FR.SourceFile},
          {"blocks", std::move(BlockArray)},
          {"hotspots", std::move(HotspotArray)},
          {"advisories", std::move(AdvisoryArray)},
          {"source_lines", std::move(SourceLineArray)},
      }));
    }

    json::Object Root({{"report",
                        json::Object({{"functions", std::move(FuncArray)}})}});

    // --- File writing with raw_fd_ostream ---
    // Create the output directory (e.g. reports/) if it does not exist.
    StringRef ParentDir = sys::path::parent_path(ReportPath);
    if (!ParentDir.empty())
      sys::fs::create_directories(ParentDir);

    // raw_fd_ostream wraps a file descriptor; it takes a path and an
    // std::error_code output parameter. On failure the error_code is set.
    std::error_code EC;
    raw_fd_ostream OS(ReportPath, EC);
    if (EC) {
      errs() << "[EnergyPass] Failed to write report: " << EC.message()
             << "\n";
      return false;
    }

    // json::Value overloads operator<< for raw_ostream, producing
    // compact single-line JSON output.
    OS << json::Value(std::move(Root)) << "\n";
    OS.close();

    outs() << "[EnergyPass] Report written to " << ReportPath << "\n";
    return false;
  }

  bool runOnFunction(Function &F) override {
    BlockFrequencyInfo &BFI =
        getAnalysis<BlockFrequencyInfoWrapperPass>().getBFI();

    // --- Per-function accumulators ---
    struct OpcodeStat {
      unsigned Count = 0;
      double TotalCost = 0.0;
    };
    std::unordered_map<std::string, OpcodeStat> OpcodeStats;
    std::map<unsigned, double> LineEnergy;
    double TotalEnergy = 0.0;
    unsigned TotalInsts = 0;
    unsigned TotalBlocks = 0;
    unsigned BlockIdx = 0;

    FuncReport FR;
    FR.Name = F.getName().str();

    // === Function Header ===
    outs() << "\n";
    outs() << "============================================================\n";
    outs() << "  Function:  " << F.getName() << "\n";
    outs() << "  Args:      " << F.arg_size() << "\n";
    outs() << "============================================================\n\n";

    // === Per-Block Table ===
    outs() << "  Block                       Freq    Insts  Block Energy\n";
    outs() << "  -------------------------  ------  -----  ------------\n";

    for (BasicBlock &BB : F) {
      uint64_t Freq = BFI.getBlockFreq(&BB).getFrequency();
      uint64_t EntryFreq = BFI.getEntryFreq();
      double NormalizedFreq = (EntryFreq > 0) ? (double)Freq / EntryFreq : 0.0;

      double BlockEnergy = 0.0;
      unsigned BlockInsts = 0;

      for (Instruction &Inst : BB) {
        StringRef OpName = Inst.getOpcodeName();
        auto It = OpcodeEnergy.find(OpName.str());
        double Cost = (It != OpcodeEnergy.end()) ? It->second : 1.0;

        BlockEnergy += Cost * NormalizedFreq;
        BlockInsts++;

        OpcodeStats[OpName.str()].Count++;
        OpcodeStats[OpName.str()].TotalCost += Cost;

        // --- Accumulate energy per source line ---
        if (DebugLoc DL = Inst.getDebugLoc()) {
          unsigned Line = DL.getLine();
          if (FR.SourceFile.empty())
            if (MDNode *N = DL.getScope())
              if (DIScope *Scope = dyn_cast_or_null<DIScope>(N))
                FR.SourceFile = Scope->getFilename().str();
          LineEnergy[Line] += Cost * NormalizedFreq;
        }
      }

      TotalEnergy += BlockEnergy;
      TotalInsts += BlockInsts;
      TotalBlocks++;

      std::string BBName = BB.hasName() ? BB.getName().str()
                                        : "BB_" + std::to_string(BlockIdx);
      outs() << "  " << leftAlign(BBName, 24)
             << rightAlign(fmtDouble(NormalizedFreq), 7) << "  "
             << rightAlign(std::to_string(BlockInsts), 5) << "  "
             << rightAlign(fmtDouble(BlockEnergy), 10) << "\n";

      FR.Blocks.push_back({BBName, NormalizedFreq, BlockEnergy});
      BlockIdx++;

      // --- Per-block remark with source location ---
      // Finds the first instruction in the block with a valid DebugLoc
      // so the remark carries the correct source file and line.
      {
        OptimizationRemarkEmitter &ORE =
            getAnalysis<OptimizationRemarkEmitterWrapperPass>().getORE();

        const Instruction *FirstDbg = &*BB.begin();
        for (const Instruction &I : BB) {
          if (I.getDebugLoc()) {
            FirstDbg = &I;
            break;
          }
        }
        OptimizationRemarkAnalysis RemB("energy", "BlockEnergy", FirstDbg);
        RemB << "block energy: " << fmtDouble(BlockEnergy)
             << " (frequency: " << fmtDouble(NormalizedFreq) << ")";
        fflush(stdout);
        ORE.emit(RemB);
        fflush(stdout);
      }
    }

    // --- Per-Block Table Footer ---
    outs() << "  -------------------------  ------  -----  ------------\n";
    outs() << "  " << leftAlign("Total", 24)
           << rightAlign("", 7) << "  "
           << rightAlign(std::to_string(TotalInsts), 5) << "  "
            << rightAlign(fmtDouble(TotalEnergy), 10) << "\n\n";

    // === Source Line Heatmap ===
    for (const auto &[Line, En] : LineEnergy) {
      FR.SourceLines.push_back({Line, En});
    }
    if (!FR.SourceFile.empty())
      outs() << "  Source File: " << FR.SourceFile
             << "  (" << FR.SourceLines.size() << " lines)\n\n";

    // === Energy Hotspots ===
    struct Hotspot {
      std::string Name;
      double Energy;
      double Percent;
    };
    std::vector<Hotspot> HotspotList;
    for (const auto &BR : FR.Blocks) {
      double Pct = TotalEnergy > 0 ? (BR.Energy / TotalEnergy) * 100.0 : 0.0;
      HotspotList.push_back({BR.Name, BR.Energy, Pct});
    }
    std::sort(HotspotList.begin(), HotspotList.end(),
              [](const Hotspot &A, const Hotspot &B) {
                return A.Energy > B.Energy;
              });

    outs() << "  ===== ENERGY HOTSPOTS =====\n";
    outs() << "  Rank  Block                        Energy    Percent\n";
    outs() << "  ----  -------------------------  --------  --------\n";
    unsigned Rank = 1;
    for (const auto &H : HotspotList) {
      outs() << "  " << rightAlign(std::to_string(Rank), 4) << "  "
             << leftAlign(H.Name, 25)
             << rightAlign(fmtDouble(H.Energy), 8) << "  "
             << rightAlign(fmtDouble(H.Percent), 7) << "%\n";
      if (++Rank > 3) {
        if (HotspotList.size() > 3)
          outs() << "  ....  ...\n";
        break;
      }
    }
    outs() << "\n";

    // Store top 3 hotspots in FuncReport for JSON/HTML output
    for (size_t i = 0; i < std::min(size_t(3), HotspotList.size()); ++i) {
      FR.Hotspots.push_back(
          {HotspotList[i].Name, HotspotList[i].Energy, HotspotList[i].Percent});
    }

    // === Optimization Advisory ===
    // Rule-based analysis of instruction mix for optimization opportunities.
    std::vector<FuncReport::AdvisoryReport> Advisor;

    auto getCnt = [&](const std::string &N) -> unsigned {
      auto It = OpcodeStats.find(N);
      return It != OpcodeStats.end() ? It->second.Count : 0;
    };
    auto getCst = [&](const std::string &N) -> double {
      auto It = OpcodeStats.find(N);
      return It != OpcodeStats.end() ? It->second.TotalCost : 0.0;
    };
    auto pctOf = [&](unsigned C) -> double {
      return TotalInsts > 0 ? (double)C / TotalInsts * 100.0 : 0.0;
    };

    unsigned MulCnt  = getCnt("mul") + getCnt("fmul");
    unsigned DivCnt  = getCnt("sdiv") + getCnt("udiv") + getCnt("fdiv");
    unsigned LoadCnt = getCnt("load");
    unsigned StoreCnt = getCnt("store");
    unsigned CallCnt = getCnt("call");

    if (MulCnt > 0 && pctOf(MulCnt) >= 8.0) {
      Advisor.push_back({
          fmtDouble(pctOf(MulCnt)) + "% multiplications (cost: "
              + fmtDouble(getCst("mul") + getCst("fmul")) + ")",
          "Consider vectorization or strength reduction",
          "Lower per-op cost via SIMD or shift-add chains"});
    }
    if (DivCnt > 0 && pctOf(DivCnt) >= 5.0) {
      Advisor.push_back({
          fmtDouble(pctOf(DivCnt)) + "% divisions (cost: "
              + fmtDouble(getCst("sdiv") + getCst("udiv") + getCst("fdiv")) + ")",
          "Replace with cheaper arithmetic (multiply-by-inverse)",
          "Div is 10-40x more expensive than mul on modern CPUs"});
    }
    if (LoadCnt > 0 && pctOf(LoadCnt) >= 30.0) {
      Advisor.push_back({
          fmtDouble(pctOf(LoadCnt)) + "% loads (cost: "
              + fmtDouble(getCst("load")) + ")",
          "Improve cache locality (struct-of-arrays, prefetch)",
          "Cache misses dominate memory access energy"});
    }
    if (StoreCnt > 0 && pctOf(StoreCnt) >= 20.0) {
      Advisor.push_back({
          fmtDouble(pctOf(StoreCnt)) + "% stores (cost: "
              + fmtDouble(getCst("store")) + ")",
          "Reduce memory writes (register allocation, write-combine)",
          "Store energy includes write-back to cache/memory"});
    }
    if ((LoadCnt + StoreCnt) > 0 && pctOf(LoadCnt + StoreCnt) >= 40.0) {
      Advisor.push_back({
          fmtDouble(pctOf(LoadCnt + StoreCnt)) + "% memory ops (cost: "
              + fmtDouble(getCst("load") + getCst("store")) + ")",
          "Improve data reuse via tiling or loop interchange",
          "Fewer cache misses reduces DRAM access energy"});
    }
    if (CallCnt > 0 && pctOf(CallCnt) >= 20.0) {
      Advisor.push_back({
          fmtDouble(pctOf(CallCnt)) + "% calls (cost: "
              + fmtDouble(getCst("call")) + ")",
          "Consider inlining hot call sites",
          "Eliminates call/ret overhead and enables further optimization"});
    }

    // Store advisories in FuncReport for JSON/HTML output.
    for (const auto &A : Advisor) {
      FR.Advisories.push_back(A);
    }

    FR.TotalEnergy = TotalEnergy;
    AllReports.push_back(std::move(FR));

    // === Per-function Optimization Remark ===
    // Finds the first instruction with a valid DebugLoc in the function
    // so the remark carries the correct source file and line.
    {
      OptimizationRemarkEmitter &ORE =
          getAnalysis<OptimizationRemarkEmitterWrapperPass>().getORE();

      const Instruction *FirstDbg = nullptr;
      for (const BasicBlock &BB : F) {
        for (const Instruction &I : BB) {
          if (I.getDebugLoc()) {
            FirstDbg = &I;
            break;
          }
        }
        if (FirstDbg) break;
      }
      const Instruction *Anchor = FirstDbg ? FirstDbg : &*F.begin()->begin();
      OptimizationRemarkAnalysis Rem("energy", "EstimatedEnergy", Anchor);
      Rem << "estimated energy: " << fmtDouble(TotalEnergy)
          << " (" << std::to_string(TotalInsts) << " insts, "
          << std::to_string(TotalBlocks) << " blocks)";
      fflush(stdout);
      ORE.emit(Rem);
      fflush(stdout);
    }

    // === Instruction Breakdown Table ===
    // Sort opcodes alphabetically for deterministic output.
    std::vector<std::pair<std::string, OpcodeStat>> SortedStats(
        OpcodeStats.begin(), OpcodeStats.end());
    std::sort(SortedStats.begin(), SortedStats.end(),
              [](const auto &A, const auto &B) { return A.first < B.first; });

    outs() << "  Instruction Breakdown:\n";
    outs() << "  Opcode                    Count  Total Cost  Avg Cost\n";
    outs() << "  ------                    -----  ----------  --------\n";

    double GrandTotalCost = 0.0;
    unsigned GrandTotalCount = 0;
    for (const auto &[Op, Stat] : SortedStats) {
      double AvgCost = Stat.Count > 0 ? Stat.TotalCost / Stat.Count : 0.0;
      outs() << "  " << leftAlign(Op, 24)
             << rightAlign(std::to_string(Stat.Count), 6) << "  "
             << rightAlign(fmtDouble(Stat.TotalCost), 10) << "  "
             << rightAlign(fmtDouble(AvgCost), 8) << "\n";
      GrandTotalCost += Stat.TotalCost;
      GrandTotalCount += Stat.Count;
    }

    outs() << "  ------                    -----  ----------  --------\n";
    outs() << "  " << leftAlign("Total", 24)
           << rightAlign(std::to_string(GrandTotalCount), 6) << "  "
           << rightAlign(fmtDouble(GrandTotalCost), 10) << "\n";

    // === Optimization Advisory (terminal output) ===
    outs() << "\n  Optimization Advisory:\n";
    outs() << "  ---------------------------------------------------------------------\n";
    if (Advisor.empty()) {
      outs() << "  No significant optimization opportunities detected.\n";
    } else {
      for (const auto &A : Advisor) {
        outs() << "  Observation:   " << A.Observation << "\n";
        outs() << "  Recommendation: " << A.Recommendation << "\n";
        outs() << "  Benefit:       " << A.Benefit << "\n";
        outs() << "  ---------------------------------------------------------------------\n";
      }
    }

    outs() << "============================================================\n";
    fflush(stdout);

    return false;
  }
};

} // anonymous namespace

char EnergyPass::ID = 0;
static RegisterPass<EnergyPass> X("energy",
                                  "LLVM Energy Estimation Pass (JSON + BFI)",
                                  false,
                                  false);
