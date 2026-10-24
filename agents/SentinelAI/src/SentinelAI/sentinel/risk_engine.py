class RiskEngine:
    def assess(self, action):
        impact=action.get('impact',1)
        sensitivity=action.get('sensitivity',1)
        permissions=action.get('permissions',1)
        reversibility=action.get('reversibility',1)
        return impact+sensitivity+permissions+(6-reversibility)
