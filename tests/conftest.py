import pytest
from fulfillment.db import FulfillmentDB


@pytest.fixture
def db(tmp_path):
    db_path = str(tmp_path / "test_fulfillment.db")
    return FulfillmentDB(db_path)
