// benchmark: sorting.c
// Memory-bound: array sorting with nested loops.
// Expected: high load/store count, many comparisons.

volatile int sink = 0;

void bubble_sort(int arr[], int n) {
    for (int i = 0; i < n - 1; i++) {
        for (int j = 0; j < n - i - 1; j++) {
            if (arr[j] > arr[j + 1]) {
                int temp = arr[j];
                arr[j] = arr[j + 1];
                arr[j + 1] = temp;
            }
        }
    }
    sink = arr[0];
}

int main() {
    int arr[50];
    for (int i = 0; i < 50; i++) {
        arr[i] = 50 - i;
    }
    bubble_sort(arr, 50);
    return sink;
}