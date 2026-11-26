import os
from datetime import date

import pytest
from sqlalchemy.orm import sessionmaker

from app import db as dbmod
from app import models  # noqa: F401  (register tables)
from app.providers import FakeEmail, FakeProvider, set_email_provider, set_payment_provider
from app.services import Actor, create_customer

BROKER = Actor("Bea Broker", "broker")


@pytest.fixture()
def db():
    engine = dbmod.make_engine(os.environ.get("TEST_DATABASE_URL", "sqlite://"))
    dbmod.Base.metadata.drop_all(engine)
    dbmod.Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    set_payment_provider(FakeProvider())
    set_email_provider(FakeEmail())
    s = Session()
    yield s
    s.close()


@pytest.fixture()
def customer(db):
    c, _, _ = create_customer(db, BROKER, "Acme AI Inc", "Ada Founder", "ada@acme.test")
    db.commit()
    return c


START = date(2026, 1, 1)
END = date(2027, 1, 1)
