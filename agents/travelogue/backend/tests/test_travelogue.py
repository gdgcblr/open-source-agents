import asyncio
import json
import os
import tempfile
import time
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch
import httpx
from backend.app import create_app
from backend.agents import build_workflow, demo_plan, plan_trip, generation_settings, compact_context
from backend.models import TripRequest, Itinerary, validate_itinerary


def trip(**changes):
    return TripRequest.model_validate(dict(
        dict(country="JP", start_date="2026-11-10", end_date="2026-11-14", budget="100000", currency="INR", travelers=2),
        **changes))


class ApplicationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {"TRAVELOGUE_MODE": "demo", "MODEL_PROVIDER": "demo"})
        self.env.start()
        self.app = create_app(Path(self.temp.name))
        self.lifespan = self.app.router.lifespan_context(self.app)
        await self.lifespan.__aenter__()
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app), base_url='http://testserver')

    async def asyncTearDown(self):
        await self.client.aclose()
        await self.lifespan.__aexit__(None, None, None)
        self.env.stop()
        self.temp.cleanup()

    async def test_catalog_and_seed_status(self):
        catalog = (await self.client.get('/api/catalog')).json()
        self.assertEqual(len(catalog['countries']), 5)
        entries = (await self.client.get('/api/entries')).json()
        self.assertEqual(len(entries), 3)
        self.assertTrue(all(not e['published'] for e in entries))

    async def test_journal_lifecycle_and_reload(self):
        payload = dict(place_id="paris", title="A small discovery", visited_on="2026-01-10", body="<script>Text stays text</script>")
        created = await self.client.post('/api/entries', json=payload)
        self.assertEqual(created.status_code, 201)
        ident = created.json()['id']
        self.assertEqual(created.json()['country'], 'FR')
        payload['title'] = 'An updated memory'
        self.assertEqual((await self.client.put(f'/api/entries/{ident}', json=payload)).status_code, 200)
        from backend.storage import Store
        reloaded = Store(Path(self.temp.name)).entry(ident)
        self.assertEqual(reloaded['title'], payload['title'])
        self.assertEqual(reloaded['body'], payload['body'])
        self.assertEqual((await self.client.delete(f'/api/entries/{ident}')).status_code, 204)
        self.assertEqual((await self.client.delete(f'/api/entries/{ident}')).status_code, 404)

    async def test_validation_and_publication_disabled(self):
        base = dict(place_id='paris', title='Memory', visited_on='2026-01-01')
        for change in [dict(place_id='unknown'), dict(title='  '), dict(visited_on='2999-01-01')]:
            self.assertEqual((await self.client.post('/api/entries', json=dict(base, **change))).status_code, 422)
        self.assertEqual((await self.client.post('/api/entries', json=dict(base, published=True))).status_code, 400)

    async def test_external_origin_and_host_are_blocked(self):
        self.assertEqual((await self.client.get('/api/entries', headers={'Origin': 'https://untrusted.example'})).status_code, 403)
        self.assertEqual((await self.client.get('/api/entries', headers={'Host': 'public.example'})).status_code, 403)

    async def test_invalid_media_leaves_no_orphan(self):
        ident = (await self.client.get('/api/entries')).json()[0]['id']
        response = await self.client.post(f'/api/entries/{ident}/media', files={'file': ('photo.png', b'not an image', 'image/png')})
        self.assertEqual(response.status_code, 415)
        self.assertEqual(list((Path(self.temp.name)/'media').iterdir()), [])

    async def test_missing_inspector_fails_closed(self):
        ident = (await self.client.get('/api/entries')).json()[0]['id']
        with patch('backend.app.shutil.which', return_value=None):
            response = await self.client.post(f'/api/entries/{ident}/media', files={'file': ('a.png', b'\x89PNG\r\n\x1a\ninvalid', 'image/png')})
        self.assertEqual(response.status_code, 503)
        self.assertEqual(list((Path(self.temp.name)/'media').iterdir()), [])

    async def test_demo_plan_runs_saves_and_preserves_sources(self):
        response = await self.client.post('/api/planner/runs', json=trip().model_dump(mode='json'))
        self.assertEqual(response.status_code, 202)
        ident = response.json()['id']
        for _ in range(60):
            run = (await self.client.get(f'/api/planner/runs/{ident}')).json()
            if run['status'] in {'completed', 'failed'}:
                break
            await asyncio.sleep(.03)
        self.assertEqual(run['status'], 'completed', run)
        self.assertEqual(len(run['stages']), 5)
        self.assertTrue(all(state == 'completed' for state in run['stage_states'].values()))
        self.assertIn('finished_at', run)
        self.assertEqual(run['result']['model'], 'scripted-demo')
        self.assertIn('SCRIPTED DEMO', run['result']['itinerary']['warnings'][0])
        self.assertEqual((await self.client.post(f'/api/plans/{ident}')).status_code, 201)
        self.assertEqual(len((await self.client.get('/api/plans')).json()), 1)
        edited = run['result']['itinerary']
        edited['days'][0]['activities'][0]['note'] = 'Leave the afternoon free for a quiet walk.'
        saved = await self.client.post(f'/api/plans/{ident}', json=edited)
        self.assertEqual(saved.status_code, 201)
        self.assertEqual(saved.json()['result']['itinerary']['days'][0]['activities'][0]['note'], edited['days'][0]['activities'][0]['note'])
        edited['days'][0]['activities'][0]['source_ids'] = ['invented']
        self.assertEqual((await self.client.post(f'/api/plans/{ident}', json=edited)).status_code, 422)
        self.assertEqual((await self.client.get('/api/planner/runs/missing')).status_code, 404)

    async def test_invalid_trip_and_unsuccessful_save(self):
        payload = trip().model_dump(mode='json')
        self.assertEqual((await self.client.post('/api/planner/runs', json=dict(payload, end_date='2026-11-01'))).status_code, 422)
        self.assertEqual((await self.client.post('/api/plans/missing')).status_code, 400)


class AgentTests(unittest.IsolatedAsyncioTestCase):
    async def test_adk_parallel_then_sequential_structure(self):
        workflow = build_workflow('http://localhost:11434', 'gemma3:4b', lambda *args: None)
        self.assertEqual([a.name for a in workflow.sub_agents], ['research','itinerary_planner','trip_reviewer'])
        self.assertEqual([a.name for a in workflow.sub_agents[0].sub_agents], ['destination_researcher','season_researcher'])
        self.assertEqual([a.output_key for a in workflow.sub_agents[0].sub_agents], ['destinations','seasons'])

    async def test_actual_adk_orchestration_with_mock_ollama_transport(self):
        request = trip()
        expected = demo_plan(request).model_dump_json()
        calls = []
        def handler(req):
            payload = json.loads(req.content)
            calls.append(payload)
            self.assertEqual(payload['model'], 'gemma3:4b')
            self.assertLessEqual(payload['options']['num_ctx'], 8192)
            self.assertEqual(payload['keep_alive'], '15m')
            self.assertNotIn('system', [m['role'] for m in payload['messages']])
            content = '\n'.join(m['content'] for m in payload['messages'])
            if 'Return a concise audit only' in content:
                self.assertIsInstance(payload['format'], dict)
                self.assertEqual(payload['options']['num_predict'], 512)
                reply = json.dumps({'approved': True, 'issues': [], 'warnings': ['Check current opening hours.']})
            elif 'Create JSON with title' in content:
                self.assertIsInstance(payload['format'], dict)
                self.assertLess(payload['options']['num_predict'], 4096)
                reply = expected
            else:
                self.assertEqual(payload['format'], 'json')
                self.assertEqual(payload['options']['num_predict'], 384)
                reply = json.dumps({'summary': 'Use curated evidence; verify seasonal notes.', 'source_ids': ['curated-kyoto'], 'warnings': []})
            return httpx.Response(200, json={'message': {'content': reply}, 'prompt_eval_count': 50, 'eval_count': 20,
                                            'load_duration': 100000000, 'eval_duration': 500000000})
        build_workflow('http://localhost:11434', 'gemma3:4b', lambda *args: None)
        original = httpx.AsyncClient
        def client(**kwargs):
            return original(transport=httpx.MockTransport(handler), **kwargs)
        stages = []
        with patch.dict(os.environ, {'TAVILY_API_KEY':'', 'OLLAMA_MODEL':'gemma3:4b', 'OLLAMA_CONTEXT_TOKENS':'8192',
                'OLLAMA_RESEARCH_TOKENS':'384', 'OLLAMA_REVIEW_TOKENS':'512', 'OLLAMA_KEEP_ALIVE':'15m'}), patch('backend.agents.httpx.AsyncClient', side_effect=client):
            result = await plan_trip(request, 'ollama', lambda stage, status, *extra: stages.append(stage))
        self.assertEqual(len(calls), 4)
        self.assertEqual(result['provider'], 'ollama')
        self.assertEqual(stages[-1], 'validation')
        self.assertEqual(set(stages), {'destination_researcher','season_researcher','itinerary_planner','trip_reviewer','validation'})
        self.assertIn('Check current opening hours.', result['itinerary']['warnings'])
        self.assertEqual(result['itinerary']['title'], json.loads(expected)['title'], 'Reviewer must not replace the drafted itinerary')
        self.assertEqual(len(result['performance']['model_requests']), 4)
        self.assertEqual(result['performance']['model_requests'][0]['tokens_per_second'], 40)

    async def test_reviewer_rejection_is_not_returned_as_success(self):
        request = trip(interests='Vegetarian meals only')
        draft = demo_plan(request)
        draft.days[0].activities[0].note = 'Dinner is a beef tasting menu.'
        expected = draft.model_dump_json()
        def handler(req):
            content = '\n'.join(m['content'] for m in json.loads(req.content)['messages'])
            finding = {'category':'constraint_violation', 'message':'Dietary requirement conflicts with the dinner activity.',
                       'requirement_quote':'Vegetarian meals only', 'activity_quote':'beef tasting menu'}
            reply = json.dumps({'issues': [finding], 'warnings': []}) if 'Return a concise audit only' in content else expected
            return httpx.Response(200, json={'message': {'content': reply}})
        original = httpx.AsyncClient
        def client(**kwargs): return original(transport=httpx.MockTransport(handler), **kwargs)
        with patch.dict(os.environ, {'TAVILY_API_KEY':''}), patch('backend.agents.httpx.AsyncClient', side_effect=client):
            with self.assertRaisesRegex(ValueError, 'Itinerary rejected: Dietary requirement'):
                await plan_trip(request, 'ollama', lambda *args: None)

    async def test_reported_italy_advice_is_returned_as_warnings(self):
        request = trip(country='IT')
        expected = demo_plan(request).model_dump_json()
        advice = ['Rome & Florence are popular destinations; potential for crowds. Consider booking accommodations in advance.',
                  'Amalfi Coast: Seasonality impacts travel. Check weather forecasts and potential for high prices.']
        def handler(req):
            text = '\n'.join(m['content'] for m in json.loads(req.content)['messages'])
            # Reproduce the exact legacy failure, including the false approval flag.
            reply = json.dumps({'approved':False,'issues':advice,'warnings':[]}) if 'Return a concise audit only' in text else expected
            return httpx.Response(200, json={'message':{'content':reply}})
        original = httpx.AsyncClient
        def client(**kwargs): return original(transport=httpx.MockTransport(handler), **kwargs)
        with patch.dict(os.environ, {'TAVILY_API_KEY':''}), patch('backend.agents.httpx.AsyncClient', side_effect=client):
            result = await plan_trip(request, 'ollama', lambda *args: None)
        self.assertEqual(result['itinerary']['country'], 'IT')
        for message in advice:
            self.assertIn(message, result['itinerary']['warnings'])

    async def test_compact_context_preserves_constraints_and_evidence(self):
        request = trip()
        source = {'id':'official', 'url':'https://www.japan.travel/en/', 'title':'Tourism'}
        context = json.loads(compact_context(request, [source]))
        self.assertEqual(context['request'], request.model_dump(mode='json'))
        self.assertEqual(context['sources'], [source])
        self.assertTrue(all('image' not in p and 'color' not in p for p in context['places']))
        self.assertTrue(all('season' in p and 'id' in p for p in context['places']))

    async def test_generation_limits_scale_with_trip_length_and_reject_bad_settings(self):
        with patch.dict(os.environ, {'OLLAMA_CONTEXT_TOKENS':'8192', 'OLLAMA_MAX_PLAN_TOKENS':'4096'}):
            self.assertLess(generation_settings(1)['planner_tokens'], generation_settings(14)['planner_tokens'])
            self.assertLessEqual(generation_settings(14)['planner_tokens'], 4096)
        with patch.dict(os.environ, {'OLLAMA_CONTEXT_TOKENS':'-1'}):
            with self.assertRaisesRegex(ValueError, 'Configuration error'):
                generation_settings()

    async def test_output_limit_is_reported_instead_of_accepting_partial_json(self):
        def handler(req):
            return httpx.Response(200, json={'message': {'content': '{}'}, 'done_reason':'length'})
        original = httpx.AsyncClient
        def client(**kwargs): return original(transport=httpx.MockTransport(handler), **kwargs)
        with patch.dict(os.environ, {'TAVILY_API_KEY':''}), patch('backend.agents.httpx.AsyncClient', side_effect=client):
            with self.assertRaisesRegex(ValueError, 'output-token limit'):
                await plan_trip(trip(), 'ollama', lambda *args: None)

    async def test_ollama_failure_does_not_substitute_demo(self):
        with patch.dict(os.environ, {'TAVILY_API_KEY':''}), patch('backend.agents.httpx.AsyncClient.post', side_effect=httpx.ConnectError('offline')):
            with self.assertRaises(httpx.ConnectError):
                await plan_trip(trip(), 'ollama', lambda *args: None)

    async def test_wrong_country_and_fabricated_source_rejected(self):
        request = trip()
        plan = demo_plan(request)
        plan.days[0].activities[0].place_id = 'paris'
        plan.days[0].activities[0].source_ids = ['invented-source']
        errors = validate_itinerary(plan, request, {'curated-kyoto'})
        self.assertTrue(any('wrong-country' in e for e in errors))
        self.assertTrue(any('not retrieved' in e for e in errors))


if __name__ == '__main__':
    unittest.main()
