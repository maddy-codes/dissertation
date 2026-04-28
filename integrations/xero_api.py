from __future__ import annotations

import base64
import json
import os
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, Dict, Optional

import requests


import threading

XERO_TOKEN_URL = "https://identity.xero.com/connect/token"
XERO_CONNECTIONS_URL = "https://api.xero.com/connections"
XERO_ACCOUNTING_BASE = "https://api.xero.com/api.xro/2.0"

_GLOBAL_ACCOUNTS_CACHE = {}
_GLOBAL_ACCOUNTS_CACHE_TS = {}
_ACCOUNTS_LOCK = threading.Lock()

_GLOBAL_TX_CACHE = {}  # key: (tenant_id, start_date, end_date, type)
_GLOBAL_TX_CACHE_TS = {}
_TX_LOCK = threading.Lock()

@dataclass
class XeroToken:
    access_token: str
    refresh_token: str
    expires_at: float


class XeroClient:
    """
    Minimal Xero Accounting API client using a refresh token.

    Note: Xero rotates refresh tokens. If you don't persist the new refresh token,
    your env var will eventually go stale. You can set XERO_TOKEN_CACHE_PATH
    to persist updated tokens on disk (JSON).
    """

    def __init__(
        self,
        *,
        client_id: str,
        client_secret: str,
        refresh_token: str,
        token_cache_path: Optional[str] = None,
        session: Optional[requests.Session] = None,
        user=None,
    ) -> None:
        self._client_id = client_id
        self._client_secret = client_secret
        self._initial_refresh_token = refresh_token
        self._token_cache_path = token_cache_path
        self._session = session or requests.Session()
        self._token: Optional[XeroToken] = None
        self.user = user
        self._accounts_cache: Dict[str, Any] = {}

        if self.user:
            cached = self.user.get_xero_token()
            if cached and cached.get("access_token") and cached.get("refresh_token") and cached.get("expires_at"):
                self._token = XeroToken(
                    access_token=cached["access_token"],
                    refresh_token=cached["refresh_token"],
                    expires_at=float(cached["expires_at"]),
                )
        elif self._token_cache_path:
            cached = self._load_cached_token()
            if cached:
                self._token = cached

    @staticmethod
    def from_env() -> "XeroClient":
        cid = os.environ.get("XERO_CLIENT_ID", "").strip()
        sec = os.environ.get("XERO_CLIENT_SECRET", "").strip()
        ref = os.environ.get("XERO_REFRESH_TOKEN", "").strip()
        if not cid or not sec or not ref:
            raise RuntimeError(
                "Xero not configured. Set XERO_CLIENT_ID, XERO_CLIENT_SECRET, XERO_REFRESH_TOKEN."
            )
        cache_path = os.environ.get("XERO_TOKEN_CACHE_PATH", "").strip() or None
        return XeroClient(
            client_id=cid,
            client_secret=sec,
            refresh_token=ref,
            token_cache_path=cache_path,
        )

    def _auth_header_basic(self) -> str:
        raw = f"{self._client_id}:{self._client_secret}".encode("utf-8")
        return "Basic " + base64.b64encode(raw).decode("ascii")

    def _get(self, url: str, **kwargs):
        """
        GET wrapper that respects Xero's 429 Retry-After header.

        Xero's per-tenant ceiling is 60 calls/min/5 concurrent. Pulling a
        Trial Balance + P&L + comparison reports + paginated transactions can
        easily breach this on a busy account, so we wait the requested cool-off
        period (capped) and retry a small number of times before giving up.
        """
        max_retries = int(os.environ.get("XERO_MAX_RETRIES", "4"))
        max_backoff = float(os.environ.get("XERO_MAX_BACKOFF_SECONDS", "30"))

        attempt = 0
        while True:
            resp = self._session.get(url, **kwargs)
            if resp.status_code != 429 or attempt >= max_retries:
                return resp
            retry_after = resp.headers.get("Retry-After")
            try:
                wait = float(retry_after) if retry_after is not None else (2 ** attempt)
            except ValueError:
                wait = 2 ** attempt
            wait = min(max(wait, 1.0), max_backoff)
            attempt += 1
            try:
                # Lazy import so we don't pollute the top of the module
                import time as _time
                _time.sleep(wait)
            except Exception:
                pass

    def _load_cached_token(self) -> Optional[XeroToken]:
        try:
            with open(self._token_cache_path, "r", encoding="utf-8") as f:
                d = json.load(f)
            if not d.get("access_token") or not d.get("refresh_token") or not d.get(
                "expires_at"
            ):
                return None
            return XeroToken(
                access_token=d["access_token"],
                refresh_token=d["refresh_token"],
                expires_at=float(d["expires_at"]),
            )
        except Exception:
            return None

    def _save_cached_token(self) -> None:
        if self.user and self._token:
            from setup.models import db
            self.user.set_xero_token({
                "access_token": self._token.access_token,
                "refresh_token": self._token.refresh_token,
                "expires_at": self._token.expires_at,
            })
            db.session.add(self.user)
            db.session.commit()
            return
            
        if not self._token_cache_path or not self._token:
            return
        try:
            with open(self._token_cache_path, "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "access_token": self._token.access_token,
                        "refresh_token": self._token.refresh_token,
                        "expires_at": self._token.expires_at,
                    },
                    f,
                    ensure_ascii=True,
                    indent=2,
                    sort_keys=True,
                )
        except Exception:
            # Non-fatal; proceed without persistence.
            pass

    def _ensure_token(self) -> XeroToken:
        now = time.time()
        if self._token and (self._token.expires_at - 30) > now:
            return self._token

        refresh = self._token.refresh_token if self._token else self._initial_refresh_token
        resp = self._session.post(
            XERO_TOKEN_URL,
            headers={"Authorization": self._auth_header_basic()},
            data={"grant_type": "refresh_token", "refresh_token": refresh},
            timeout=30,
        )
        if resp.status_code >= 400:
            raise RuntimeError(f"Xero token refresh failed: {resp.status_code} {resp.text}")
        data = resp.json()
        access = data["access_token"]
        new_refresh = data["refresh_token"]
        expires_in = float(data.get("expires_in", 1800))
        self._token = XeroToken(
            access_token=access,
            refresh_token=new_refresh,
            expires_at=time.time() + expires_in,
        )
        self._save_cached_token()
        return self._token

    def _headers(self, tenant_id: str) -> Dict[str, str]:
        tok = self._ensure_token()
        return {
            "Authorization": f"Bearer {tok.access_token}",
            "xero-tenant-id": tenant_id,
            "Accept": "application/json",
        }

    def list_connections(self) -> list[dict[str, Any]]:
        tok = self._ensure_token()
        resp = self._get(
            XERO_CONNECTIONS_URL,
            headers={"Authorization": f"Bearer {tok.access_token}", "Accept": "application/json"},
            timeout=30,
        )
        if resp.status_code >= 400:
            raise RuntimeError(f"Xero connections failed: {resp.status_code} {resp.text}")
        return resp.json()

    def get_accounts(self, tenant_id: str) -> dict[str, Any]:
        with _ACCOUNTS_LOCK:
            now = time.time()
            if tenant_id in _GLOBAL_ACCOUNTS_CACHE and (now - _GLOBAL_ACCOUNTS_CACHE_TS.get(tenant_id, 0)) < 300:
                return _GLOBAL_ACCOUNTS_CACHE[tenant_id]
                
            url = f"{XERO_ACCOUNTING_BASE}/Accounts"
            resp = self._get(url, headers=self._headers(tenant_id), timeout=60)
            if resp.status_code >= 400:
                raise RuntimeError(f"Xero accounts failed: {resp.status_code} {resp.text}")
                
            result = resp.json()
            _GLOBAL_ACCOUNTS_CACHE[tenant_id] = result
            _GLOBAL_ACCOUNTS_CACHE_TS[tenant_id] = now
            return result

    def get_bank_transactions(
        self, tenant_id: str, start_date: date = None, end_date: date = None, account_code: str = None, max_pages: int = 50
    ) -> dict[str, Any]:
        # Use cache for broad queries to enable instant lookup for subsequent parallel calls
        cache_key = (tenant_id, str(start_date), str(end_date), "bank_tx")
        
        # Fast path if already cached
        now = time.time()
        if not account_code and cache_key in _GLOBAL_TX_CACHE and (now - _GLOBAL_TX_CACHE_TS.get(cache_key, 0)) < 600:
            return _GLOBAL_TX_CACHE[cache_key]

        with _TX_LOCK:
            # Check again inside lock
            now = time.time()
            if not account_code and cache_key in _GLOBAL_TX_CACHE and (now - _GLOBAL_TX_CACHE_TS.get(cache_key, 0)) < 600:
                return _GLOBAL_TX_CACHE[cache_key]

            url = f"{XERO_ACCOUNTING_BASE}/BankTransactions"
            all_items: list[dict[str, Any]] = []

            conditions = []
            if start_date:
                conditions.append(f"Date >= DateTime({start_date.year},{start_date.month},{start_date.day})")
            if end_date:
                conditions.append(f"Date < DateTime({end_date.year},{end_date.month},{end_date.day})")
            if account_code:
                conditions.append(f'BankAccount.Code == "{account_code}"')
                
            where = " && ".join(conditions) if conditions else None

            for page in range(1, max_pages + 1):
                params = {"page": page}
                if where:
                    params["where"] = where
                    
                resp = self._get(
                    url,
                    headers=self._headers(tenant_id),
                    params=params,
                    timeout=60,
                )
                if resp.status_code >= 400:
                    raise RuntimeError(
                        f"Xero bank transactions failed: {resp.status_code} {resp.text}"
                    )
                data = resp.json()
                items = data.get("BankTransactions") or []
                if not isinstance(items, list) or not items:
                    break
                all_items.extend(items)

            result = {"BankTransactions": all_items, "Pagination": {"where": where}}
            if not account_code:
                _GLOBAL_TX_CACHE[cache_key] = result
                _GLOBAL_TX_CACHE_TS[cache_key] = now
                
            return result

    def get_invoices(
        self, tenant_id: str, start_date: date = None, end_date: date = None, contact_id: str = None, statuses: list[str] = None, max_pages: int = 50
    ) -> dict[str, Any]:
        cache_key = (tenant_id, str(start_date), str(end_date), "invoices")
        
        # Fast path
        now = time.time()
        if not contact_id and cache_key in _GLOBAL_TX_CACHE and (now - _GLOBAL_TX_CACHE_TS.get(cache_key, 0)) < 600:
            return _GLOBAL_TX_CACHE[cache_key]

        with _TX_LOCK:
            # Double check
            now = time.time()
            if not contact_id and cache_key in _GLOBAL_TX_CACHE and (now - _GLOBAL_TX_CACHE_TS.get(cache_key, 0)) < 600:
                return _GLOBAL_TX_CACHE[cache_key]

            url = f"{XERO_ACCOUNTING_BASE}/Invoices"
            all_items: list[dict[str, Any]] = []

            conditions = []
            if start_date:
                conditions.append(f"Date >= DateTime({start_date.year},{start_date.month},{start_date.day})")
            if end_date:
                conditions.append(f"Date < DateTime({end_date.year},{end_date.month},{end_date.day})")
            if contact_id:
                conditions.append(f'Contact.ContactID == Guid("{contact_id}")')
            if statuses:
                status_str = ",".join([f'"{s}"' for s in statuses])
                conditions.append(f"Status == {status_str}")

            where = " && ".join(conditions) if conditions else None

            for page in range(1, max_pages + 1):
                params = {"page": page}
                if where:
                    params["where"] = where

                resp = self._get(
                    url,
                    headers=self._headers(tenant_id),
                    params=params,
                    timeout=60,
                )
                if resp.status_code >= 400:
                    raise RuntimeError(f"Xero invoices failed: {resp.status_code} {resp.text}")
                data = resp.json()
                items = data.get("Invoices") or []
                if not isinstance(items, list) or not items:
                    break
                all_items.extend(items)

            result = {"Invoices": all_items}
            if not contact_id:
                _GLOBAL_TX_CACHE[cache_key] = result
                _GLOBAL_TX_CACHE_TS[cache_key] = now
                
            return result

    def get_manual_journals(
        self,
        tenant_id: str,
        start_date: date = None,
        end_date: date = None,
        max_pages: int = 50,
    ) -> dict[str, Any]:
        """Fetch Manual Journals over a date window. Cached on the broad query."""
        cache_key = (tenant_id, str(start_date), str(end_date), "manual_journals")

        now = time.time()
        if cache_key in _GLOBAL_TX_CACHE and (now - _GLOBAL_TX_CACHE_TS.get(cache_key, 0)) < 600:
            return _GLOBAL_TX_CACHE[cache_key]

        with _TX_LOCK:
            now = time.time()
            if cache_key in _GLOBAL_TX_CACHE and (now - _GLOBAL_TX_CACHE_TS.get(cache_key, 0)) < 600:
                return _GLOBAL_TX_CACHE[cache_key]

            url = f"{XERO_ACCOUNTING_BASE}/ManualJournals"
            all_items: list[dict[str, Any]] = []

            conditions = []
            if start_date:
                conditions.append(
                    f"Date >= DateTime({start_date.year},{start_date.month},{start_date.day})"
                )
            if end_date:
                conditions.append(
                    f"Date < DateTime({end_date.year},{end_date.month},{end_date.day})"
                )
            where = " && ".join(conditions) if conditions else None

            for page in range(1, max_pages + 1):
                params = {"page": page}
                if where:
                    params["where"] = where
                resp = self._get(
                    url,
                    headers=self._headers(tenant_id),
                    params=params,
                    timeout=60,
                )
                if resp.status_code >= 400:
                    raise RuntimeError(
                        f"Xero manual journals failed: {resp.status_code} {resp.text}"
                    )
                data = resp.json()
                items = data.get("ManualJournals") or []
                if not isinstance(items, list) or not items:
                    break
                all_items.extend(items)

            result = {"ManualJournals": all_items}
            _GLOBAL_TX_CACHE[cache_key] = result
            _GLOBAL_TX_CACHE_TS[cache_key] = now
            return result

    def get_balance_sheet(self, tenant_id: str, report_date: date) -> dict[str, Any]:
        url = f"{XERO_ACCOUNTING_BASE}/Reports/BalanceSheet"
        resp = self._get(
            url,
            headers=self._headers(tenant_id),
            params={"date": report_date.isoformat()},
            timeout=60,
        )
        if resp.status_code >= 400:
            raise RuntimeError(f"Xero balance sheet failed: {resp.status_code} {resp.text}")
        return resp.json()

    def get_trial_balance(self, tenant_id: str, report_date: date) -> dict[str, Any]:
        url = f"{XERO_ACCOUNTING_BASE}/Reports/TrialBalance"
        resp = self._get(
            url,
            headers=self._headers(tenant_id),
            params={"date": report_date.isoformat()},
            timeout=60,
        )
        if resp.status_code >= 400:
            raise RuntimeError(f"Xero trial balance failed: {resp.status_code} {resp.text}")
        return resp.json()

    def get_profit_and_loss(self, tenant_id: str, start_date: date, end_date: date) -> dict[str, Any]:
        url = f"{XERO_ACCOUNTING_BASE}/Reports/ProfitAndLoss"
        resp = self._get(
            url,
            headers=self._headers(tenant_id),
            params={"fromDate": start_date.isoformat(), "toDate": end_date.isoformat()},
            timeout=60,
        )
        if resp.status_code >= 400:
            raise RuntimeError(f"Xero P&L failed: {resp.status_code} {resp.text}")
        return resp.json()


def parse_year_end_date(val: Any) -> Optional[date]:
    if isinstance(val, date):
        return val
    if isinstance(val, str):
        s = val.strip()
        for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%Y/%m/%d"):
            try:
                return datetime.strptime(s, fmt).date()
            except Exception:
                pass
    return None


def default_two_year_window(year_end: date) -> tuple[date, date]:
    # Inclusive-ish range: [year_end - 730d, year_end + 1d)
    start = year_end - timedelta(days=730)
    end = year_end + timedelta(days=1)
    return start, end

