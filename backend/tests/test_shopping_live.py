"""Synthetic planning inputs; real shopping providers run only with explicit opt-in."""
import json
import os
from html import escape
from pathlib import Path
import socket

import httpx
import pytest

from respace import tracing
from respace.discovery import GeminiProductModels, PlaywrightVerifier, ProductService, SerpAPIShopping
from respace.planning import PlanningController
from respace.products import choice_eligible
from respace.store import SQLiteStore


SCENARIOS = json.loads((Path(__file__).parent / "fixtures/shopping-scenarios.json").read_text())


@pytest.fixture(params=SCENARIOS, ids=SCENARIOS)
def shopping_input(request, tmp_path):
    scenario = SCENARIOS[request.param]
    room_id = "4f47f263-534c-47b5-9d40-dad7fd633b9b"
    operation = {
        "operation_id": "fd1c1f01-1e4a-4ae3-89a0-e4a10555b280",
        "room_id": room_id,
        "request": {"budget": scenario["budget"], "styles": scenario["styles"], "intent": "add"},
        "base_context": {
            "room_id": room_id,
            "capture_id": "178c2dac-46eb-42e7-aea8-df0823352c59",
            "snapshot_id": None,
            "planning_revision": 0,
            "active_design_id": None,
            "active_revision": 0,
        },
        "answer_history": [],
    }
    controller = PlanningController(None, None, None, None, None)
    search_request = controller._search_request(operation, scenario["payload"])
    (tmp_path / "request.json").write_text(json.dumps(search_request, indent=2))
    return search_request


def test_shopping_input_preview(shopping_input, tmp_path):
    queries = ProductService.queries(shopping_input)
    assert len(set(queries)) == 3
    assert shopping_input["schema_version"] == 1
    assert shopping_input["intended_context"]["room_id"] == shopping_input["room_id"]
    print(json.dumps({"request": shopping_input, "queries": queries}, indent=2))
    print(f"Synthetic request: {tmp_path / 'request.json'}")


@pytest.mark.skipif(os.environ.get("RESPACE_BROWSER_REPLAY") != "1", reason="Set RESPACE_BROWSER_REPLAY=1 to run local Chromium without provider usage")
def test_browser_shopping_replay(shopping_input, tmp_path, monkeypatch):
    from google import genai
    import respace.discovery as discovery

    category = shopping_input["category"]
    sizes = {"desk": (["120", "60", "74"], [1.2, .6, .74]),
             "chair": (["50", "55", "82"], [.5, .55, .82]),
             "rug": (["240", "170", "1.2"], [2.4, 1.7, .012])}
    values, dimensions = sizes[category]
    cases = [("available", "item", "in_stock", "verified"), ("alternative", "item", "in_stock", "verified")]
    cases += ([("package_only", "package", "in_stock", "package_dimensions")] if category == "desk" else
              [("out_of_stock", "item", "out_of_stock", "verified")] if category == "chair" else
              [("missing_footprint", "item", "in_stock", "missing_dimensions")])
    listings = {}
    for name, classification, availability, outcome in cases:
        listing_id = category + "_" + name
        url = "https://fixtures.example.com/" + listing_id
        title = "Synthetic " + category.replace("_", " ") + " / natural / " + name
        measurements = [{"axis": axis, "label": axis.title(), "value": value, "unit": "cm",
                         "quote": f"{axis.title()} {value} cm"}
                        for axis, value in zip(("width", "depth", "height"), values)
                        if not (name == "missing_footprint" and axis == "width")]
        facts = {"exact_variant": True, "variant_quote": title, "options": {"finish": "natural"},
                 "gtin": None, "manufacturer": None, "mpn": None, "identity_quote": None,
                 "classification": classification, "measurements": measurements,
                 "price": "129.00", "currency": "USD", "price_quote": "USD 129.00",
                 "availability": availability, "availability_quote": availability.replace("_", " "),
                 "units_per_pack": 2 if category == "chair" else 1,
                 "pack_quote": "Contains 2 identical chairs" if category == "chair" else "Contains 1 unit",
                 "features": {"material": "wood", "condition": "new"},
                 "feature_quotes": {"material": "Material wood", "condition": "Condition new"}}
        if listing_id == "desk_available":
            facts["pack_quote"] = "Contains\n1\nunit"
        text = "\n".join([title, *(m["quote"] for m in measurements), facts["price_quote"],
                           facts["availability_quote"], facts["pack_quote"], *facts["feature_quotes"].values()])
        listings[url] = {"listing_id": listing_id, "candidate": {"title": title, "merchant": "Synthetic Furnishings", "product_url": url},
                         "page": {"visible_text": text}, "facts": facts,
                         "expected": {"dimension_outcome": outcome, "dimensions": dimensions if outcome == "verified" else None}}
    (tmp_path / "synthetic-listings.json").write_text(json.dumps(listings, indent=2))
    tokens = {entry["listing_id"]: entry for entry in listings.values()}
    provider_calls, browser_urls, model_calls, model_batch_sizes = [], [], [], []

    def blocked_connection(*args, **kwargs):
        raise AssertionError("Live network access is prohibited in the offline shopping replay")

    def fixture_addresses(host, port, **kwargs):
        assert host == "fixtures.example.com"
        return [(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", ("93.184.216.34", port))]

    def fixture_page(request):
        entry = listings[request.url]
        browser_urls.append(request.url)
        content = "<pre>" + escape(entry["page"]["visible_text"]) + "</pre>"
        if entry["listing_id"] == "desk_available":
            content = content.replace("Contains\n1\nunit", "</pre><span>Contains</span><span>1</span><span>unit</span><pre>")
            content = '<button role="tab">Measurements</button><section role="tabpanel" hidden>' + content + '</section>'
        tag = 'div' if entry['listing_id'].endswith('alternative') else 'main'
        uncertain = '<main>Uncertain Product information retained</main>' if entry['listing_id'].endswith('available') else ''
        metadata = json.dumps({'@type': 'Product', 'name': entry['candidate']['title']})
        html = ('<!doctype html><html><body><nav>Unrelated navigation</nav>'
                '<header role="banner">Unrelated banner</header><' + tag + '><header role="banner"><h1>'
                + escape(entry['candidate']['title']) + '</h1></header>' + content + '</' + tag + '>' + uncertain
                + '<script type="application/ld+json">' + metadata + '</script>'
                '<script type="application/json">{"publishedProductMetadata":"retained"}</script>'
                '<footer role="contentinfo">Unrelated footer</footer></body></html>')
        if entry['listing_id'].endswith('available'):
            html = html.replace('</body>', '<div data-published-metadata="' + 'x' * 120000 + '"></div>'
                + '<svg><title>Published dimension guide</title><text>Width 120 cm</text><path d="'
                + 'M 0 0 ' * 20000 + '"></path></svg><div>' + ' \n' * 10000 + '</div></body>')
        return {"status": 200, "headers": {"content-type": "text/html; charset=utf-8"}, "body": html.encode()}

    def shopping_response(request):
        parameters = dict(request.url.params)
        provider_calls.append({key: value for key, value in parameters.items() if key != "api_key"})
        if parameters["engine"] == "google_shopping":
            assert parameters["no_cache"] == "true" and parameters["gl"] == "us"
            data = {"shopping_results": [
                {"title": entry["candidate"]["title"], "product_id": entry["listing_id"],
                 "link": "https://www.google.com/shopping/product/" + entry["listing_id"],
                 "source": entry["candidate"]["merchant"], "immersive_product_page_token": entry["listing_id"]}
                for entry in listings.values()]}
        else:
            assert parameters["engine"] == "google_immersive_product"
            candidate = tokens[parameters["page_token"]]["candidate"]
            data = {"product_results": {"stores": [{"link": candidate["product_url"], "name": candidate["merchant"], "title": candidate["title"]}]}}
        return httpx.Response(200, json={"search_metadata": {"id": "offline-replay", "status": "Success"}, **data})

    def model_response(request):
        body = json.loads(request.content)
        prompt = body["contents"][0]["parts"][0]["text"]
        data = json.loads(prompt.split("\n", 1)[1])
        if 'listings' in data:
            results = []
            model_batch_sizes.append(len(data['listings']))
            for listing in data['listings']:
                entry = listings[listing['candidate']['product_url']]
                page = listing['page']
                evidence_text = '\n'.join(page.get(key, '') for key in ('visible_text', 'structured_data', 'specification_text', 'product_dom'))
                quotes = [entry['facts'][key] for key in ('variant_quote', 'price_quote', 'availability_quote', 'pack_quote')]
                quotes += [measurement['quote'] for measurement in entry['facts']['measurements']]
                assert all(quote in evidence_text for quote in quotes)
                assert 'Unrelated navigation' not in evidence_text and 'Unrelated footer' not in evidence_text
                assert '<h1>' in page['product_dom'] and entry['candidate']['title'] in page['structured_data']
                assert 'publishedProductMetadata' in page['product_dom']
                if entry['listing_id'].endswith('available'):
                    assert 'Uncertain Product information retained' in page['product_dom']
                    assert len(page['product_dom']) > 100000 and not page['incomplete_capture']
                    assert 'Published dimension guide' in page['product_dom'] and 'Width 120 cm' in page['product_dom']
                    assert 'M 0 0 ' not in page['product_dom'] and ' \n' * 100 not in page['product_dom']
                results.append({'listing_id': listing['listing_id'], 'source_url': page['source_url'], 'facts': entry['facts'],
                                'evidence_channels': {key: 'dom' for key in ('variant', 'measurements', 'price', 'availability', 'pack_contents', 'features')}})
                model_calls.append('extraction')
        else:
            results = []
            model_batch_sizes.append(len(data['choices']))
            for entry in data['choices']:
                alternative = entry['product']['title'].endswith(' / alternative')
                results.append({'choice_id': entry['choice_id'], 'variant_id': entry['product']['variant_id'],
                    'offer_id': entry['product']['offer_id'], 'scores': {
                    'practical_score': 70 if alternative else 80, 'style_score': 60 if alternative else 80,
                    'practical_reason': 'Recorded synthetic search request.', 'style_reason': 'Recorded synthetic style.'}})
                model_calls.append('ranking')
        return httpx.Response(200, json={'candidates': [{'content': {'role': 'model', 'parts': [{'text': json.dumps({'results': results})}]}}]})

    for name in ("GEMINI_API_KEY", "GOOGLE_API_KEY", "SERPAPI_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(socket.socket, "connect", blocked_connection)
    monkeypatch.setattr(socket, "create_connection", blocked_connection)
    monkeypatch.setattr(socket, "getaddrinfo", fixture_addresses)
    monkeypatch.setattr(discovery, "_browser_response", fixture_page)
    client = genai.Client(api_key="offline-replay", http_options={"httpx_client": httpx.Client(transport=httpx.MockTransport(model_response))})
    models = GeminiProductModels(client=client, model="offline-replay")
    shopping = SerpAPIShopping("offline-replay", httpx.Client(transport=httpx.MockTransport(shopping_response)))
    store = SQLiteStore(tmp_path / "records.sqlite3")
    with store.transaction():
        store.put("rooms", shopping_input["room_id"], {"room_id": shopping_input["room_id"]})
    previous_handlers = tracing.logger.handlers[:]
    tracing.logger.handlers = []
    tracing.configure(tmp_path / "trace.jsonl")
    try:
        products = ProductService(store, shopping, PlaywrightVerifier(models), models)
        result = products.search(shopping_input, shopping_input["intended_context"]["operation_id"])
        assert len(result["queries"]) == 3 and not result["source_failures"]
        assert set(browser_urls) == set(listings)
        assert model_calls.count("extraction") == len(listings)
        assert model_batch_sizes == [3, 2]
        assert result['usage']['serpapi_search_requests'] == 3
        assert result['usage']['merchant_resolution_requests'] == 3
        assert result['usage']['gemini_extraction_requests'] == result['usage']['gemini_scoring_requests'] == 1
        assert result['coverage'] == {'discovered': 9, 'distinct': 3, 'captured': 3, 'extracted': 3,
                                     'eligible': 2, 'rejected': 1, 'pending': 0, 'complete': True, 'discovery_complete': True}
        assert len(result["displayed_choices"]) == 2
        assert [choice["scores"]["overall"] for choice in result["displayed_choices"]] == [77, 65]
        assert all(choice_eligible(choice, shopping_input) for choice in result["displayed_choices"])
        for evidence in store.list("dimensions"):
            expected = listings[evidence["source_url"]]["expected"]
            assert evidence["outcome"] == expected["dimension_outcome"]
            if expected["dimensions"] is not None:
                assert evidence["dimensions"] == pytest.approx(expected["dimensions"])
    finally:
        records = {kind: store.list(kind) for kind in ("searches", "candidates", "variants", "dimensions", "offers", "comparisons")}
        records["offline_usage"] = {"serpapi_requests": 0, "gemini_requests": 0,
                                    "replayed_provider_calls": provider_calls, "browser_urls": browser_urls, "replayed_model_calls": model_calls}
        (tmp_path / "report.json").write_text(json.dumps(records, indent=2))
        shopping.client.close()
        client.close()
        for handler in tracing.logger.handlers[:]:
            handler.close()
        tracing.logger.handlers = previous_handlers
    print(f"Offline browser replay evidence: {tmp_path}")


@pytest.mark.skipif(os.environ.get("RESPACE_LIVE_SHOPPING") != "1", reason="Set RESPACE_LIVE_SHOPPING=1 to call paid providers")
def test_live_shopping(shopping_input, tmp_path):
    required = ("SERPAPI_API_KEY", "GEMINI_EXTRACTION_MODEL")
    missing = [name for name in required if not os.environ.get(name)]
    if not (os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")):
        missing.append("GEMINI_API_KEY or GOOGLE_API_KEY")
    assert not missing, "Missing live-provider configuration: " + ", ".join(missing)

    models = GeminiProductModels()
    shopping = SerpAPIShopping()
    store = SQLiteStore(tmp_path / "records.sqlite3")
    with store.transaction():
        store.put("rooms", shopping_input["room_id"], {"room_id": shopping_input["room_id"]})
    products = ProductService(store, shopping, PlaywrightVerifier(models), models)
    previous_handlers = tracing.logger.handlers[:]
    tracing.logger.handlers = []
    tracing.configure(tmp_path / "trace.jsonl")
    print(f"Live shopping evidence: {tmp_path}", flush=True)
    try:
        result = products.search(shopping_input, shopping_input["intended_context"]["operation_id"])
        assert len(result["queries"]) == 3 and not result["source_failures"], "Fresh discovery failed; inspect report.json"
        assert result["attempted_candidates"], "No merchant candidates reached verification; inspect report.json"
        assert result["displayed_choices"], "No eligible exact variants; inspect candidate rejection reasons in report.json"
        assert all(choice_eligible(choice, shopping_input) for choice in result["displayed_choices"])
    finally:
        records = {kind: store.list(kind) for kind in ("searches", "candidates", "variants", "dimensions", "offers", "comparisons")}
        (tmp_path / "report.json").write_text(json.dumps(records, indent=2))
        shopping.client.close()
        models.client.close()
        for handler in tracing.logger.handlers[:]:
            handler.close()
        tracing.logger.handlers = previous_handlers
