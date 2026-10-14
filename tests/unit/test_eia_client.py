class FakeResponse:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload


class FakeSession:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.calls = []

    def get(self, url, params, timeout):
        self.calls.append(params)
        return next(self.responses)

    def close(self):
        pass

from ercot_forecast.eia.client import EIAClient


def test_paginates_beyond_5000_rows():
    first_rows = [{"period": str(index)} for index in range(5000)]
    second_rows = [{"period": "final"}]

    session = FakeSession([
        FakeResponse(
            200,
            {"response": {"total": 5001, "data": first_rows}},
        ),
        FakeResponse(
            200,
            {"response": {"total": 5001, "data": second_rows}},
        ),
    ])

    client = EIAClient(
        api_key="test-key",
        page_size=5000,
        session=session,
    )

    pages = list(client.iter_region_data())

    assert [page.offset for page in pages] == [0, 5000]
    assert sum(len(page.rows) for page in pages) == 5001
    assert all("api_key" not in page.parameters for page in pages)