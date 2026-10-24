class BudgetPlanner:
    def validate(self, action):
        budget=action.get('budget',100)
        if budget>1000: raise ValueError('Budget exceeded')
        return True
