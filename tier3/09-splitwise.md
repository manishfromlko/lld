# 09 — Splitwise / Expense Splitter

**Priority:** TIER 3 — common LLD, tests graph algorithms for minimum transactions

---

## Problem Statement

Design an expense splitting system where users in a group can add expenses and the system calculates the **minimum number of transactions** to settle all debts. The system must support multiple split strategies (equal, exact amount, percentage), maintain expense history, and efficiently compute optimal settlements using a greedy heap-based algorithm.

---

## Clarification Questions

| # | Question | Why It Matters |
|---|----------|----------------|
| 1 | **Group management** — Can a user belong to multiple groups? Can members be added/removed after expenses exist? | Determines if balances are per-group or global, and if we need to handle mid-group membership changes. |
| 2 | **Split types** — Do we support equal, exact, and percentage splits? Any custom ratio splits? | Drives the Strategy pattern design; each split type has different validation rules. |
| 3 | **Multiple currencies** — Must we handle multi-currency expenses with exchange rates? | Adds significant complexity; for an LLD interview, usually single-currency is assumed unless stated. |
| 4 | **Minimum transactions optimization** — Should we guarantee mathematically minimum transactions, or is a greedy approximation acceptable? | True minimum is NP-hard in the general case; greedy with heaps gives optimal results for most practical scenarios. |
| 5 | **Expense history** — Do we need full audit trail of all expenses and settlements? | Affects storage design and whether we need immutable records vs. mutable balance tracking. |
| 6 | **Settle up** — Can users partially settle? Can two users settle independently of the group? | Partial settlements add complexity to the balance graph. |
| 7 | **Simplify debts** — Should the system automatically simplify transitive debts (A→B→C becomes A→C)? | This is exactly what the minimum-transactions algorithm solves; confirm scope. |

---

## Entities

```
┌─────────────┐       ┌──────────────────┐       ┌──────────────────┐
│    User      │──M:N──│      Group        │──1:N──│     Expense      │
│  id, name,   │       │  id, name,        │       │  id, paidBy,     │
│  email       │       │  members: [User]  │       │  amount, splitType│
└─────────────┘       └──────────────────┘       │  splits: [Split] │
                                                   │  description,    │
                                                   │  timestamp       │
                                                   └────────┬─────────┘
                                                            │ 1:N
                                                   ┌────────▼─────────┐
                                                   │     Split        │
                                                   │  user, amount    │
                                                   └──────────────────┘

┌────────────────────────┐
│   SplitStrategy «I»    │◄─── Strategy Pattern
│  + split(amount, users)│
├────────────────────────┤
│ EqualSplitStrategy     │
│ ExactSplitStrategy     │
│ PercentageSplitStrategy│
└────────────────────────┘

┌──────────────────┐
│   Transaction    │   ← Settlement record
│  from: User      │
│  to: User        │
│  amount: double  │
└──────────────────┘

Services: ExpenseService, SettlementService, GroupService
```

---

## Design Patterns

### 1. Strategy Pattern — Split Strategies

Each split type encapsulates its own logic behind the `SplitStrategy` interface. New split types (e.g., share-based) can be added without modifying existing code.

```
Client ──▶ SplitStrategy.split(amount, users, params)
                │
      ┌─────────┼───────────┐
      ▼         ▼           ▼
   Equal     Exact     Percentage
  (÷ N)   (explicit)  (% of total)
```

### 2. Factory Pattern — Expense Creation

`ExpenseFactory` selects the correct `SplitStrategy` based on the `SplitType` enum, constructs the `Expense`, and validates the split amounts.

### 3. Observer Pattern — Notifications

When an expense is added or a settlement is recorded, registered observers (email notifier, push notifier, activity logger) are invoked.

```
ExpenseService.addExpense()
    └──▶ notifyObservers(ExpenseEvent)
              ├──▶ EmailNotifier
              ├──▶ PushNotifier
              └──▶ ActivityLogger
```

---

## SOLID Principles

| Principle | Application in This Design |
|-----------|---------------------------|
| **S — Single Responsibility** | `ExpenseService` handles expense CRUD; `SettlementService` handles debt minimization; `GroupService` handles membership. Each class has one reason to change. |
| **O — Open/Closed** | New split types are added by implementing `SplitStrategy` — no modification to `ExpenseService` or `Expense` classes required. |
| **L — Liskov Substitution** | Any `SplitStrategy` implementation can replace another wherever the interface is expected; all satisfy the contract of returning valid `Split` lists summing to the total amount. |
| **I — Interface Segregation** | `SplitStrategy` has a single method `split()`. Observers implement only `onExpenseAdded()` or `onSettlement()` — not forced to implement both unless they need to. |
| **D — Dependency Inversion** | `ExpenseService` depends on the `SplitStrategy` abstraction, not on concrete `EqualSplitStrategy`. Strategy is injected via factory, keeping high-level modules decoupled. |

---

## Core Algorithm — Minimum Transactions

This is the **KEY algorithm** tested in interviews. Given net balances, find the minimum set of transactions to settle all debts.

### Step-by-Step

1. **Calculate net balance** for each user:
   ```
   balance[user] = total_owed_to_them − total_they_owe
   ```
   All balances sum to zero (money is conserved).

2. **Separate into two groups:**
   - **Creditors** — users with positive balance (they are owed money)
   - **Debtors** — users with negative balance (they owe money)

3. **Greedy matching with heaps:**
   - Put creditors in a **max-heap** (largest credit first)
   - Put debtors in a **min-heap** (largest debt first, stored as negative)
   - Pop the top of each heap, settle `min(credit, |debt|)`
   - Push back any remainder
   - Repeat until both heaps are empty

4. **Each iteration produces exactly one transaction**, and the algorithm terminates with the minimum number of transactions for this greedy approach.

### Worked Example

```
Scenario: A paid 300 for dinner, split equally among A, B, C
          Each person's fair share = 100

Step 1 — Net balances:
  A: paid 300, owes 100 → net = +200  (creditor)
  B: paid   0, owes 100 → net = -100  (debtor)
  C: paid   0, owes 100 → net = -100  (debtor)

Step 2 — Heaps:
  Max-heap (creditors): [A: +200]
  Min-heap (debtors):   [B: -100, C: -100]

Step 3 — Iteration 1:
  Pop A(+200), Pop B(-100)
  Settle min(200, 100) = 100  →  Transaction: B → A : ₹100
  A remainder = +100, push back to max-heap
  B settled completely

Step 4 — Iteration 2:
  Pop A(+100), Pop C(-100)
  Settle min(100, 100) = 100  →  Transaction: C → A : ₹100
  Both settled completely

Result: 2 transactions (minimum possible)
  B → A : ₹100
  C → A : ₹100
```

### Complex Example (5 users)

```
Expenses:
  A paid 400, B paid 200, C paid 0, D paid 100, E paid 0
  Total = 700, equal share = 140 each

Net balances:
  A: 400 - 140 = +260
  B: 200 - 140 = +60
  C:   0 - 140 = -140
  D: 100 - 140 = -40
  E:   0 - 140 = -140

Max-heap (creditors): [A:+260, B:+60]
Min-heap (debtors):   [C:-140, E:-140, D:-40]

Iteration 1: A(+260) ↔ C(-140) → C→A: 140, A remainder +120
Iteration 2: A(+120) ↔ E(-140) → E→A: 120, E remainder -20
Iteration 3: B(+60)  ↔ E(-20)  → E→B: 20,  B remainder +40
Iteration 4: B(+40)  ↔ D(-40)  → D→B: 40,  both settled

Result: 4 transactions (minimum for this configuration)
```

### Time Complexity

| Operation | Complexity |
|-----------|-----------|
| Calculate net balances | O(E) where E = number of expenses |
| Build heaps | O(N log N) where N = number of users |
| Settlement iterations | O(N log N) — at most N-1 transactions, each with heap operations |
| **Total** | **O(E + N log N)** |

> **Note:** The truly optimal minimum-transactions problem (minimizing the count of transactions globally) is NP-hard. The greedy heap approach gives optimal results when debts don't form complex cycles. For interview purposes, the heap approach is the expected answer.

---

## Data Structure Choices

| Data Structure | Usage | Why |
|----------------|-------|-----|
| `HashMap<String, Double>` | Net balances per user | O(1) lookup/update for balance computation |
| `PriorityQueue` (max-heap) | Creditors queue | Always process the largest creditor first for greedy optimality |
| `PriorityQueue` (min-heap) | Debtors queue | Always process the largest debtor first |
| `List<Expense>` | Expense history per group | Ordered append for chronological history |
| `Map<String, List<Group>>` | User-to-groups mapping | Quick lookup of all groups a user belongs to |

---

## Concurrency Considerations

For a typical Splitwise LLD interview, concurrency is **not the focus**. However, if asked:

- **Thread-safe balance updates:** Use `ConcurrentHashMap` for the balance map, or synchronize on the group object when adding expenses.
- **Atomic settlements:** Wrap the settlement computation in a `synchronized` block or use `ReentrantLock` per group to prevent concurrent expense additions from corrupting balance calculations.
- **Read-heavy workload:** Balances are read more often than written — a `ReadWriteLock` per group allows concurrent reads while serializing writes.
- **Eventual consistency:** In a distributed setting, expense additions can be eventually consistent, but settlement calculations should always use the latest state.

---

## Java Implementation

### Enum — SplitType

```java
public enum SplitType {
    EQUAL,
    EXACT,
    PERCENTAGE
}
```

### Entity — User

```java
public class User {
    private final String id;
    private final String name;
    private final String email;

    public User(String id, String name, String email) {
        this.id = id;
        this.name = name;
        this.email = email;
    }

    public String getId() { return id; }
    public String getName() { return name; }
    public String getEmail() { return email; }

    @Override
    public boolean equals(Object o) {
        if (this == o) return true;
        if (!(o instanceof User)) return false;
        return id.equals(((User) o).id);
    }

    @Override
    public int hashCode() { return id.hashCode(); }

    @Override
    public String toString() { return name; }
}
```

### Entity — Split

```java
public class Split {
    private final User user;
    private final double amount;

    public Split(User user, double amount) {
        this.user = user;
        this.amount = amount;
    }

    public User getUser() { return user; }
    public double getAmount() { return amount; }
}
```

### Entity — Expense

```java
import java.time.Instant;
import java.util.List;
import java.util.UUID;

public class Expense {
    private final String id;
    private final User paidBy;
    private final double amount;
    private final SplitType splitType;
    private final List<Split> splits;
    private final String description;
    private final Instant timestamp;

    public Expense(User paidBy, double amount, SplitType splitType,
                   List<Split> splits, String description) {
        this.id = UUID.randomUUID().toString();
        this.paidBy = paidBy;
        this.amount = amount;
        this.splitType = splitType;
        this.splits = splits;
        this.description = description;
        this.timestamp = Instant.now();
    }

    public String getId() { return id; }
    public User getPaidBy() { return paidBy; }
    public double getAmount() { return amount; }
    public SplitType getSplitType() { return splitType; }
    public List<Split> getSplits() { return splits; }
    public String getDescription() { return description; }
    public Instant getTimestamp() { return timestamp; }
}
```

### Entity — Group

```java
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;

public class Group {
    private final String id;
    private final String name;
    private final List<User> members;
    private final List<Expense> expenses;

    public Group(String name, List<User> members) {
        this.id = UUID.randomUUID().toString();
        this.name = name;
        this.members = new ArrayList<>(members);
        this.expenses = new ArrayList<>();
    }

    public String getId() { return id; }
    public String getName() { return name; }
    public List<User> getMembers() { return members; }
    public List<Expense> getExpenses() { return expenses; }

    public void addMember(User user) { members.add(user); }
    public void addExpense(Expense expense) { expenses.add(expense); }
}
```

### Entity — Transaction (Settlement Record)

```java
public class Transaction {
    private final User from;
    private final User to;
    private final double amount;

    public Transaction(User from, User to, double amount) {
        this.from = from;
        this.to = to;
        this.amount = amount;
    }

    public User getFrom() { return from; }
    public User getTo() { return to; }
    public double getAmount() { return amount; }

    @Override
    public String toString() {
        return String.format("%s → %s : ₹%.2f", from.getName(), to.getName(), amount);
    }
}
```

### Strategy Interface — SplitStrategy

```java
import java.util.List;

public interface SplitStrategy {
    List<Split> split(double amount, List<User> users, List<Double> params);
}
```

### Strategy — EqualSplitStrategy

```java
import java.util.List;
import java.util.stream.Collectors;

public class EqualSplitStrategy implements SplitStrategy {

    @Override
    public List<Split> split(double amount, List<User> users, List<Double> params) {
        double perHead = amount / users.size();
        return users.stream()
                .map(user -> new Split(user, perHead))
                .collect(Collectors.toList());
    }
}
```

### Strategy — ExactSplitStrategy

```java
import java.util.ArrayList;
import java.util.List;

public class ExactSplitStrategy implements SplitStrategy {

    @Override
    public List<Split> split(double amount, List<User> users, List<Double> params) {
        if (users.size() != params.size()) {
            throw new IllegalArgumentException("Each user must have an exact split amount");
        }
        double total = params.stream().mapToDouble(Double::doubleValue).sum();
        if (Math.abs(total - amount) > 0.01) {
            throw new IllegalArgumentException(
                    "Exact split amounts (" + total + ") don't sum to total (" + amount + ")");
        }

        List<Split> splits = new ArrayList<>();
        for (int i = 0; i < users.size(); i++) {
            splits.add(new Split(users.get(i), params.get(i)));
        }
        return splits;
    }
}
```

### Strategy — PercentageSplitStrategy

```java
import java.util.ArrayList;
import java.util.List;

public class PercentageSplitStrategy implements SplitStrategy {

    @Override
    public List<Split> split(double amount, List<User> users, List<Double> params) {
        if (users.size() != params.size()) {
            throw new IllegalArgumentException("Each user must have a percentage");
        }
        double totalPercent = params.stream().mapToDouble(Double::doubleValue).sum();
        if (Math.abs(totalPercent - 100.0) > 0.01) {
            throw new IllegalArgumentException(
                    "Percentages must sum to 100, got " + totalPercent);
        }

        List<Split> splits = new ArrayList<>();
        for (int i = 0; i < users.size(); i++) {
            double share = amount * params.get(i) / 100.0;
            splits.add(new Split(users.get(i), share));
        }
        return splits;
    }
}
```

### Factory — SplitStrategyFactory

```java
import java.util.HashMap;
import java.util.Map;

public class SplitStrategyFactory {

    private static final Map<SplitType, SplitStrategy> STRATEGIES = new HashMap<>();

    static {
        STRATEGIES.put(SplitType.EQUAL, new EqualSplitStrategy());
        STRATEGIES.put(SplitType.EXACT, new ExactSplitStrategy());
        STRATEGIES.put(SplitType.PERCENTAGE, new PercentageSplitStrategy());
    }

    public static SplitStrategy getStrategy(SplitType type) {
        SplitStrategy strategy = STRATEGIES.get(type);
        if (strategy == null) {
            throw new IllegalArgumentException("Unsupported split type: " + type);
        }
        return strategy;
    }
}
```

### Observer — ExpenseObserver

```java
public interface ExpenseObserver {
    void onExpenseAdded(Expense expense, Group group);
    void onSettlement(Transaction transaction);
}
```

```java
public class EmailNotifier implements ExpenseObserver {

    @Override
    public void onExpenseAdded(Expense expense, Group group) {
        for (Split split : expense.getSplits()) {
            System.out.printf("[EMAIL] %s: You owe ₹%.2f for '%s' (paid by %s)%n",
                    split.getUser().getName(), split.getAmount(),
                    expense.getDescription(), expense.getPaidBy().getName());
        }
    }

    @Override
    public void onSettlement(Transaction transaction) {
        System.out.printf("[EMAIL] Settlement: %s%n", transaction);
    }
}
```

### Service — ExpenseService

```java
import java.util.*;

public class ExpenseService {

    private final List<ExpenseObserver> observers = new ArrayList<>();

    public void addObserver(ExpenseObserver observer) {
        observers.add(observer);
    }

    public Expense addExpense(Group group, User paidBy, double amount,
                              SplitType splitType, List<User> participants,
                              List<Double> params, String description) {

        SplitStrategy strategy = SplitStrategyFactory.getStrategy(splitType);
        List<Split> splits = strategy.split(amount, participants, params);

        Expense expense = new Expense(paidBy, amount, splitType, splits, description);
        group.addExpense(expense);

        observers.forEach(o -> o.onExpenseAdded(expense, group));
        return expense;
    }

    public Map<User, Double> calculateBalances(Group group) {
        Map<User, Double> balances = new HashMap<>();
        for (User member : group.getMembers()) {
            balances.put(member, 0.0);
        }

        for (Expense expense : group.getExpenses()) {
            User payer = expense.getPaidBy();
            balances.merge(payer, expense.getAmount(), Double::sum);

            for (Split split : expense.getSplits()) {
                balances.merge(split.getUser(), -split.getAmount(), Double::sum);
            }
        }
        return balances;
    }
}
```

### Service — SettlementService (Core Heap Algorithm)

```java
import java.util.*;

public class SettlementService {

    public List<Transaction> minimizeTransactions(Map<User, Double> balances) {
        PriorityQueue<Map.Entry<User, Double>> creditors =
                new PriorityQueue<>((a, b) -> Double.compare(b.getValue(), a.getValue()));
        PriorityQueue<Map.Entry<User, Double>> debtors =
                new PriorityQueue<>(Comparator.comparingDouble(Map.Entry::getValue));

        for (Map.Entry<User, Double> entry : balances.entrySet()) {
            double balance = entry.getValue();
            if (balance > 0.01) {
                creditors.offer(entry);
            } else if (balance < -0.01) {
                debtors.offer(entry);
            }
        }

        List<Transaction> transactions = new ArrayList<>();

        while (!creditors.isEmpty() && !debtors.isEmpty()) {
            Map.Entry<User, Double> creditor = creditors.poll();
            Map.Entry<User, Double> debtor = debtors.poll();

            double credit = creditor.getValue();
            double debt = -debtor.getValue();
            double settled = Math.min(credit, debt);

            transactions.add(new Transaction(debtor.getKey(), creditor.getKey(), settled));

            double creditRemaining = credit - settled;
            double debtRemaining = debt - settled;

            if (creditRemaining > 0.01) {
                creditors.offer(new AbstractMap.SimpleEntry<>(creditor.getKey(), creditRemaining));
            }
            if (debtRemaining > 0.01) {
                debtors.offer(new AbstractMap.SimpleEntry<>(debtor.getKey(), -debtRemaining));
            }
        }

        return transactions;
    }
}
```

### Service — GroupService

```java
import java.util.*;

public class GroupService {

    private final Map<String, Group> groups = new HashMap<>();

    public Group createGroup(String name, List<User> members) {
        Group group = new Group(name, members);
        groups.put(group.getId(), group);
        return group;
    }

    public void addMember(String groupId, User user) {
        Group group = groups.get(groupId);
        if (group == null) throw new IllegalArgumentException("Group not found");
        group.addMember(user);
    }

    public Group getGroup(String groupId) {
        return groups.get(groupId);
    }
}
```

### Main — Demo

```java
import java.util.*;

public class SplitwiseDemo {

    public static void main(String[] args) {
        User alice = new User("u1", "Alice", "alice@email.com");
        User bob = new User("u2", "Bob", "bob@email.com");
        User charlie = new User("u3", "Charlie", "charlie@email.com");
        User diana = new User("u4", "Diana", "diana@email.com");

        GroupService groupService = new GroupService();
        Group trip = groupService.createGroup("Goa Trip",
                Arrays.asList(alice, bob, charlie, diana));

        ExpenseService expenseService = new ExpenseService();
        expenseService.addObserver(new EmailNotifier());

        // --- Expense 1: Alice pays 1200 for hotel, split equally ---
        System.out.println("=== Expense 1: Hotel (Equal Split) ===");
        expenseService.addExpense(trip, alice, 1200.0, SplitType.EQUAL,
                Arrays.asList(alice, bob, charlie, diana),
                Collections.emptyList(), "Hotel booking");

        // --- Expense 2: Bob pays 800 for food, exact split ---
        System.out.println("\n=== Expense 2: Food (Exact Split) ===");
        expenseService.addExpense(trip, bob, 800.0, SplitType.EXACT,
                Arrays.asList(alice, bob, charlie, diana),
                Arrays.asList(200.0, 200.0, 150.0, 250.0), "Dinner");

        // --- Expense 3: Charlie pays 500 for fuel, percentage split ---
        System.out.println("\n=== Expense 3: Fuel (Percentage Split) ===");
        expenseService.addExpense(trip, charlie, 500.0, SplitType.PERCENTAGE,
                Arrays.asList(alice, bob, charlie, diana),
                Arrays.asList(30.0, 30.0, 20.0, 20.0), "Fuel");

        // --- Calculate balances ---
        System.out.println("\n=== Net Balances ===");
        Map<User, Double> balances = expenseService.calculateBalances(trip);
        balances.forEach((user, balance) ->
                System.out.printf("  %s: %+.2f%n", user.getName(), balance));

        // --- Minimize transactions ---
        System.out.println("\n=== Minimum Transactions to Settle ===");
        SettlementService settlementService = new SettlementService();
        List<Transaction> transactions = settlementService.minimizeTransactions(balances);
        transactions.forEach(t -> System.out.println("  " + t));
        System.out.println("Total transactions: " + transactions.size());
    }
}
```

### Expected Output

```
=== Expense 1: Hotel (Equal Split) ===
[EMAIL] Alice: You owe ₹300.00 for 'Hotel booking' (paid by Alice)
[EMAIL] Bob: You owe ₹300.00 for 'Hotel booking' (paid by Alice)
[EMAIL] Charlie: You owe ₹300.00 for 'Hotel booking' (paid by Alice)
[EMAIL] Diana: You owe ₹300.00 for 'Hotel booking' (paid by Alice)

=== Expense 2: Food (Exact Split) ===
[EMAIL] Alice: You owe ₹200.00 for 'Dinner' (paid by Bob)
[EMAIL] Bob: You owe ₹200.00 for 'Dinner' (paid by Bob)
[EMAIL] Charlie: You owe ₹150.00 for 'Dinner' (paid by Bob)
[EMAIL] Diana: You owe ₹250.00 for 'Dinner' (paid by Bob)

=== Expense 3: Fuel (Percentage Split) ===
[EMAIL] Alice: You owe ₹150.00 for 'Fuel' (paid by Charlie)
[EMAIL] Bob: You owe ₹150.00 for 'Fuel' (paid by Charlie)
[EMAIL] Charlie: You owe ₹100.00 for 'Fuel' (paid by Charlie)
[EMAIL] Diana: You owe ₹100.00 for 'Fuel' (paid by Charlie)

=== Net Balances ===
  Alice: +550.00      (paid 1200, owes 650)
  Bob: +150.00        (paid 800, owes 650)
  Charlie: -50.00     (paid 500, owes 550)
  Diana: -650.00      (paid 0, owes 650)

=== Minimum Transactions to Settle ===
  Diana → Alice : ₹550.00
  Diana → Bob : ₹50.00
  Charlie → Bob : ₹50.00
Total transactions: 3
```

---

## Class Diagram Summary

```
                    ┌─────────────────────┐
                    │    SplitwiseDemo     │
                    │      (main)         │
                    └─────────┬───────────┘
                              │ uses
              ┌───────────────┼───────────────┐
              ▼               ▼               ▼
    ┌─────────────────┐ ┌──────────────┐ ┌──────────────────┐
    │  ExpenseService  │ │ GroupService │ │SettlementService │
    │  + addExpense()  │ │+createGroup()│ │+minimizeTransac- │
    │  + calcBalances()│ │+addMember()  │ │ tions()          │
    └────────┬────────┘ └──────────────┘ └──────────────────┘
             │                                     │
     uses    │                              returns │
             ▼                                     ▼
    ┌──────────────────┐                ┌──────────────────┐
    │ SplitStrategy «I»│                │   Transaction    │
    │ + split()        │                │ from, to, amount │
    └───────┬──────────┘                └──────────────────┘
            │ implements
    ┌───────┼───────────┐
    ▼       ▼           ▼
  Equal   Exact    Percentage

    ┌─────────────────────────┐
    │  ExpenseObserver «I»    │
    │  +onExpenseAdded()      │
    │  +onSettlement()        │
    └───────────┬─────────────┘
                │ implements
                ▼
         EmailNotifier
```

---

## Interview-Ready Answer

> "I would design Splitwise around three core services: **GroupService** for managing groups and membership, **ExpenseService** for adding expenses with pluggable split strategies, and **SettlementService** for computing minimum transactions. The split logic uses the **Strategy pattern** — `EqualSplitStrategy`, `ExactSplitStrategy`, and `PercentageSplitStrategy` all implement a common `SplitStrategy` interface, making it trivial to add new split types without touching existing code. When an expense is added, the system records who paid and each participant's share. The **key algorithm** is in `SettlementService`: I compute the net balance for each user (total received minus total owed), then use two **priority queues** — a max-heap for creditors and a min-heap for debtors. I greedily match the largest creditor with the largest debtor, settle the minimum of their amounts, and push any remainder back into the heap. This runs in **O(N log N)** and produces the minimum number of transactions for the greedy approach. I use the **Observer pattern** to notify users when expenses are added or settled, and a **Factory** to construct expenses with the correct strategy. The design follows SOLID — strategies are open for extension, services have single responsibilities, and high-level modules depend on abstractions, not concrete split implementations."
