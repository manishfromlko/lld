# 09 — Splitwise Expense Splitter (Python Implementation)

**File:** `splitwise.py`  
**Tier:** 3

---

## Problem Statement

Design a group expense splitter that supports equal, exact, and percentage splits. After recording all expenses, compute the minimum number of transactions needed to fully settle all debts.

---

## Design Patterns Used

| Pattern | Where | Why |
|---|---|---|
| **Strategy** | `SplitStrategy` ABC → `EqualSplitStrategy`, `ExactSplitStrategy`, `PercentageSplitStrategy` | Add new split types (Shares-based) without changing `ExpenseService` |
| **Observer** | `ExpenseObserver` → `EmailNotifier` | Decouple expense recording from notification side-effects |
| **Registry** | `_STRATEGIES: dict[SplitType, SplitStrategy]` | Factory lookup without if-else chains |

---

## Class Structure

```
SplitType (Enum): EQUAL, EXACT, PERCENTAGE
User(user_id, name, email)
Split(user, amount)
Expense(expense_id, paid_by, amount, split_type, splits, description)
Group(group_id, name, members, expenses)
Transaction(from_user, to_user, amount)

SplitStrategy (ABC)
├── EqualSplitStrategy      — amount / len(users) each
├── ExactSplitStrategy      — validate sum == amount
└── PercentageSplitStrategy — validate sum == 100%

_STRATEGIES dict[SplitType → SplitStrategy]   — registry / factory

GroupService                — create_group / get_group
ExpenseService              — add_expense + observer notification + balance calc
SettlementService           — minimize_transactions (greedy two-heap algorithm)
```

---

## Balance Calculation

After all expenses, compute each user's net balance:

```python
def calculate_balances(self, group: Group) -> dict[User, float]:
    balances = {m: 0.0 for m in group.members}
    for expense in group.expenses:
        balances[expense.paid_by] += expense.amount      # payer is owed money
        for split in expense.splits:
            balances[split.user] -= split.amount          # participant owes money
    return balances
```

- **Positive balance** → user is owed money (creditor).
- **Negative balance** → user owes money (debtor).

---

## Minimum Transactions Algorithm — Greedy Two-Heap

The key insight: to settle N people optimally, always pair the **largest creditor** with the **largest debtor**.

```
max-heap of creditors (negate for Python's min-heap)
min-heap of debtors  (already negative balances)

while both heaps non-empty:
    credit_neg, creditor = pop creditors   # largest credit
    debt, debtor         = pop debtors    # largest debt

    credit      = -credit_neg
    debt_amount = -debt
    settled     = min(credit, debt_amount)

    emit Transaction(debtor → creditor, settled)

    if remaining credit > 0:  push back to creditors
    if remaining debt > 0:    push back to debtors
```

**Complexity:** O(N log N) — each person is pushed/popped at most twice.  
**Transaction count:** At most N-1 transactions for N people (optimal for the greedy case).

---

## Python Heap Trick for Max-Heap

Python's `heapq` is a **min-heap only**. To simulate a max-heap for creditors, negate the balance:

```python
# Creditors: store negative balance so largest credit comes out first
heapq.heappush(creditors, (-balance, user))   # e.g., balance=300 → push -300
credit_neg, creditor = heapq.heappop(creditors)
credit = -credit_neg   # restore positive value
```

---

## Split Strategy Validation

```python
class ExactSplitStrategy(SplitStrategy):
    def split(self, amount, users, params):
        if len(users) != len(params):
            raise ValueError("Each user must have an exact amount")
        if abs(sum(params) - amount) > 0.01:
            raise ValueError(f"Exact amounts don't sum to {amount}")
        return [Split(u, p) for u, p in zip(users, params)]

class PercentageSplitStrategy(SplitStrategy):
    def split(self, amount, users, params):
        if abs(sum(params) - 100) > 0.01:
            raise ValueError("Percentages must sum to 100")
        return [Split(u, amount * p / 100) for u, p in zip(users, params)]
```

Use `0.01` tolerance instead of `== 0` to handle floating-point rounding.

---

## Python vs Java Key Differences

| Concern | Java | Python |
|---|---|---|
| Priority queue | `PriorityQueue` (min-heap) | `heapq` + negate for max-heap |
| `Comparable` | `implements Comparable<User>` | `@dataclass(eq=True)` + `__hash__` |
| Strategy registry | `Map<SplitType, SplitStrategy>` | `dict[SplitType, SplitStrategy]` |
| `BigDecimal` for money | Avoids float precision issues | Use `round(..., 2)` or `decimal.Decimal` in production |

---

## Worked Example

```
Alice pays ₹1200 hotel (equal 4-way): each owes ₹300
Bob pays ₹800 dinner (exact: Alice 200, Bob 200, Charlie 150, Diana 250)
Charlie pays ₹500 fuel (30/30/20/20%)

Net balances:
  Alice:   +1200 - 300 - 200 - 150 = +550  (creditor)
  Bob:     + 800 - 300 - 200 - 150 = +150  (creditor)
  Charlie: + 500 - 300 - 150 - 100 = -50   (debtor)
  Diana:       0 - 300 - 250 - 100 = -650  (debtor)

Greedy settlement:
  Diana → Alice ₹550   (largest debtor pays largest creditor)
  Diana → Bob ₹100     (Diana still owes 100 after paying Alice)
  Charlie → Bob ₹50    (Charlie pays remaining Bob balance)
  Total: 3 transactions
```

---

## Interview Talking Points

1. **Why greedy two-heap and not DP?** — The DP approach (find minimum transactions as a set-cover problem) is NP-hard. The greedy heap approach is O(N log N), produces at most N-1 transactions, and is optimal for most practical inputs.
2. **Is the greedy approach always optimal?** — It minimises the number of transactions but may not minimise total money moved. For interview purposes, greedy is the expected answer.
3. **Float precision for money** — In production, use `decimal.Decimal` with rounding modes. In an interview, acknowledge the issue and note that `abs(diff) < 0.01` is the practical guard.
4. **Adding a new split type** — Implement `SplitStrategy.split()`, add an entry to `_STRATEGIES`, and add the enum value. Zero changes to `ExpenseService` or `SettlementService`.
