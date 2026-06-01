// benchmark: memory.c
// Memory-intensive: linked-list traversal.
// Expected: high load/store count, few arithmetic ops.

struct Node {
    int data;
    struct Node *next;
};

volatile int sink = 0;

#define POOL_SIZE 1000

static struct Node pool[POOL_SIZE];

void init_list(void) {
    for (int i = 0; i < POOL_SIZE - 1; i++) {
        pool[i].data = i;
        pool[i].next = &pool[i + 1];
    }
    pool[POOL_SIZE - 1].data = POOL_SIZE - 1;
    pool[POOL_SIZE - 1].next = 0;
}

int traverse(void) {
    int sum = 0;
    struct Node *cur = &pool[0];
    while (cur) {
        sum += cur->data;
        cur = cur->next;
    }
    return sum;
}

int main() {
    init_list();
    int result = traverse();
    sink = result;
    return 0;
}
