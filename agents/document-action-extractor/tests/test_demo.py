from main import DEMO_ACTIONS, FIELDS


def test_demo_has_four_action_items():
    assert len(DEMO_ACTIONS) == 4


def test_demo_has_required_fields():
    for action in DEMO_ACTIONS:
        assert set(FIELDS).issubset(action)


def test_demo_does_not_guess_relative_date():
    budget_task = next(
        action for action in DEMO_ACTIONS
        if action["task"] == "Review the budget"
    )
    assert budget_task["deadline"] == "Next Monday (date not resolved)"
