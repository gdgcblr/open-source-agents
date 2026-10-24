import json

import pytest

from migine.models import FinancialRecord
from migine.ollama import search
from migine.storage import Store


@pytest.mark.parametrize(
    "fields",
    [
        {"amount": "-1.00"},
        {"amount": "1.001"},
        {"currency": "rupees"},
        {"period": "2026-99"},
        {"account": "1234567890123456"},
        {"occurred_on": "2026-02-30"},
        {"approved": True},
        {"status": "statement"},
    ],
)
def test_invalid_financial_fields(fields):
    values = {
        "kind": "charge",
        "provider": "sample",
        "amount": "5.00",
        "currency": "USD",
        "occurred_on": "2026-10-01",
        "status": "credited",
        "evidence": "Sample evidence",
    }
    with pytest.raises(ValueError):
        FinancialRecord.model_validate(values | fields)


def test_keyword_and_local_vectors(tmp_path):
    store = Store(tmp_path)
    store.add_source(
        {
            "id": "one",
            "title": "Statement balance",
            "body": "Please pay the balance.",
            "received": "2026-10-01",
            "url": "demo:one",
        }
    )
    store.add_source(
        {
            "id": "two",
            "title": "Lunch",
            "body": "Lunch on Friday.",
            "received": "2026-10-01",
            "url": "demo:two",
        }
    )
    assert search(store, "balance")[0]["id"] == "one"

    class Embedder:
        class settings:
            embedding_model = "test"

        def embed(self, _query, query=False):
            return [1.0, 0.0]

    with store.connect() as db:
        db.execute("INSERT INTO vectors VALUES(?,?,?)", ("one", "test", json.dumps([1.0, 0.0])))
        db.execute("INSERT INTO vectors VALUES(?,?,?)", ("two", "test", json.dumps([0.0, 1.0])))
    assert search(store, "payment reminder", Embedder())[0]["id"] == "one"
