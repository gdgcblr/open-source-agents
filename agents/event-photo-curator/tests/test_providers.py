import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

from google.genai.errors import APIError
import pytest
from rich.console import Console

from curator.loader import read_photo
from curator.providers import GeminiProvider, MockProvider, validate_result
from curator.ranker import cache_key, rank


@pytest.fixture
def photos(sample):
    return [read_photo(sample / name)[0] for name in ('01-sharp.png', '04-scene.png', '05-scene.png')]


def fake_response(photos):
    items = [dict(id=p.digest, moment=8, composition=7, expressions=9, reason='An engaged audience.', caption='Learning together.') for p in reversed(photos)]
    return SimpleNamespace(text=json.dumps({'assessments': items}), usage_metadata=SimpleNamespace(total_token_count=1234))


def provider_with_client(monkeypatch):
    client = Mock()
    monkeypatch.setattr('google.genai.Client', lambda **kwargs: client)
    return GeminiProvider('fake-test-key', 'gemini-2.5-flash'), client


def test_gemini_retries_429_maps_ids_and_reuses_cache(photos, tmp_path, monkeypatch):
    provider, client = provider_with_client(monkeypatch)
    client.models.generate_content.side_effect = [APIError(429, {'error': {'message': 'test'}}), fake_response(photos)]
    sleep = Mock()
    monkeypatch.setattr('curator.providers.time.sleep', sleep)
    cache = tmp_path / 'cache'
    assert rank(photos, provider, 'casual', cache, 5, Console(quiet=True)) == (1234, 0)
    assert sleep.call_count == 1
    assert client.models.generate_content.call_count == 2
    assert all(p.assessment['id'] == p.digest and p.assessment['score'] == 8 for p in photos)
    request = client.models.generate_content.call_args.kwargs
    assert request['config'].response_mime_type == 'application/json'
    assert request['config'].thinking_config.thinking_budget == 0
    assert request['config'].max_output_tokens == 1536
    assert len(request['contents']) == 7  # prompt + three labelled image parts
    assert rank(photos, provider, 'casual', cache, 5, Console(quiet=True)) == (0, 3)
    assert client.models.generate_content.call_count == 2


def test_batches_only_survivors_and_settings_invalidate_cache(photos, tmp_path):
    provider = MockProvider()
    score = Mock(wraps=provider.score)
    provider.score = score
    photos[0].reasons = ['Blurry']
    cache = tmp_path / 'cache'
    rank(photos, provider, 'casual', cache, 1, Console(quiet=True))
    assert score.call_count == 2
    assert all(photos[0] not in c.args[0] for c in score.call_args_list)
    assert cache_key(photos[1], provider, 'casual') != cache_key(photos[1], provider, 'formal')
    old = cache_key(photos[1], provider, 'casual')
    provider.model = 'different-model'
    assert old != cache_key(photos[1], provider, 'casual')


def test_corrupt_cache_is_recomputed(photos, tmp_path):
    provider = MockProvider()
    cache = tmp_path / 'cache'
    cache.mkdir()
    (cache / (cache_key(photos[0], provider, 'casual') + '.json')).write_text('{bad')
    assert rank(photos[:1], provider, 'casual', cache, 5, Console(quiet=True)) == (0, 0)
    assert photos[0].assessment['score'] >= 1


@pytest.mark.parametrize('code,expected_calls', [(401, 1), (429, 5), (503, 5)])
def test_gemini_failures_are_bounded_and_sanitized(photos, monkeypatch, code, expected_calls):
    provider, client = provider_with_client(monkeypatch)
    client.models.generate_content.side_effect = APIError(code, {'error': {'message': 'secret-provider-detail'}})
    monkeypatch.setattr('curator.providers.time.sleep', lambda delay: None)
    with pytest.raises(RuntimeError) as exc:
        provider.score(photos, 'casual')
    assert 'secret-provider-detail' not in str(exc.value)
    assert client.models.generate_content.call_count == expected_calls


@pytest.mark.parametrize('failure', ['invalid-json', 'missing-id', 'bad-score', 'duplicate-id'])
def test_gemini_invalid_results_never_rank_photos(photos, monkeypatch, failure):
    provider, client = provider_with_client(monkeypatch)
    response = fake_response(photos)
    data = json.loads(response.text)
    if failure == 'missing-id':
        data['assessments'].pop()
    elif failure == 'bad-score':
        data['assessments'][0]['moment'] = 99
    elif failure == 'duplicate-id':
        data['assessments'][0]['id'] = data['assessments'][1]['id']
    response.text = 'not json' if failure == 'invalid-json' else json.dumps(data)
    client.models.generate_content.return_value = response
    with pytest.raises(RuntimeError, match='no scores were fabricated'):
        provider.score(photos, 'casual')


@pytest.mark.parametrize('value', [True, float('nan'), float('inf'), 0, 11, '8'])
def test_score_validation(value):
    with pytest.raises(ValueError):
        validate_result({'id': 'a', 'score': value, 'reason': 'Reason', 'caption': 'Caption'}, 'a')


def test_alternate_model_does_not_get_flash_only_settings(photos, monkeypatch):
    provider, client = provider_with_client(monkeypatch)
    provider.model = 'other-vision-model'
    client.models.generate_content.return_value = fake_response(photos)
    provider.score(photos, 'casual')
    assert client.models.generate_content.call_args.kwargs['config'].thinking_config is None


def test_ai_can_rescue_a_low_sharpness_burst_frame(photos,tmp_path):
    from curator.dedupe import group_duplicates,select_diverse
    import imagehash
    first,second=photos[:2]
    first.phash=second.phash=imagehash.hex_to_hash('0000000000000000')
    second.sharpness=1
    second.flags=['Blurry']
    group_duplicates([first,second],0)
    class Editorial:
        name='test-editor';model='test'
        def score(self,batch,style):
            return [dict(id=p.digest,score=10 if p is second else 2,reason='Better moment despite softness',caption='Event moment') for p in batch],0
    rank([first,second],Editorial(),'casual',tmp_path/'cache',1,Console(quiet=True))
    assert select_diverse([first,second],1)==[second]


def test_ollama_uses_images_and_never_cloud(photos,monkeypatch):
    from curator.providers import OllamaProvider
    from io import BytesIO
    photo=photos[0]
    response={'message':{'content':json.dumps({'assessments':[dict(id=photo.digest,moment=9,composition=6,expressions=6,reason='Visible scene',caption='A moment')]})},'prompt_eval_count':100,'eval_count':50}
    requests=[]
    def open_request(request,timeout):
        requests.append(request)
        return BytesIO(json.dumps(response).encode())
    monkeypatch.setattr('urllib.request.urlopen',open_request)
    result,tokens=OllamaProvider().score([photo],'casual')
    payload=json.loads(requests[0].data)
    assert requests[0].full_url=='http://127.0.0.1:11434/api/chat'
    assert payload['messages'][1]['images'] and payload['format']['type']=='object'
    assert tokens==150 and result[0]['score']==7
    with pytest.raises(ValueError):OllamaProvider('gemma4:cloud')
