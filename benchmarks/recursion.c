// benchmark: recursion.c
// Compute-bound: recursive function calls.
// Expected: high call/ret count, some arithmetic.

volatile int sink = 0;

int factorial(int n) {
    if (n <= 1) {
        sink = 1;
        return 1;
    }
    sink = n;
    return n * factorial(n - 1);
}

int main() {
    return factorial(10);
}