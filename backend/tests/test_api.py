import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from app import db as dbmod
from app.db import get_db
from app.main import app
from app.providers import FakeEmail, FakeProvider, set_email_provider, set_payment_provider
from app.seed import BROKER_EMAIL, BROKER_PASSWORD, CUSTOMER_EMAIL, CUSTOMER_PASSWORD, seed_users


@pytest.fixture()
def client():
    engine = dbmod.make_engine(os.environ.get("TEST_DATABASE_URL", "sqlite://"))
    dbmod.Base.metadata.drop_all(engine)
    dbmod.Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with Session() as s:
        seed_users(s)
    set_payment_provider(FakeProvider())
    set_email_provider(FakeEmail())

    def override():
        s = Session()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = override
    yield TestClient(app)
    app.dependency_overrides.clear()


def login(client, email, pw):
    r = client.post("/api/auth/login", json={"email": email, "password": pw})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


def test_full_http_flow_matches_headline_scenario(client):
    broker = login(client, BROKER_EMAIL, BROKER_PASSWORD)
    cust = login(client, CUSTOMER_EMAIL, CUSTOMER_PASSWORD)
    customers = client.get("/api/customers", headers=broker).json()
    cid = customers[0]["id"]

    # issue
    r = client.post(
        "/api/policies",
        headers=broker,
        json={
            "customer_id": cid,
            "start_date": "2026-01-01",
            "end_date": "2027-01-01",
            "coverages": [{"code": "general_liability", "limit": "1M"}],
        },
    )
    assert r.status_code == 200, r.text
    pid = r.json()["id"]
    assert r.json()["balance_cents"] == 240_000

    # customer pays (simulated test card)
    pay = client.post(f"/api/policies/{pid}/payments", headers=cust).json()
    assert pay["payment"]["status"] == "pending" and pay["mode"] == "fake"
    decl = client.post(
        f"/api/payments/{pay['payment']['id']}/simulate", headers=cust, json={"outcome": "decline"}
    ).json()
    assert decl["payment"]["status"] == "failed"
    pay = client.post(f"/api/policies/{pid}/payments", headers=cust).json()
    ok = client.post(
        f"/api/payments/{pay['payment']['id']}/simulate", headers=cust, json={"outcome": "succeed"}
    ).json()
    assert ok["payment"]["status"] == "succeeded"
    assert client.get(f"/api/policies/{pid}", headers=cust).json()["balance_cents"] == 0

    # preview + add coverage
    pv = client.post(
        f"/api/policies/{pid}/preview",
        headers=broker,
        json={
            "kind": "add_coverage",
            "code": "tech_eo",
            "limit": "1M",
            "effective_date": "2026-03-01",
        },
    ).json()
    assert pv["premium_change_cents"] == 306_000 and pv["new_balance_cents"] == 306_000
    r = client.post(
        f"/api/policies/{pid}/coverages",
        headers=broker,
        json={"code": "tech_eo", "limit": "1M", "effective_date": "2026-03-01", "reason": "asked"},
    )
    assert r.json()["balance_cents"] == 306_000
    pay = client.post(f"/api/policies/{pid}/payments", headers=cust).json()
    client.post(
        f"/api/payments/{pay['payment']['id']}/simulate", headers=cust, json={"outcome": "succeed"}
    )

    # correction preview then apply
    rider = next(c for c in r.json()["coverages"] if c["code"] == "tech_eo")
    pv = client.post(
        f"/api/policies/{pid}/preview",
        headers=broker,
        json={"kind": "correction", "coverage_id": rider["id"], "new_effective_date": "2026-02-22"},
    ).json()
    assert pv["premium_change_cents"] == 7_000 and pv["lines"][1]["covered_days"] == 313
    r = client.post(
        f"/api/policies/{pid}/coverages/{rider['id']}/correct-effective-date",
        headers=broker,
        json={"new_effective_date": "2026-02-22", "reason": "Binder says Feb 22"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["balance_cents"] == 7_000

    # customer sees original charge + correction + explanation
    st = client.get(f"/api/policies/{pid}/statement", headers=cust).json()
    assert [(x["type"], x["amount_cents"]) for x in st["rows"]][-3:] == [
        ("CHARGE", 306_000),
        ("PAYMENT", -306_000),
        ("ADJUSTMENT", 7_000),
    ]
    assert "Binder says Feb 22" == st["rows"][-1]["action"]["note"]
    assert st["balance_cents"] == 7_000

    # cancel preview matches actual
    pv = client.post(
        f"/api/policies/{pid}/preview",
        headers=broker,
        json={"kind": "cancel", "cancelled_on": "2026-07-01"},
    ).json()
    # $70 is unpaid, so refundable cash is 546,000 and credit is paid-earned
    r = client.post(
        f"/api/policies/{pid}/cancel",
        headers=broker,
        json={"cancelled_on": "2026-07-01", "reason": "closing"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["policy"]["status"] == "cancelled"
    refunded = sum(x["amount_cents"] for x in r.json()["refunds"])
    assert refunded == 297_986  # paid 546,000 - earned (119,014 + 129,000); the unpaid $70 nets off
    assert pv["refund_cents"] == refunded
    assert pv["new_balance_cents"] == r.json()["policy"]["balance_cents"] - refunded


def test_customers_cannot_see_other_customers_or_use_broker_actions(client):
    broker = login(client, BROKER_EMAIL, BROKER_PASSWORD)
    cust = login(client, CUSTOMER_EMAIL, CUSTOMER_PASSWORD)
    new = client.post(
        "/api/customers",
        headers=broker,
        json={"name": "Other Co", "contact_name": "Oz", "email": "oz@other.test"},
    ).json()
    r = client.post(
        "/api/policies",
        headers=broker,
        json={
            "customer_id": new["customer"]["id"],
            "start_date": "2026-01-01",
            "end_date": "2027-01-01",
            "coverages": [{"code": "cyber", "limit": "1M"}],
        },
    )
    pid = r.json()["id"]
    assert client.get(f"/api/policies/{pid}", headers=cust).status_code == 404
    assert client.post("/api/policies", headers=cust, json={}).status_code == 403
    assert client.get("/api/customers", headers=cust).status_code == 403
    assert client.get("/api/policies", headers=cust).json() == []
    assert client.get("/api/policies").status_code == 401
    # new customer can log in with the temporary password
    login(client, "oz@other.test", new["login"]["temporary_password"])


def test_demo_scenario_loader(client):
    broker = login(client, BROKER_EMAIL, BROKER_PASSWORD)
    cid = client.get("/api/customers", headers=broker).json()[0]["id"]
    p = client.post("/api/demo/scenario", headers=broker, json={"customer_id": cid}).json()
    assert p["balance_cents"] == 0 and len(p["coverages"]) == 2


def _signed(secret: str, payload: dict):
    """Build a request exactly as Stripe sends it: JSON body plus a signed Stripe-Signature header."""
    import hashlib
    import hmac
    import json
    import time

    body = json.dumps(payload)
    ts = int(time.time())
    sig = hmac.new(secret.encode(), f"{ts}.{body}".encode(), hashlib.sha256).hexdigest()
    return body, {"Stripe-Signature": f"t={ts},v1={sig}", "Content-Type": "application/json"}


def test_signed_stripe_webhook_books_the_payment_and_is_idempotent(client, monkeypatch):
    """The real webhook route, with a real signature, for the events Stripe actually sends."""
    from app import api as api_mod
    from app.config import get_settings

    secret = "whsec_test_secret"
    monkeypatch.setattr(
        api_mod,
        "get_settings",
        lambda: get_settings().model_copy(update={"stripe_webhook_secret": secret}),
    )
    broker = login(client, BROKER_EMAIL, BROKER_PASSWORD)
    cust = login(client, CUSTOMER_EMAIL, CUSTOMER_PASSWORD)
    customers = client.get("/api/customers", headers=broker).json()
    cid = customers[0]["id"]
    pol = client.post(
        "/api/policies",
        headers=broker,
        json={
            "customer_id": cid,
            "start_date": "2026-01-01",
            "end_date": "2027-01-01",
            "coverages": [{"code": "general_liability", "limit": "1M"}],
        },
    ).json()
    pid = pol["id"]
    pay = client.post(f"/api/policies/{pid}/payments", headers=cust).json()["payment"]

    event = {
        "id": "evt_real_1",
        "object": "event",
        "type": "payment_intent.succeeded",
        "data": {
            "object": {
                "id": pay["provider_ref"],
                "object": "payment_intent",
                "amount": 240000,
                "status": "succeeded",
                "latest_charge": {"id": "ch_1"},
                "metadata": {"a": "b"},
            }
        },
    }
    body, headers = _signed(secret, event)
    r = client.post("/api/webhooks/stripe", content=body, headers=headers)
    assert r.status_code == 200, r.text
    assert r.json()["result"] == "applied"
    assert client.get(f"/api/policies/{pid}", headers=cust).json()["balance_cents"] == 0

    body, headers = _signed(secret, event)  # Stripe retries deliveries: same event id again
    r = client.post("/api/webhooks/stripe", content=body, headers=headers)
    assert r.status_code == 200 and r.json()["result"] == "duplicate"

    for etype, obj in [
        (
            "refund.created",
            {
                "id": "re_1",
                "object": "refund",
                "payment_intent": pay["provider_ref"],
                "amount": 100,
            },
        ),
        (
            "charge.refunded",
            {"id": "ch_1", "object": "charge", "payment_intent": pay["provider_ref"]},
        ),
        (
            "refund.updated",
            {"id": "re_1", "object": "refund", "payment_intent": pay["provider_ref"]},
        ),
    ]:
        body, headers = _signed(
            secret,
            {"id": f"evt_{etype}", "object": "event", "type": etype, "data": {"object": obj}},
        )
        r = client.post("/api/webhooks/stripe", content=body, headers=headers)
        assert r.status_code == 200, f"{etype}: {r.text}"


def test_webhook_with_a_bad_signature_is_rejected(client):
    r = client.post(
        "/api/webhooks/stripe", content="{}", headers={"Stripe-Signature": "t=1,v1=bad"}
    )
    assert r.status_code == 400
