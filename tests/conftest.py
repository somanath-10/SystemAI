import gc

import pytest
from fastapi.testclient import TestClient as BaseTestClient


class TestClient(BaseTestClient):
    __test__ = False

    def __init__(self, app, **kwargs):
        kwargs['headers'] = {**kwargs.get('headers', {}), 'Authorization': f'Bearer {app.state.api_token}'}
        super().__init__(app, **kwargs)


@pytest.fixture(autouse=True)
def collect_closed_test_runtimes():
    yield
    gc.collect()
