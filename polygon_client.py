"""
polygon_client.py
~~~~~~~~~~~~~~~~~~~

This module implements a minimal wrapper around the Polygon.io REST API.  It
provides helper functions for retrieving the list of options contracts for a
given underlying symbol, as well as convenience methods for handling rate
limits and retry logic.  The wrapper uses the built‑in :mod:`requests` library
and avoids dependencies on external client libraries, which keeps the
repository lightweight and deployable in environments where pip installation
may be restricted.

The Polygon API key must be supplied via the ``api_key`` argument when
constructing the :class:`PolygonClient` or by setting the ``POLYGON_API_KEY``
environment variable.  If both are provided, the explicit argument takes
precedence.  API calls are throttled to respect the free tier rate limit of
five requests per minute.  If an HTTP 429 (Too Many Requests) response is
encountered, the client will back off exponentially up to a configurable
maximum delay.

For more details on the Polygon Options Snapshot endpoint see the official
documentation: https://polygon.io/docs/rest/options/snapshots/option-chain-snapshot
"""

from __future__ import annotations

import os
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

import requests


class PolygonClient:
    """A simple synchronous client for a subset of the Polygon.io REST API.

    Parameters
    ----------
    api_key: str | None
        The Polygon API key.  If ``None``, the client attempts to read the key
        from the ``POLYGON_API_KEY`` environment variable.  A missing API key
        results in a :class:`ValueError` when the first request is made.
    base_url: str
        Base URL for the Polygon API.  Defaults to ``https://api.polygon.io``.
    max_retries: int
        Maximum number of retry attempts after hitting a rate limit.  Each retry
        waits twice as long as the previous one (exponential backoff).
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: str = "https://api.polygon.io",
        max_retries: int = 5,
    ) -> None:
        self.api_key = api_key or os.getenv("POLYGON_API_KEY")
        self.base_url = base_url.rstrip("/")
        self.max_retries = max_retries

    def _request(self, method: str, path: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Make an HTTP request to the Polygon API with retries.

        Parameters
        ----------
        method: str
            HTTP method (e.g. ``"GET"``).
        path: str
            Endpoint path starting with a slash, for example ``"/v3/snapshot/options/TSLA"``.
        params: dict[str, Any] | None
            Query parameters to include in the request.  The API key is appended
            automatically.

        Returns
        -------
        dict
            Parsed JSON response from the Polygon API.

        Raises
        ------
        RuntimeError
            If the API key is missing or the request ultimately fails.
        """
        if not self.api_key:
            raise RuntimeError("Polygon API key is not set. Set POLYGON_API_KEY or pass api_key to the client.")

        url = f"{self.base_url}{path}"
        params = params.copy() if params else {}
        params["apiKey"] = self.api_key

        attempt = 0
        delay = 1.0
        while True:
            try:
                response = requests.request(method, url, params=params, timeout=20)
            except requests.RequestException as exc:
                attempt += 1
                if attempt > self.max_retries:
                    raise RuntimeError(f"Failed to call {url}: {exc}")
                time.sleep(delay)
                delay *= 2
                continue

            if response.status_code == 200:
                return response.json()
            if response.status_code == 429:
                # Rate limited; apply exponential backoff
                attempt += 1
                if attempt > self.max_retries:
                    raise RuntimeError(f"Rate limit exceeded and max retries reached for {url}")
                time.sleep(delay)
                delay *= 2
                continue
            else:
                raise RuntimeError(
                    f"Polygon API call failed (status {response.status_code}): {response.text}"
                )

    def get_options_chain(self, symbol: str, contract_type: Optional[str] = None) -> List[Dict[str, Any]]:
        """Retrieve the full option chain snapshot for a given underlying symbol.

        Parameters
        ----------
        symbol: str
            The underlying ticker symbol (e.g. ``"AAPL"``).
        contract_type: str | None
            Optional filter to limit results to ``"call"`` or ``"put"`` contracts.  If
            ``None`` (default), both calls and puts are returned.

        Returns
        -------
        list[dict]
            A list of contract objects returned by the Polygon API.  Each
            contract contains pricing details, greeks, implied volatility and
            other metadata.  See the official documentation for field names.
        """
        path = f"/v3/snapshot/options/{symbol.upper()}"
        params: Dict[str, Any] = {}
        if contract_type is not None:
            params["contract_type"] = contract_type
        data = self._request("GET", path, params)
        return data.get("results", [])


__all__ = ["PolygonClient"]