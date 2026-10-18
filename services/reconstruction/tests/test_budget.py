import pytest

from respace_reconstruction.budget import CompletionBudget
from respace_reconstruction.instances import ProviderUnavailable


def test_completion_retries_cannot_repeat_unknown_billing_outcomes(tmp_path):
    path=tmp_path/"budget.json"
    budget=CompletionBudget(path)
    assert budget.reserve("request-1")==5
    with pytest.raises(ProviderUnavailable,match="unknown billing"):
        CompletionBudget(path).reserve("request-1")
    with pytest.raises(ProviderUnavailable,match="exhausted"):
        CompletionBudget(path).reserve("request-2")
    budget.settle("request-1",{"request_fingerprint":"request-1","cost_usd":1.25})
    assert CompletionBudget(path).reserve("request-1") is None
    assert CompletionBudget(path).reserve("request-2")==3.75


def test_over_budget_receipt_leaves_reservation_intact(tmp_path):
    path=tmp_path/"budget.json";budget=CompletionBudget(path);budget.reserve("request")
    with pytest.raises(ProviderUnavailable,match="over-budget"):
        budget.settle("request",{"request_fingerprint":"request","cost_usd":5.01})
    with pytest.raises(ProviderUnavailable,match="unknown billing"):
        CompletionBudget(path).reserve("request")
