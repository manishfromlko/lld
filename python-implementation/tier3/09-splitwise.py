"""
Splitwise — Expense Splitter
- Strategy Pattern: SplitStrategy (Equal / Exact / Percentage)
- Core Algorithm: Minimum transactions via two priority queues (greedy heap)
- Observer Pattern: notify on expense added
"""

import uuid
import heapq
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


# ──────────────────────────────────────────────
#  Enums
# ──────────────────────────────────────────────

class SplitType(Enum):
    EQUAL = "EQUAL"
    EXACT = "EXACT"
    PERCENTAGE = "PERCENTAGE"


# ──────────────────────────────────────────────
#  Entities
# ──────────────────────────────────────────────

@dataclass(eq=True)
class User:
    user_id: str
    name: str
    email: str

    def __hash__(self):
        return hash(self.user_id)

    def __str__(self):
        return self.name


@dataclass
class Split:
    user: User
    amount: float


@dataclass
class Expense:
    expense_id: str
    paid_by: User
    amount: float
    split_type: SplitType
    splits: list[Split]
    description: str
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class Group:
    group_id: str
    name: str
    members: list[User]
    expenses: list[Expense] = field(default_factory=list)


@dataclass
class Transaction:
    from_user: User
    to_user: User
    amount: float

    def __str__(self):
        return f"{self.from_user.name} → {self.to_user.name} : ₹{self.amount:.2f}"


# ──────────────────────────────────────────────
#  Split Strategy (Strategy Pattern)
# ──────────────────────────────────────────────

class SplitStrategy(ABC):
    @abstractmethod
    def split(self, amount: float, users: list[User], params: list[float]) -> list[Split]:
        pass


class EqualSplitStrategy(SplitStrategy):
    def split(self, amount: float, users: list[User], params: list[float]) -> list[Split]:
        per_head = amount / len(users)
        return [Split(u, per_head) for u in users]


class ExactSplitStrategy(SplitStrategy):
    def split(self, amount: float, users: list[User], params: list[float]) -> list[Split]:
        if len(users) != len(params):
            raise ValueError("Each user must have an exact amount")
        if abs(sum(params) - amount) > 0.01:
            raise ValueError(f"Exact amounts {sum(params)} don't sum to {amount}")
        return [Split(u, p) for u, p in zip(users, params)]


class PercentageSplitStrategy(SplitStrategy):
    def split(self, amount: float, users: list[User], params: list[float]) -> list[Split]:
        if abs(sum(params) - 100) > 0.01:
            raise ValueError(f"Percentages must sum to 100, got {sum(params)}")
        return [Split(u, amount * p / 100) for u, p in zip(users, params)]


_STRATEGIES: dict[SplitType, SplitStrategy] = {
    SplitType.EQUAL: EqualSplitStrategy(),
    SplitType.EXACT: ExactSplitStrategy(),
    SplitType.PERCENTAGE: PercentageSplitStrategy(),
}


# ──────────────────────────────────────────────
#  Observer
# ──────────────────────────────────────────────

class ExpenseObserver(ABC):
    @abstractmethod
    def on_expense_added(self, expense: Expense, group: Group):
        pass

    @abstractmethod
    def on_settlement(self, txn: Transaction):
        pass


class EmailNotifier(ExpenseObserver):
    def on_expense_added(self, expense: Expense, group: Group):
        for split in expense.splits:
            print(f"  [EMAIL] {split.user.name}: You owe ₹{split.amount:.2f} "
                  f"for '{expense.description}' (paid by {expense.paid_by.name})")

    def on_settlement(self, txn: Transaction):
        print(f"  [EMAIL] Settlement: {txn}")


# ──────────────────────────────────────────────
#  Services
# ──────────────────────────────────────────────

class GroupService:
    def __init__(self):
        self._groups: dict[str, Group] = {}

    def create_group(self, name: str, members: list[User]) -> Group:
        g = Group(str(uuid.uuid4()), name, list(members))
        self._groups[g.group_id] = g
        return g

    def get_group(self, group_id: str) -> Group:
        return self._groups[group_id]


class ExpenseService:
    def __init__(self):
        self._observers: list[ExpenseObserver] = []

    def add_observer(self, obs: ExpenseObserver):
        self._observers.append(obs)

    def add_expense(self, group: Group, paid_by: User, amount: float,
                    split_type: SplitType, participants: list[User],
                    params: list[float], description: str) -> Expense:
        strategy = _STRATEGIES[split_type]
        splits = strategy.split(amount, participants, params)
        expense = Expense(str(uuid.uuid4()), paid_by, amount, split_type, splits, description)
        group.expenses.append(expense)
        for obs in self._observers:
            obs.on_expense_added(expense, group)
        return expense

    def calculate_balances(self, group: Group) -> dict[User, float]:
        balances: dict[User, float] = {m: 0.0 for m in group.members}
        for expense in group.expenses:
            balances[expense.paid_by] = balances.get(expense.paid_by, 0) + expense.amount
            for split in expense.splits:
                balances[split.user] = balances.get(split.user, 0) - split.amount
        return balances


class SettlementService:
    """
    Minimum transactions algorithm using two priority queues (greedy approach).
    O(N log N) — optimal for most practical inputs.
    """

    def minimize_transactions(self, balances: dict[User, float]) -> list[Transaction]:
        # max-heap for creditors (negate for Python's min-heap)
        creditors: list[tuple[float, User]] = []
        # min-heap for debtors (store as negative balance)
        debtors: list[tuple[float, User]] = []

        for user, balance in balances.items():
            if balance > 0.01:
                heapq.heappush(creditors, (-balance, user))  # negate for max-heap
            elif balance < -0.01:
                heapq.heappush(debtors, (balance, user))     # already negative

        transactions: list[Transaction] = []

        while creditors and debtors:
            credit_neg, creditor = heapq.heappop(creditors)
            debt, debtor = heapq.heappop(debtors)

            credit = -credit_neg    # restore positive value
            debt_amount = -debt     # restore positive value

            settled = min(credit, debt_amount)
            transactions.append(Transaction(debtor, creditor, settled))

            remaining_credit = credit - settled
            remaining_debt = debt_amount - settled

            if remaining_credit > 0.01:
                heapq.heappush(creditors, (-remaining_credit, creditor))
            if remaining_debt > 0.01:
                heapq.heappush(debtors, (-remaining_debt, debtor))

        return transactions


# ──────────────────────────────────────────────
#  Demo
# ──────────────────────────────────────────────

if __name__ == "__main__":
    alice = User("u1", "Alice", "alice@mail.com")
    bob = User("u2", "Bob", "bob@mail.com")
    charlie = User("u3", "Charlie", "charlie@mail.com")
    diana = User("u4", "Diana", "diana@mail.com")

    group_svc = GroupService()
    trip = group_svc.create_group("Goa Trip", [alice, bob, charlie, diana])

    expense_svc = ExpenseService()
    expense_svc.add_observer(EmailNotifier())
    settlement_svc = SettlementService()

    print("=== Expense 1: Hotel — Equal Split (₹1200) ===")
    expense_svc.add_expense(trip, alice, 1200.0, SplitType.EQUAL,
                            [alice, bob, charlie, diana], [], "Hotel booking")

    print("\n=== Expense 2: Dinner — Exact Split (₹800) ===")
    expense_svc.add_expense(trip, bob, 800.0, SplitType.EXACT,
                            [alice, bob, charlie, diana],
                            [200.0, 200.0, 150.0, 250.0], "Dinner")

    print("\n=== Expense 3: Fuel — Percentage Split (₹500) ===")
    expense_svc.add_expense(trip, charlie, 500.0, SplitType.PERCENTAGE,
                            [alice, bob, charlie, diana],
                            [30.0, 30.0, 20.0, 20.0], "Fuel")

    print("\n=== Net Balances ===")
    balances = expense_svc.calculate_balances(trip)
    for user, bal in balances.items():
        sign = "+" if bal >= 0 else ""
        print(f"  {user.name}: {sign}{bal:.2f}")

    print("\n=== Minimum Transactions to Settle ===")
    txns = settlement_svc.minimize_transactions(balances)
    for t in txns:
        print(f"  {t}")
    print(f"Total transactions: {len(txns)}")

    print("\n=== Simple 3-Person Example ===")
    # A pays 300, B and C owe 100 each
    u_a = User("a", "A", "")
    u_b = User("b", "B", "")
    u_c = User("c", "C", "")
    simple_balances = {u_a: 200.0, u_b: -100.0, u_c: -100.0}
    for t in settlement_svc.minimize_transactions(simple_balances):
        print(f"  {t}")
