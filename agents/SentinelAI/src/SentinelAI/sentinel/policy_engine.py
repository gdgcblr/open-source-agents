class PolicyEngine:
    def evaluate(self, action, risk):
        return risk < 15 and not action.get('blocked',False)
