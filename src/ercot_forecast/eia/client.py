from dataclasses import dataclass
from typing import Any, Iterator, Sequence

import requests
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)


@dataclass(frozen=True)
class EIARegionPage:
    rows: list[dict[str, Any]]
    total: int
    offset: int
    parameters: dict[str, Any]
    payload: dict[str, Any]


class EIAClientError(Exception):
    """Base error for EIA client failures."""


class RetryableEIAError(EIAClientError):
    """Temporary error that may succeed when retried."""


class NonRetryableEIAError(EIAClientError):
    """Invalid request or response that should not be retried."""


class EIAClient:
    REGION_DATA_URL = (
        "https://api.eia.gov/v2/electricity/rto/region-data/data/"
    )

    def __init__(
        self,
        api_key: str,
        page_size: int = 5000,
        timeout_seconds: int = 60,
        session: requests.Session | None = None,
    ) -> None:
        if not 1 <= page_size <= 5000:
            raise ValueError("page_size must be between 1 and 5000")

        self._api_key = api_key
        self._page_size = page_size
        self._timeout_seconds = timeout_seconds
        self._session = session or requests.Session()
    
    def build_region_data_parameters(
        self,
        *,
        start: str | None,
        end: str | None,
        offset: int,
        data_types: Sequence[str] = ("D", "DF"),
        respondent: str = "ERCO",
        frequency: str = "hourly",
    ) -> dict[str, Any]:
        parameters: dict[str, Any] = {
            "frequency": frequency,
            "data[0]": "value",
            "facets[type][]": list(data_types),
            "facets[respondent][]": [respondent],
            "sort[0][column]": "period",
            "sort[0][direction]": "asc",
            "offset": offset,
            "length": self._page_size,
        }

        if start is not None:
            parameters["start"] = start

        if end is not None:
            parameters["end"] = end

        return parameters
    
    @retry(
        retry=retry_if_exception_type(RetryableEIAError),
        stop=stop_after_attempt(4),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        reraise=True,
    )
    def fetch_region_data_page(
        self,
        *,
        start: str | None,
        end: str | None,
        offset: int,
        data_types: Sequence[str] = ("D", "DF"),
        respondent: str = "ERCO",
        frequency: str = "hourly",
    ) -> EIARegionPage:
        safe_parameters = self.build_region_data_parameters(
            start=start,
            end=end,
            offset=offset,
            data_types=data_types,
            respondent=respondent,
            frequency=frequency,
        )

        request_parameters = {
            **safe_parameters,
            "api_key": self._api_key,
        }

        try:
            response = self._session.get(
                self.REGION_DATA_URL,
                params=request_parameters,
                timeout=self._timeout_seconds,
            )
        except (requests.Timeout, requests.ConnectionError):
            raise RetryableEIAError(
                "Temporary connection failure while contacting EIA"
            ) from None

        if response.status_code == 429 or response.status_code >= 500:
            raise RetryableEIAError(
                f"EIA returned temporary HTTP status {response.status_code}"
            )

        if 400 <= response.status_code < 500:
            raise NonRetryableEIAError(
                f"EIA rejected the request with HTTP status "
                f"{response.status_code}"
            )

        try:
            payload = response.json()
            response_data = payload["response"]
            rows = response_data["data"]
            total = int(response_data["total"])
        except (KeyError, TypeError, ValueError):
            raise NonRetryableEIAError(
                "EIA returned an unexpected response structure"
            ) from None

        if not isinstance(rows, list):
            raise NonRetryableEIAError(
                "EIA response data is not a list"
            )

        return EIARegionPage(
            rows=rows,
            total=total,
            offset=offset,
            parameters=safe_parameters,
            payload=payload,
        )

    def iter_region_data(
        self,
        *,
        start: str | None = None,
        end: str | None = None,
        data_types: Sequence[str] = ("D", "DF"),
        respondent: str = "ERCO",
        frequency: str = "hourly",
        ) -> Iterator[EIARegionPage]:

        offset = 0
        accumulated = 0

        while True:
            page = self.fetch_region_data_page(
                start=start,
                end=end,
                offset=offset,
                data_types=data_types,
                respondent=respondent,
                frequency=frequency,
            )

            yield page

            received = len(page.rows)
            accumulated += received

            if received == 0:
                break

            if accumulated >= page.total:
                break

            offset += received

    def close(self) -> None:
        self._session.close()

    def __enter__(self) -> "EIAClient":
        return self

    def __exit__(self, *args: object) -> None:
        self.close()
        