// benchmark: loop.c
// Compute-bound: arithmetic in a tight loop.
// Expected: high add/mul count, few load/store.

volatile int sink = 0;

int loop_sum(int n) {
    int sum = 0;
    for (int i = 0; i < n; i++) {
        sum = sum + i * 2;
        sink = sum;
    }
    return sum;
}

int main() {
    return loop_sum(1000);
}
