from .sentinel.risk_engine import RiskEngine
from .sentinel.policy_engine import PolicyEngine
from .sentinel.action_receipt import ActionReceipt
from .sentinel.budget_planner import BudgetPlanner
class DecisionEngine:
    def __init__(self):
        self.risk=RiskEngine(); self.policy=PolicyEngine(); self.budget=BudgetPlanner()
    def evaluate(self,action):
        score=self.risk.assess(action)
        allowed=self.policy.evaluate(action,score)
        self.budget.validate(action)
        return ActionReceipt().create(action,score,allowed)
