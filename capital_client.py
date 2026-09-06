"""Thin wrapper around the Capital.com REST API.

Docs: https://open-api.capital.com/
Only the endpoints this bot actually needs are wrapped. If Capital.com
changes their API, check the Swagger docs linked above before assuming
this code is wrong.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

import requests


class CapitalApiError(RuntimeError):
    pass


@dataclass
class Position:
    deal_id: str
    epic: str
    direction: str
    size: float
    open_level: float
    stop_level: float | None
    profit_level: float | None


class CapitalClient:
    SESSION_TTL_SECONDS = 9 * 60  # sessions expire after 10 min idle; refresh early

    def __init__(self, base_url: str, identifier: str, api_key: str, password: str):
        self.base_url = base_url.rstrip("/")
        self.identifier = identifier
        self.api_key = api_key
        self.password = password
        self._session = requests.Session()
        self._cst: str | None = None
        self._security_token: str | None = None
        self._session_created_at: float = 0.0

    # -- session management -------------------------------------------------

    def _login(self) -> None:
        resp = self._session.post(
            f"{self.base_url}/api/v1/session",
            headers={"X-CAP-API-KEY": self.api_key},
            json={"identifier": self.identifier, "password": self.password},
            timeout=15,
        )
        if resp.status_code != 200:
            raise CapitalApiError(
                f"Login failed ({resp.status_code}): {resp.text}"
            )
        self._cst = resp.headers.get("CST")
        self._security_token = resp.headers.get("X-SECURITY-TOKEN")
        if not self._cst or not self._security_token:
            raise CapitalApiError("Login succeeded but session tokens were missing")
        self._session_created_at = time.monotonic()

    def _ensure_session(self) -> None:
        if self._cst is None or (time.monotonic() - self._session_created_at) > self.SESSION_TTL_SECONDS:
            self._login()

    def _headers(self) -> dict[str, str]:
        assert self._cst and self._security_token
        return {
            "X-CAP-API-KEY": self.api_key,
            "CST": self._cst,
            "X-SECURITY-TOKEN": self._security_token,
        }

    def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        self._ensure_session()
        resp = self._session.request(
            method, f"{self.base_url}{path}", headers=self._headers(), timeout=15, **kwargs
        )
        if resp.status_code == 401:
            # session may have been invalidated server-side; retry once after re-login
            self._login()
            resp = self._session.request(
                method, f"{self.base_url}{path}", headers=self._headers(), timeout=15, **kwargs
            )
        if resp.status_code >= 400:
            raise CapitalApiError(f"{method} {path} failed ({resp.status_code}): {resp.text}")
        if not resp.content:
            return {}
        return resp.json()

    # -- account --------------------------------------------------------------

    def get_accounts(self) -> list[dict[str, Any]]:
        return self._request("GET", "/api/v1/accounts").get("accounts", [])

    def get_primary_account(self) -> dict[str, Any]:
        accounts = self.get_accounts()
        if not accounts:
            raise CapitalApiError("No accounts returned for this login")
        for acc in accounts:
            if acc.get("preferred"):
                return acc
        return accounts[0]

    @staticmethod
    def get_equity(account: dict[str, Any]) -> float:
        """Extract the numeric balance from an /accounts entry (balance is a nested object)."""
        return account["balance"]["balance"]

    def top_up_demo(self, amount: float) -> dict[str, Any]:
        """Demo accounts only. `amount` is added to the current balance (negative to reduce)."""
        return self._request("POST", "/api/v1/accounts/topUp", json={"amount": amount})

    # -- market data ------------------------------------------------------------

    def search_markets(self, search_term: str) -> list[dict[str, Any]]:
        return self._request(
            "GET", "/api/v1/markets", params={"searchTerm": search_term}
        ).get("markets", [])

    def get_market(self, epic: str) -> dict[str, Any]:
        return self._request("GET", f"/api/v1/markets/{epic}")

    def get_prices(self, epic: str, resolution: str = "HOUR", max_points: int = 200) -> list[dict[str, Any]]:
        """resolution: MINUTE, MINUTE_5, MINUTE_15, MINUTE_30, HOUR, HOUR_4, DAY, WEEK"""
        data = self._request(
            "GET",
            f"/api/v1/prices/{epic}",
            params={"resolution": resolution, "max": max_points},
        )
        return data.get("prices", [])

    # -- positions ------------------------------------------------------------

    def get_open_positions(self) -> list[Position]:
        data = self._request("GET", "/api/v1/positions").get("positions", [])
        positions = []
        for item in data:
            pos = item["position"]
            market = item["market"]
            positions.append(
                Position(
                    deal_id=pos["dealId"],
                    epic=market["epic"],
                    direction=pos["direction"],
                    size=pos["size"],
                    open_level=pos["level"],
                    stop_level=pos.get("stopLevel"),
                    profit_level=pos.get("profitLevel"),
                )
            )
        return positions

    def open_position(
        self,
        epic: str,
        direction: str,
        size: float,
        stop_level: float | None = None,
        profit_level: float | None = None,
    ) -> str:
        payload: dict[str, Any] = {
            "epic": epic,
            "direction": direction,  # "BUY" or "SELL"
            "size": size,
        }
        if stop_level is not None:
            payload["stopLevel"] = stop_level
        if profit_level is not None:
            payload["profitLevel"] = profit_level
        result = self._request("POST", "/api/v1/positions", json=payload)
        deal_ref = result.get("dealReference")
        if not deal_ref:
            raise CapitalApiError(f"Open position did not return a dealReference: {result}")
        return deal_ref

    def close_position(self, deal_id: str) -> None:
        self._request("DELETE", f"/api/v1/positions/{deal_id}")
