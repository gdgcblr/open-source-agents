from .decision import DecisionEngine
class SecureAgent:
    def __init__(self):
        self.engine=DecisionEngine()
    def run(self,action):
        return self.engine.evaluate(action)
