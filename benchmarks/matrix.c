// benchmark: matrix.c
// Mixed compute + memory: matrix multiplication.
// Expected: balanced add/mul/load/store mix.

#define N 64

volatile int sink = 0;

static int A[N][N], B[N][N], C[N][N];

void matmul(void) {
    for (int i = 0; i < N; i++) {
        for (int j = 0; j < N; j++) {
            int sum = 0;
            for (int k = 0; k < N; k++) {
                sum += A[i][k] * B[k][j];
            }
            C[i][j] = sum;
        }
    }
    sink = C[0][0];
}

int main() {
    matmul();
    return 0;
}
