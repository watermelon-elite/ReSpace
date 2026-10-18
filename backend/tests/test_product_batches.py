from copy import deepcopy
import json
from pathlib import Path

import httpx
import pytest
from google import genai

from respace.discovery import GeminiProductModels, PlaywrightVerifier, ProductService, TransientProductError
from respace.operations import DomainError, OperationService
from respace.planning import PlanningController
from respace.products import offer_eligible
from test_discovery import Shopping
from test_operations import room


SCENARIOS = json.loads((Path(__file__).parent / 'fixtures/shopping-scenarios.json').read_text())


class CapturedProducts(PlaywrightVerifier):
    def __init__(self, models, pages):
        super().__init__(models)
        self.pages = pages
        self.calls = []

    def capture(self, candidate):
        self.calls.append(candidate['product_url'])
        return deepcopy(self.pages[candidate['product_url']])

    def verify(self, candidate):
        raise AssertionError('Search must capture listings before batch extraction')


class ProductResponses:
    def __init__(self, category, *, reject_early=True):
        dimensions = {'desk': ['120', '60', '74'], 'chair': ['50', '55', '82'], 'rug': ['240', '170', '1.2']}[category]
        self.pages, self.facts, self.hits, self.calls = {}, {}, [], []
        self.modify_results = lambda results, data: results
        self.fail_extractions = 0
        for index in range(1, 7):
            title = f'Independent {category} {index} natural'
            url = f'https://fixtures.example.com/{category}/{index}'
            measurements = [{'axis': axis, 'label': axis.title(), 'value': value, 'unit': 'cm',
                             'quote': f'{axis.title()} {value} cm'}
                            for axis, value in zip(('width', 'depth', 'height'), dimensions)]
            if reject_early and index < 5:
                measurements.pop(0 if category == 'rug' else -1)
            facts = {'exact_variant': True, 'variant_quote': title, 'options': {'finish': 'natural'},
                     'gtin': None, 'manufacturer': None, 'mpn': None, 'identity_quote': None,
                     'classification': 'item', 'measurements': measurements, 'price': '100.00', 'currency': 'USD',
                     'price_quote': 'USD 100.00', 'availability': 'in_stock', 'availability_quote': 'In stock',
                     'units_per_pack': 2 if category == 'chair' else 1,
                     'pack_quote': 'Contains 2 identical chairs' if category == 'chair' else f'Contains 1 {category}',
                     'features': {'material': 'wood', 'condition': 'new'},
                     'feature_quotes': {'material': 'Material wood', 'condition': 'Condition new'}}
            if not reject_early:
                facts['price'] = ['100.00', '150.00', '200.00', '250.00', '300.00', '100.00'][index - 1]
                facts['price_quote'] = 'USD ' + facts['price']
            text = '\n'.join([title, *(entry['quote'] for entry in measurements), facts['price_quote'],
                              facts['availability_quote'], facts['pack_quote'], 'Material wood', 'Condition new'])
            self.pages[url] = {'source_url': url, 'visible_text': text, 'structured_data': ''}
            self.facts[url] = facts
            self.hits.append({'title': title, 'product_id': str(index), 'source': 'Independent fixtures', 'link': url})

    def respond(self, request):
        body = json.loads(request.content)
        prompt = body['contents'][0]['parts'][0]['text']
        data = json.loads(prompt.split('\n', 1)[1])
        self.calls.append(data)
        if 'listings' in data:
            assert 'layout_reference' not in data
            if self.fail_extractions:
                self.fail_extractions -= 1
                return httpx.Response(503, json={'error': {'code': 503, 'message': 'Controlled transient failure'}})
            results = [{'listing_id': entry['listing_id'], 'source_url': entry['page']['source_url'],
                        'facts': self.facts[entry['page']['source_url']],
                        'evidence_channels': {field: 'dom' for field in
                            ('variant', 'measurements', 'price', 'availability', 'pack_contents', 'features', 'identity')}}
                       for entry in data['listings']]
        else:
            assert 'Optional reference' in data['layout_reference']['usage']
            assert '# ReSpace layout reasoning context' in data['layout_reference']['content']
            results = []
            for entry in data['choices']:
                best = ' 6 natural' in entry['product']['title']
                results.append({'choice_id': entry['choice_id'], 'variant_id': entry['product']['variant_id'],
                                'offer_id': entry['product']['offer_id'],
                                'scores': {'practical_score': 95 if best else 70, 'style_score': 90 if best else 70,
                                           'practical_reason': 'Published functionality matches the request.',
                                           'style_reason': 'Published finish matches the explicit style.'}})
        results = self.modify_results(results, data)
        return httpx.Response(200, json={'candidates': [{'content': {'role': 'model',
                               'parts': [{'text': json.dumps({'results': list(reversed(results))})}]}}],
                               'usageMetadata': {'promptTokenCount': 100, 'candidatesTokenCount': 50, 'totalTokenCount': 150}})


@pytest.mark.asyncio
@pytest.mark.parametrize('scenario_name', SCENARIOS)
@pytest.mark.parametrize('retry_first_batch', [False, True])
@pytest.mark.parametrize('continuation', ['finalize', 'question', 'refine'])
async def test_controller_covers_later_batches_and_finalizes_ranked_products(store, scenario_name, retry_first_batch, continuation):
    scenario = SCENARIOS[scenario_name]
    category = scenario['payload']['category']
    responses = ProductResponses(category)
    responses.fail_extractions = int(retry_first_batch)
    client = genai.Client(api_key='offline', http_options={
        'retry_options': {'attempts': 1},
        'httpx_client': httpx.Client(transport=httpx.MockTransport(responses.respond))})
    models = GeminiProductModels(client=client, model='offline')
    capture = CapturedProducts(models, responses.pages)
    shopping = Shopping([responses.hits[:3], responses.hits[3:], responses.hits[:1]])
    room(store, 'r')
    measured = {'units': 'meters', 'objects': [], 'floor_area_m2': 12}
    with store.transaction():
        store.put('captures', 'capture', {'capture_id': 'capture', 'room_id': 'r', 'state': 'complete', 'measured_context': measured})
    operations = OperationService(store)
    operations.submit('device', 'r', 'generation', {'operation_id': 'batch-flow', 'capture_id': 'capture',
        'planning_revision': 0, 'expected_active_revision': 0, 'budget': scenario['budget'], 'intent': 'add', 'styles': scenario['styles']})

    class Planner:
        calls = []

        async def act(self, context):
            self.calls.append(deepcopy(context))
            if retry_first_batch and len(self.calls) == 1:
                raise DomainError('planning_provider_failure', 'Controlled planner interruption', 502, True)
            if not context['actions']:
                return {'action': 'search_products', 'payload': scenario['payload']}
            searches = [action['result'] for action in context['actions'] if 'result' in action]
            result = searches[-1]
            refined = len(searches) > 1
            assert result['coverage']['distinct'] == 6
            assert result['coverage']['pending'] == 0
            assert result['coverage']['captured'] == result['coverage']['extracted'] == (4 if refined else 6)
            assert len(result['displayed_choices']) == 2
            assert [choice['scores']['overall'] for choice in result['displayed_choices']] == [89, 68]
            assert len(result['rejected_choices']) == 4
            assert result['usage']['gemini_extraction_requests'] == (1 if refined else 2 + int(retry_first_batch))
            assert result['usage']['gemini_scoring_requests'] == 1
            assert result['usage']['capture_attempts'] == (4 if refined else 6)
            chosen = result['displayed_choices'][0]
            if continuation == 'question' and not context['answers']:
                return {'action': 'ask_user', 'payload': {'kind': 'listing_choice', 'topic': 'practical_tradeoff',
                    'text': 'Which verified option suits your everyday use?', 'choices': [
                        {'choice_id': 'best', 'label': chosen['title'], 'variant_id': chosen['variant_id']}]}}
            if continuation == 'refine' and not refined:
                return {'action': 'search_products', 'payload': {**scenario['payload'],
                    'function': scenario['payload']['function'] + ' narrow workspace alternative'}}
            return {'action': 'finalize_selection', 'payload': {'selected': [
                {'variant_id': chosen['variant_id'], 'offer_id': chosen['offer_id'], 'quantity': scenario['payload']['quantity']}]}}

    planner = Planner()

    async def spatial(operation_id, selection, *, bounded=False):
        assert selection['purchases']['total'] == '100.00'
        operations.finish(operation_id, 'succeeded', {'result_kind': 'controlled_selection_handoff'})

    try:
        for _ in range(160):
            products = ProductService(store, shopping, capture, models)
            before = len(shopping.queries) + len(capture.calls) + len(responses.calls) + len(planner.calls)
            await PlanningController(store, operations, products, planner, spatial).run('batch-flow', bounded=True)
            after = len(shopping.queries) + len(capture.calls) + len(responses.calls) + len(planner.calls)
            assert after - before <= 1
            current = operations.get('device', 'batch-flow')
            if current['state'] == 'needs_clarification':
                question = current['pending_question']
                paused = (len(shopping.queries), len(capture.calls), len(responses.calls), len(planner.calls))
                await PlanningController(store, operations, products, planner, spatial).run('batch-flow', bounded=True)
                assert paused == (len(shopping.queries), len(capture.calls), len(responses.calls), len(planner.calls))
                operations.answer('device', 'batch-flow', {'operation_id': 'batch-flow', 'question_id': question['question_id'],
                    'reply_id': 'independent-answer', 'expected_decision_revision': current['decision_revision'],
                    'expected_question_revision': question['question_revision'], 'choice_ids': ['best'], 'action': 'answer'})
            if current['state'] in ('succeeded', 'failed', 'rejected'):
                break
        assert current['state'] == 'succeeded', current.get('failure')
        assert len(capture.calls) == (10 if continuation == 'refine' else 6)
        assert len(shopping.queries) == (6 if continuation == 'refine' else 3)
        assert len([call for call in responses.calls if 'listings' in call]) == 2 + int(retry_first_batch) + int(continuation == 'refine')
        assert len([call for call in responses.calls if 'choices' in call]) == (2 if continuation == 'refine' else 1)
        assert planner.calls[-1]['measured_context'] == measured
        assert planner.calls[-1]['approved_budget'] == scenario['budget']
        assert len(store.list('candidates')) == 6
        assert len(store.list('selections', 'r')) == 1
        finished_counts = (len(shopping.queries), len(capture.calls), len(responses.calls), len(planner.calls))
        await PlanningController(store, operations, ProductService(store, shopping, capture, models), planner, spatial).run('batch-flow', bounded=True)
        assert finished_counts == (len(shopping.queries), len(capture.calls), len(responses.calls), len(planner.calls))
        if continuation == 'question':
            assert planner.calls[-1]['answers'][0]['request']['choice_ids'] == ['best']
    finally:
        client.close()


@pytest.mark.parametrize('output_tokens', [2048, 8192])
def test_value_uses_the_full_comparison_set_across_different_batch_partitions(store, output_tokens):
    responses = ProductResponses('desk', reject_early=False)
    client = genai.Client(api_key='offline', http_options={'retry_options': {'attempts': 1},
        'httpx_client': httpx.Client(transport=httpx.MockTransport(responses.respond))})
    models = GeminiProductModels(client=client, model='offline', output_token_limit=output_tokens)
    room(store, 'r')
    try:
        products = ProductService(store, Shopping([responses.hits, [], []]), CapturedProducts(models, responses.pages), models)
        result = products.search({'category': 'desk', 'room_id': 'r', 'approved_ceiling': '500.00'}, 'comparison')
        assert [choice['scores']['overall'] for choice in result['displayed_choices']] == [94, 73, 70.5]
        comparison = store.get('comparisons', result['comparison_snapshots'][-1])
        assert comparison['sample_count'] == 6
        assert all(entry['sample_count'] == 5 for entry in comparison['comparisons'].values())
        assert result['coverage']['eligible'] == 6 and result['coverage']['complete']
    finally:
        client.close()


@pytest.mark.parametrize('failure', ['oversized', 'incomplete_capture', 'transient_exhausted', 'invalid_score'])
def test_failed_batch_work_does_not_hide_remaining_eligible_products(store, failure):
    responses = ProductResponses('desk', reject_early=False)
    if failure == 'oversized':
        responses.pages[responses.hits[0]['link']]['product_dom'] = 'x' * 600000
    elif failure == 'incomplete_capture':
        responses.pages[responses.hits[0]['link']].update(incomplete_capture=True, truncated_fields=['product_dom'])
    elif failure == 'transient_exhausted':
        responses.fail_extractions = 2
    else:
        def invalid(results, data):
            if 'choices' in data:
                results[0]['scores']['practical_score'] = 101
            return results
        responses.modify_results = invalid
    client = genai.Client(api_key='offline', http_options={'retry_options': {'attempts': 1},
        'httpx_client': httpx.Client(transport=httpx.MockTransport(responses.respond))})
    models = GeminiProductModels(client=client, model='offline')
    room(store, 'r')
    try:
        result = ProductService(store, Shopping([responses.hits, [], []]), CapturedProducts(models, responses.pages), models).search(
            {'category': 'desk', 'room_id': 'r', 'approved_ceiling': '500.00'}, 'failed-batch')
        assert result['state'] == 'completed'
        assert result['displayed_choices'][0]['title'] == 'Independent desk 6 natural'
        assert result['coverage']['pending'] == 0
        if failure == 'incomplete_capture':
            assert any('incomplete_capture' in candidate['reasons'] for candidate in result['candidate_outcomes'])
        else:
            assert any(batch['failures'] or any(entry.get('error') for entry in batch['results'].values())
                       for batch in store.list('product_batches', 'r'))
        if failure == 'invalid_score':
            assert store.get('comparisons', result['comparison_snapshots'][-1])['sample_count'] == 6
    finally:
        client.close()


def test_merchant_offers_share_only_verified_variants_and_score_the_cheapest_offer(store):
    responses = ProductResponses('desk')
    first, second = responses.hits[4:]
    alternate_url = first['link'] + '?merchant=alternate'
    responses.pages[alternate_url] = deepcopy(responses.pages[first['link']])
    responses.pages[alternate_url]['source_url'] = alternate_url
    responses.facts[alternate_url] = deepcopy(responses.facts[first['link']])
    responses.facts[alternate_url].update(price='80.00', price_quote='USD 80.00')
    responses.pages[alternate_url]['visible_text'] = responses.pages[alternate_url]['visible_text'].replace('USD 100.00', 'USD 80.00')
    for url, gtin in ((first['link'], '0000000000005'), (alternate_url, '0000000000005'), (second['link'], '0000000000006')):
        responses.facts[url].update(gtin=gtin, identity_quote='GTIN ' + gtin)
        responses.pages[url]['visible_text'] += '\nGTIN ' + gtin
    shopping = Shopping([[first], [], []])
    shopping.listings = lambda candidate: [
        {'product_url': url, 'merchant': merchant, 'title': title} for url, merchant, title in (
            (first['link'], 'Original', first['title']), (alternate_url, 'Alternate', first['title']),
            (second['link'], 'Original', second['title']))]
    client = genai.Client(api_key='offline', http_options={'httpx_client': httpx.Client(transport=httpx.MockTransport(responses.respond))})
    models = GeminiProductModels(client=client, model='offline')
    room(store, 'r')
    try:
        result = ProductService(store, shopping, CapturedProducts(models, responses.pages), models).search(
            {'category': 'desk', 'room_id': 'r'}, 'multiple-offers')
        assert len(result['displayed_choices']) == 2
        duplicate = next(choice for choice in result['displayed_choices'] if choice['title'] == first['title'])
        assert duplicate['offer']['price'] == '80.00' and len(duplicate['offers']) == 2
        assert store.get('comparisons', result['comparison_snapshots'][-1])['sample_count'] == 2
        assert sum(len(call.get('choices', [])) for call in responses.calls) == 2
    finally:
        client.close()


@pytest.mark.parametrize('failure', ['missing', 'duplicate', 'source', 'schema', 'unknown', 'cross_listing', 'channel', 'conflict',
                                   'pack', 'stock', 'price', 'variant', 'package', 'rug_thickness', 'unsupported_quote', 'boolean_pack'])
def test_batch_extraction_preserves_valid_listing_when_another_result_is_invalid(failure):
    category = 'rug' if failure == 'rug_thickness' else 'desk'
    responses = ProductResponses(category)
    entries = [{'listing_id': str(index), 'candidate': {'category': category, 'title': responses.hits[index - 1]['title'],
                'product_url': responses.hits[index - 1]['link'], 'merchant': 'Independent fixtures'},
                'page': responses.pages[responses.hits[index - 1]['link']]} for index in (5, 6)]

    def modify(results, data):
        if failure == 'missing':
            results.pop(0)
        elif failure == 'duplicate':
            results.append(deepcopy(results[0]))
        elif failure == 'source':
            results[0]['source_url'] = results[1]['source_url']
        elif failure == 'schema':
            results[0]['facts']['units_per_pack'] = -1
        elif failure == 'unknown':
            results[0]['listing_id'] = 'not-submitted'
        elif failure == 'cross_listing':
            results[0]['facts']['variant_quote'] = results[1]['facts']['variant_quote']
        elif failure == 'channel':
            results[0]['evidence_channels']['measurements'] = 'json_ld'
        elif failure == 'pack':
            results[0]['facts'].update(units_per_pack=None, pack_quote=None)
        elif failure == 'stock':
            results[0]['facts']['availability'] = 'unverified'
        elif failure == 'price':
            results[0]['facts'].update(price=None, price_quote=None)
        elif failure == 'variant':
            results[0]['facts']['options'] = {'finish': 'black'}
        elif failure == 'package':
            results[0]['facts']['classification'] = 'package'
        elif failure == 'rug_thickness':
            results[0]['facts']['measurements'].pop()
        elif failure == 'unsupported_quote':
            results[0]['facts']['measurements'][0].update(value='999', quote='Width 999 cm')
        elif failure == 'boolean_pack':
            results[0]['facts']['units_per_pack'] = True
        else:
            results[0]['facts']['conflicts'] = {'availability': ['In stock', 'Out of stock']}
        return results

    responses.modify_results = modify
    client = genai.Client(api_key='offline', http_options={'httpx_client': httpx.Client(transport=httpx.MockTransport(responses.respond))})
    try:
        batch = PlaywrightVerifier(GeminiProductModels(client=client, model='offline')).extract_batch(entries, {'category': 'desk'})
        good = batch['results']['6']['verified']
        assert good['dimension_evidence']['outcome'] == 'verified'
        assert good['offers'][0]['pack_contents']['verified']
        bad = batch['results']['5']
        if failure in ('cross_listing', 'channel', 'variant', 'package', 'unsupported_quote'):
            assert bad['verified']['dimension_evidence']['outcome'] != 'verified'
        elif failure in ('pack', 'price'):
            assert not offer_eligible(bad['verified']['offers'][0])
        elif failure == 'rug_thickness':
            assert bad['verified']['dimension_evidence']['assumed_axes'] == {'height': .02}
            assert offer_eligible(bad['verified']['offers'][0])
        elif failure == 'stock':
            assert offer_eligible(bad['verified']['offers'][0])
        elif failure == 'conflict':
            assert bad['verified']['offers'][0]['availability'] == 'unverified'
            assert bad['verified']['offers'][0]['evidence']['conflicts']['availability']
            assert offer_eligible(bad['verified']['offers'][0])
        else:
            assert bad['error']
    finally:
        client.close()


@pytest.mark.parametrize('channel_case', ['json_ld', 'mixed', 'malformed', 'different_variant'])
def test_json_ld_priority_and_unresolved_field_dom_fallback_contract(channel_case):
    responses = ProductResponses('desk')
    hit = responses.hits[5]
    page = responses.pages[hit['link']]
    published = page['visible_text']
    if channel_case == 'mixed':
        published = published.replace('Height 74 cm', '')
    page['structured_data'] = json.dumps({'@context': 'https://schema.org', '@type': 'Product',
        'name': hit['title'], 'description': published})
    if channel_case == 'malformed':
        page['structured_data'] = '{"@type":"Product", malformed'
    elif channel_case == 'different_variant':
        page['structured_data'] = page['structured_data'].replace(hit['title'], 'Other desk black')

    def channels(results, data):
        for result in results:
            if channel_case in ('json_ld', 'mixed'):
                result['evidence_channels'] = {key: 'json_ld' for key in result['evidence_channels']}
                if channel_case == 'mixed':
                    result['facts']['measurements'][2]['evidence_channel'] = 'dom'
        return results

    responses.modify_results = channels
    raw = []

    def respond(request):
        prompt = json.loads(request.content)['contents'][0]['parts'][0]['text']
        assert 'JSON-LD FIRST' in prompt and 'DOM ONLY' in prompt
        raw.append(prompt)
        return responses.respond(request)

    client = genai.Client(api_key='offline', http_options={'httpx_client': httpx.Client(transport=httpx.MockTransport(respond))})
    try:
        result = PlaywrightVerifier(GeminiProductModels(client=client, model='offline')).extract_batch([
            {'listing_id': 'one', 'candidate': {'title': hit['title'], 'category': 'desk', 'product_url': hit['link']}, 'page': page}], {})
        verified = result['results']['one']['verified']
        assert verified['dimension_evidence']['dimensions'] == [1.2, .6, .74]
        assert verified['offers'][0]['availability'] == 'in_stock'
        sent = json.loads(raw[0].split('\n', 1)[1])['listings'][0]['page']
        assert sent['structured_data'] == page['structured_data'] and sent['visible_text'] == page['visible_text']
    finally:
        client.close()


@pytest.mark.parametrize('stage', ['capture', 'extraction', 'scoring'])
@pytest.mark.parametrize('action', ['cancel', 'delete'])
def test_late_batch_results_cannot_publish_after_cancellation_or_room_deletion(store, stage, action):
    responses = ProductResponses('desk')
    client = genai.Client(api_key='offline', http_options={'httpx_client': httpx.Client(transport=httpx.MockTransport(responses.respond))})
    models = GeminiProductModels(client=client, model='offline')
    capture = CapturedProducts(models, responses.pages)
    room(store, 'r')
    operations = OperationService(store)
    operations.submit('device', 'r', 'generation', {'operation_id': 'late', 'budget': '500.00'})
    stopped = False

    def stop():
        nonlocal stopped
        if not stopped:
            stopped = True
            if action == 'cancel':
                operations.cancel('device', 'late', 'stop')
            else:
                from unittest.mock import Mock
                operations.delete_room('device', 'r', 'remove', Mock())

    if stage == 'capture':
        original = capture.capture

        def late(candidate):
            page = original(candidate)
            stop()
            return page
        capture.capture = late
    else:
        def late(results, data):
            if ('listings' in data) == (stage == 'extraction'):
                stop()
            return results
        responses.modify_results = late

    def guard(record):
        context = record.get('intended_context', {})
        operations.guard(context.get('operation_id', record.get('operation_id')))

    products = ProductService(store, Shopping([responses.hits, [], []]), capture, models, guard=guard)
    try:
        with pytest.raises((DomainError, ValueError)):
            products.search({'category': 'desk', 'room_id': 'r', 'intended_context': {'room_id': 'r', 'operation_id': 'late'}}, 'late-search')
        assert stopped
        if action == 'delete':
            assert not store.list('product_captures', 'r') and not store.list('product_batches', 'r')
            assert store.get('rooms', 'r') is None
        else:
            assert operations.get('device', 'late')['state'] == 'cancelled'
            assert not store.list('selections', 'r')
            assert not [batch for batch in store.list('product_batches', 'r') if batch['kind'] == stage]
    finally:
        client.close()


@pytest.mark.parametrize('age_days', [2, 8])
@pytest.mark.parametrize('transient', [False, True])
def test_expired_capture_is_refreshed_before_resumed_model_batch(store, age_days, transient):
    from datetime import datetime, timedelta, timezone

    responses = ProductResponses('desk')
    client = genai.Client(api_key='offline', http_options={'httpx_client': httpx.Client(transport=httpx.MockTransport(responses.respond))})
    models = GeminiProductModels(client=client, model='offline')
    capture = CapturedProducts(models, responses.pages)
    shopping = Shopping([responses.hits, [], []])
    room(store, 'r')
    request = {'category': 'desk', 'room_id': 'r'}
    try:
        for _ in range(40):
            result = ProductService(store, shopping, capture, models).search(request, 'resume', bounded=True)
            if result['phase'] == 'extraction':
                break
        assert len(capture.calls) == 6 and not responses.calls
        record = store.get('product_captures', result['continuation']['capture_ids'][0])
        record['captured_at'] = (datetime.now(timezone.utc) - timedelta(days=age_days)).isoformat()
        record['page']['captured_at'] = record['captured_at']
        with store.transaction():
            store.put('product_captures', record['capture_id'], record)
        if transient:
            original = capture.capture
            failed = False

            def retry(candidate):
                nonlocal failed
                page = original(candidate)
                if not failed:
                    failed = True
                    raise TransientProductError('page_inaccessible', 'Controlled refresh interruption')
                return page
            capture.capture = retry
        for _ in range(40):
            before = len(capture.calls) + len(responses.calls)
            result = ProductService(store, shopping, capture, models).search(request, 'resume', bounded=True)
            assert len(capture.calls) + len(responses.calls) - before <= 1
            if result['state'] != 'running':
                break
        assert result['state'] == 'completed'
        assert len(capture.calls) == 7 + int(transient)
        assert len([call for call in responses.calls if 'listings' in call]) == 2
        refreshed = store.get('product_captures', record['capture_id'])
        assert refreshed['captured_at'] > record['captured_at']
    finally:
        client.close()
