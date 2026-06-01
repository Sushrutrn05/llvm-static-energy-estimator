# Evaluation Report

## Test Cases

### Test 1: `test.c` — Simple Function with Loop

**Purpose:** Baseline sanity check. Arithmetic loop with volatile sink.

| Metric | Value |
|--------|-------|
| Functions | 2 (`compute`, `main`) |
| Total instructions | 28 + 9 = 37 |
| Weighted energy | 1150.00 + 21.00 = 1171.00 |
| Top hotspot | `BB_2` (53.91% of `compute`) |
| Hotspot lines | 7-9 (loop body) |

**Result:** Loop body lines 7-9 are dark red in heatmap. `compute` accounts for 98.2% of total energy.

---

### Test 2: `loop.c` — Arithmetic-Intensive

**Purpose:** Register-heavy computation with minimal memory access.

| Metric | Value |
|--------|-------|
| Functions | 2 |
| Total instructions | 19 + 9 = 28 |
| Weighted energy | 429.88 + 21.00 = 450.88 |
| Instruction mix | 37% call, 32% control, 26% arithmetic, 5% memory |
| Top advisory | "36.84% calls" |

**Result:** Correctly identifies call-heavy profile. Energy per iteration is low since the inner loop has no memory loads.

---

### Test 3: `matrix.c` — 64×64 Matrix Multiply

**Flags:** `-O0 -g` (required to preserve loop structure)
**Purpose:** Triple-nested loop with high memory op density.

| Metric | Value |
|--------|-------|
| Functions | 2 (`matmul`, `main`) |
| Total instructions | 68 + 4 = 72 |
| Weighted energy | 1,597,050.00 + 8.00 = 1,597,058.00 |
| Instruction mix | 40% memory, 19% control, 18% address, 12% arithmetic |
| Top hotspot | Innermost loop body |

**Result:** Correctly identifies `matmul` as dominant consumer. Weighted energy ~1.6M is ~3,700× loop.c, consistent with O(N³) vs O(N).

---

### Test 4: `memory.c` — Linked-List Traversal

**Purpose:** Pointer chasing. Tests memory-access energy modeling.

| Metric | Value |
|--------|-------|
| Functions | 3 |
| Total instructions | 17 + 27 + 14 = 58 |
| Weighted energy | 804.88 + 267.75 + 24.00 = 1096.63 |
| Instruction mix | 35% load/store, 24% control, 18% call, 12% address |
| Top advisory | "46.43% memory ops" |

**Result:** Memory ops correctly flagged. Weighted energy ~2× loop.c, ~1,500× less than matrix.c — reflects O(N) vs O(N³).

---

### Test 5: Empty Function

**Source:** `void empty() {}`
**Purpose:** Edge case — minimal baseline.

| Metric | Value |
|--------|-------|
| Functions | 1 |
| Total instructions | 1 |
| Weighted energy | 1.0 |
| Top hotspot | Only block at 100% |
| Advisories | None |

**Result:** Produces minimal energy with no advisories triggered.

---

## Cross-Benchmark Comparison

| Benchmark | Complexity | Weighted Energy | vs baseline |
|---|---|---|---|
| `empty()` | O(1) | 1 | 1× |
| `loop.c` | O(N) | 430 | 430× |
| `memory.c` | O(N) | 805 | 805× |
| `matrix.c` | O(N³) | 1,597,050 | 1.6M× |

Relative ordering matches complexity expectations.
