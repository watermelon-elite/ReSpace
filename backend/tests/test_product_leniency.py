from copy import deepcopy
import json

import httpx
import pytest
from google import genai

from respace.discovery import GeminiProductModels, PlaywrightVerifier, ProductService, checked_facts
from respace.operations import OperationService
from respace.planning import PlanningController
from respace.products import choice_eligible, offer_eligible, rank_choices
from test_operations import room
from test_products import NOW, choice


def published_listing(category):
    title = f'Sample {category} Natural'
    url = f'https://example.com/{category}'
    size = {'desk': ['120', '60', '74'], 'chair': ['50', '55', '82'], 'rug': ['2', '5']}[category]
    measurements = [{'axis': axis, 'label': axis.title(), 'value': value,
                     'unit': 'ft' if category == 'rug' else 'cm',
                     'quote': "2' x 5'" if category == 'rug' else f'{axis.title()} {value} cm'}
                    for axis, value in zip(('width', 'depth', 'height'), size)]
    facts = {'exact_variant': True, 'variant_quote': title, 'options': {'finish': 'Natural'},
             'gtin': None, 'manufacturer': None, 'mpn': None, 'identity_quote': None,
             'classification': 'item', 'measurements': measurements, 'price': '100.00', 'currency': 'USD',
             'price_quote': 'USD 100.00', 'availability': 'in_stock', 'availability_quote': 'In stock',
             'units_per_pack': None, 'pack_quote': None, 'pack_type': 'single',
             'features': {'material': 'wood'}, 'feature_quotes': {'material': 'Solid wood'},
             'assumptions': ['Ordinary individual furnishing listing.']}
    text = '\n'.join([title, *(item['quote'] for item in measurements), 'USD 100.00', 'In stock', 'Solid wood'])
    if category == 'chair':
        facts.update(pack_type='identical_pack', units_per_pack=2, pack_quote='Set of 2 chairs',
                     conflicts={'measurements': ['Same chair model in another color'],
                                'availability': ['OutOfStock metadata', '5 left in current purchase controls']})
        text += '\nSet of\n2 chairs'
    return {'title': title, 'category': category, 'product_url': url, 'merchant': 'Example'}, facts, {
        'source_url': url, 'visible_text': text, 'structured_data': ''}


def checked_choice(category):
    candidate, facts, page = published_listing(category)
    checked = checked_facts(candidate, facts, page)
    evidence, offer = checked['dimension_evidence'], checked['offers'][0]
    return {**checked, 'category': category, 'title': candidate['title'], 'variant_id': checked['variant']['variant_id'],
            'offer_id': offer['offer_id'], 'offer': offer, 'dimension_evidence': evidence,
            'dimensions': evidence['dimensions'], 'features': checked['variant']['features']}


@pytest.mark.parametrize('category', ['desk', 'chair', 'rug'])
def test_useful_listing_is_eligible_with_disclosed_incidental_uncertainty(category):
    selected = checked_choice(category)
    assert choice_eligible(selected, {'category': category, 'approved_ceiling': '250.00'})
    if category == 'rug':
        assert selected['dimensions'] == [.6096, 1.524, .02]
        assert selected['dimension_evidence']['assumed_axes'] == {'height': .02}
        assert len(selected['dimension_evidence']['original_measurements']) == 2
        assert not choice_eligible(selected, {'max_dimensions': [None, None, .1]})
    if category == 'desk':
        assert selected['offer']['pack_contents']['basis'] == 'single_item_assumption'
    if category == 'chair':
        assert selected['offer']['availability'] == 'unverified'
        assert selected['offer']['pack_contents']['components'][0]['units'] == 2


def test_clear_products_and_offers_are_preferred_but_uncertain_fallbacks_remain_ranked():
    clear = choice('clear', '150.00', practical=65)
    uncertain = choice('uncertain', '100.00', practical=99)
    uncertain['offer']['availability'] = 'unverified'
    ranked, _ = rank_choices([uncertain, clear], {}, now=NOW)
    assert [item['variant_id'] for item in ranked] == ['clear', 'uncertain']
    assert any('Availability' in warning for warning in ranked[1]['verification_warnings'])
    assert rank_choices([uncertain], {}, now=NOW)[0][0]['variant_id'] == 'uncertain'
    same_variant = deepcopy(clear)
    same_variant['offer'].update(offer_id='uncertain-cheaper', availability='unverified', price='1.00')
    ranked, _ = rank_choices([same_variant, clear], {}, now=NOW)
    assert ranked[0]['offer']['offer_id'] == clear['offer']['offer_id']


def test_single_item_identity_quote_is_not_mislabeled_as_an_explicit_supplied_count():
    candidate, facts, page = published_listing('desk')
    facts.update(units_per_pack=1, pack_quote=candidate['title'], assumptions=[])
    offer = checked_facts(candidate, facts, page)['offers'][0]
    assert offer_eligible(offer)
    assert offer['pack_contents']['basis'] == 'single_item_assumption'
    assert offer['warnings']


@pytest.mark.parametrize('failure', ['critical_dimension', 'missing_rug_width', 'price', 'stock', 'mixed_bundle', 'known_pack'])
def test_leniency_does_not_invent_essential_size_price_or_bundle_contents(failure):
    category = 'rug' if failure == 'missing_rug_width' else 'desk'
    candidate, facts, page = published_listing(category)
    if failure == 'critical_dimension':
        facts['measurements'].pop()
    elif failure == 'missing_rug_width':
        facts['measurements'].pop(0)
    elif failure == 'price':
        facts.update(price=None, price_quote=None)
    elif failure == 'stock':
        facts.update(availability='out_of_stock', availability_quote='Out of stock')
        page['visible_text'] += '\nOut of stock'
    else:
        facts['pack_type'] = 'mixed_bundle' if failure == 'mixed_bundle' else 'identical_pack'
    result = checked_facts(candidate, facts, page)
    if failure in ('critical_dimension', 'missing_rug_width'):
        assert result['dimension_evidence']['outcome'] == 'missing_dimensions'
    assert not offer_eligible(result['offers'][0])


@pytest.mark.asyncio
async def test_lenient_products_reach_ranking_and_controller_purchase_selection(store):
    categories = ['desk', 'chair', 'rug']
    listings = {category: published_listing(category) for category in categories}
    calls = []

    def respond(request):
        body = json.loads(request.content)
        prompt = body['contents'][0]['parts'][0]['text']
        data = json.loads(prompt.split('\n', 1)[1])
        calls.append(data)
        if 'listings' in data:
            assert 'missing thickness is not a rejection' in prompt
            assert 'ordinary individual furnishing listing' in prompt
            results = [{'listing_id': entry['listing_id'], 'source_url': entry['page']['source_url'],
                'facts': listings[entry['candidate']['category']][1],
                'evidence_channels': {key: 'dom' for key in ('variant', 'measurements', 'price', 'availability', 'pack_contents', 'features')}}
                for entry in data['listings']]
        else:
            results = [{'choice_id': entry['choice_id'], 'variant_id': entry['product']['variant_id'],
                'offer_id': entry['product']['offer_id'], 'scores': {'practical_score': 85, 'style_score': 80,
                'practical_reason': 'Fits the requested function.', 'style_reason': 'Matches the requested finish.'}}
                for entry in data['choices']]
        return httpx.Response(200, json={'candidates': [{'content': {'parts': [{'text': json.dumps({'results': results})}]}}]})

    class Shopping:
        def search(self, query):
            category = next(category for category in categories if category in query)
            candidate = listings[category][0]
            return {'results': [{'title': candidate['title'], 'product_id': category,
                     'source': 'Example', 'link': candidate['product_url']}], 'fresh_requested': True}

        def listings(self, candidate):
            return [listings[candidate['category']][0]]

    class Captured(PlaywrightVerifier):
        def capture(self, candidate):
            return deepcopy(listings[candidate['category']][2])

    class Planner:
        async def act(self, context):
            if len(context['actions']) < 3:
                category = categories[len(context['actions'])]
                return {'action': 'search_products', 'payload': {'category': category, 'function': category,
                    'quantity': 2 if category == 'chair' else 1}}
            selected = []
            for action in context['actions']:
                result = action['result']
                assert result['state'] == 'completed' and len(result['displayed_choices']) == 1
                product = result['displayed_choices'][0]
                assert product['verification_warnings'] and product['uncertainty']
                selected.append({'variant_id': product['variant_id'], 'offer_id': product['offer_id'],
                                 'quantity': 2 if product['category'] == 'chair' else 1})
            return {'action': 'finalize_selection', 'payload': {'selected': selected}}

    room(store, 'r')
    with store.transaction():
        store.put('captures', 'capture', {'capture_id': 'capture', 'room_id': 'r', 'state': 'complete',
                  'measured_context': {'units': 'meters', 'floor_area_m2': 12, 'objects': []}})
    operations = OperationService(store)
    operations.submit('device', 'r', 'generation', {'operation_id': 'lenient-flow', 'capture_id': 'capture',
        'planning_revision': 0, 'expected_active_revision': 0, 'budget': '500.00', 'intent': 'add'})

    async def selected(operation_id, selection, **kwargs):
        assert selection['purchases']['total'] == '300.00'
        assert sum(product['quantity'] for product in selection['selected']) == 4
        assert all(product['verification_warnings'] for product in selection['selected'])
        operations.finish(operation_id, 'succeeded', {'result_kind': 'checked_selection'})

    client = genai.Client(api_key='offline', http_options={'httpx_client': httpx.Client(transport=httpx.MockTransport(respond))})
    try:
        models = GeminiProductModels(client=client, model='offline')
        controller = PlanningController(store, operations, ProductService(store, Shopping(), Captured(models), models), Planner(), selected)
        for step in range(250):
            await controller.run('lenient-flow', bounded=True)
            operation = operations.get('device', 'lenient-flow')
            if operation['state'] in ('succeeded', 'failed', 'rejected', 'needs_clarification'):
                break
        assert operation['state'] == 'succeeded', operation.get('failure')
        assert sum('listings' in call for call in calls) == 3
        assert sum('choices' in call for call in calls) == 3
    finally:
        client.close()
