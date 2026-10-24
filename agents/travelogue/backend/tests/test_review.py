import unittest
from backend.models import ReviewAudit, TripRequest, assess_review, validate_itinerary
from backend.agents import demo_plan


class ReviewTests(unittest.TestCase):
    def setUp(self):
        self.request = TripRequest(country='IT', start_date='2026-11-10', end_date='2026-11-14', budget='100000')
        self.plan = demo_plan(self.request)

    def test_structured_general_advice_cannot_veto_a_draft(self):
        audit = ReviewAudit(issues=[{'category':'travel_advice','message':'Rome can be crowded. Book ahead.'}])
        blockers, warnings = assess_review(audit, self.plan, self.request, [])
        self.assertEqual(blockers, [])
        self.assertIn('Rome can be crowded. Book ahead.', warnings)

    def test_unsubstantiated_conflict_remains_a_disclosed_concern(self):
        audit = ReviewAudit(issues=[{'category':'source_contradiction', 'message':'The attraction is closed.',
                                    'activity_quote':self.plan.days[0].activities[0].title,
                                    'evidence_quote':'The attraction is closed every November.'}])
        blockers, warnings = assess_review(audit, self.plan, self.request, [])
        self.assertEqual(blockers, [])
        self.assertEqual(warnings, ['Review concern (unverified): The attraction is closed.'])

    def test_quoted_schedule_contradiction_still_blocks(self):
        self.plan.days[0].activities[0].note = 'Enter the palace at 18:00.'
        audit = ReviewAudit(issues=[{'category':'schedule_conflict','message':'Arrival is after closing.',
                                    'activity_quote':'Enter the palace at 18:00.',
                                    'evidence_quote':'The palace closes at 17:00.'}])
        blockers, warnings = assess_review(audit, self.plan, self.request, [{'excerpt':'The palace closes at 17:00.'}])
        self.assertEqual(blockers, ['Arrival is after closing.'])
        self.assertEqual(warnings, [])

    def test_advisory_review_does_not_bypass_hard_validation(self):
        self.plan.days[0].activities[0].estimate = self.request.budget + 1
        audit = ReviewAudit(warnings=['Check seasonal prices.'])
        blockers, warnings = assess_review(audit, self.plan, self.request, [])
        self.assertEqual(blockers, [])
        self.assertIn('Estimated activity costs exceed the budget.', validate_itinerary(self.plan,self.request,{'curated-rome'}))
