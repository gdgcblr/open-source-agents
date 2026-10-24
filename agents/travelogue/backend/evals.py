"""Offline structural regression cases. These are not factual-quality scores."""
import json
from pathlib import Path
from pydantic import ValidationError
from .agents import demo_plan, lookup_destinations
from .models import TripRequest, validate_itinerary


def cases():
    base = dict(country='JP', start_date='2026-11-10', end_date='2026-11-14', budget='100000', currency='INR', travelers=2)
    result = []
    for code in ['JP','IN','IT','FR','TH']:
        for length in [1, 5]:
            result.append(dict(id=f'standard-{code}-{length}', category='standard', request=dict(base, country=code, end_date=f'2026-11-{9+length:02d}'), expected='valid'))
    for i, interests in enumerate(['Vegetarian food','Wheelchair-accessible places','Travel with young children','Quiet walks only','Museums and local architecture']):
        result.append(dict(id=f'preferences-{i}', category='preferences', request=dict(base, interests=interests), expected='disclose_unassessed'))
    for i, budget in enumerate(['0.01','1','10','100','1000']):
        result.append(dict(id=f'difficult-{i}', category='difficult', request=dict(base, budget=budget), expected='disclose_estimates'))
    for i, change in enumerate([{'country':'XX'},{'end_date':'2026-11-01'},{'end_date':'2026-12-20'},{'budget':'0'},{'currency':'XXX'}]):
        result.append(dict(id=f'invalid-{i}', category='invalid', request=dict(base, **change), expected='reject'))
    for mutation in ['wrong-country','invented-source','missing-day','over-budget','wrong-travelers']:
        result.append(dict(id=f'adversarial-{mutation}', category='adversarial', request=base.copy(), expected='reject_output', mutation=mutation))
    return result


def evaluate(case):
    try:
        request = TripRequest.model_validate(case['request'])
    except ValidationError:
        return case['expected'] == 'reject'
    if case['expected'] == 'reject':
        return False
    plan = demo_plan(request)
    mutation = case.get('mutation')
    if mutation == 'wrong-country': plan.days[0].activities[0].place_id = 'paris'
    if mutation == 'invented-source': plan.days[0].activities[0].source_ids = ['invented']
    if mutation == 'missing-day': plan.days.pop()
    if mutation == 'over-budget': plan.days[0].activities[0].estimate = request.budget + 1
    if mutation == 'wrong-travelers': plan.travelers += 1
    errors = validate_itinerary(plan, request, {f'curated-{p["id"]}' for p in lookup_destinations(request.country)})
    if case['expected'] == 'reject_output': return bool(errors)
    if errors: return False
    if case['expected'] == 'disclose_unassessed': return any('not been evaluated' in w for w in plan.warnings)
    if case['expected'] == 'disclose_estimates': return any('not researched prices' in w for w in plan.warnings)
    return True


def main():
    dataset = cases()
    results = [{'id': c['id'], 'category': c['category'], 'passed': evaluate(c)} for c in dataset]
    report = {'dataset_version': 'structural-v1', 'mode': 'offline scripted fixtures',
              'passed': sum(r['passed'] for r in results), 'total': len(results),
              'factual_correctness': 'NOT EVALUATED', 'preference_satisfaction': 'NOT EVALUATED',
              'live_gemma_quality': 'NOT EVALUATED', 'cases': results}
    runtime = Path(__file__).resolve().parent.parent / '.runtime'
    runtime.mkdir(exist_ok=True)
    (runtime/'eval-results.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report, indent=2))
    if report['passed'] != report['total']: raise SystemExit(1)


if __name__ == '__main__':
    main()
