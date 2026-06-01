#include <stdio.h>

volatile int sink = 0;

int compute(int n) {
    int sum = 0;
    for (int i = 0; i < n; i++) {
        sum = sum + i * 2;
        sink = sum;
    }
    return sum;
}

int main() {
    int result = compute(1000);
    printf("Result: %d\n", result);
    return 0;
}
