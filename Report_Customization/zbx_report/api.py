"""
Zabbix API Client
Compatible with Zabbix 7.0 and 8.0

Authentication modes:
  - API token (recommended for Zabbix 5.4+)
  - Username/password (all versions)

Zabbix 7.0: uses 'Authorization: Bearer <token>' header
Zabbix 8.0: same as 7.0 with additional API improvements
"""

import json
import ssl
import urllib.request
import urllib.error
from typing import Any, Dict, List, Optional


class ZabbixAPIError(Exception):
    """Raised when Zabbix API returns an error response."""
    def __init__(self, message: str, code: int = None, data: Any = None):
        super().__init__(message)
        self.code = code
        self.data = data


class ZabbixAPI:
    """
    JSON-RPC Zabbix API client.
    Compatible with Zabbix 7.0 and 8.0.

    Usage (API token):
        api = ZabbixAPI("http://zabbix/")
        api.login(api_token="your_token")

    Usage (user/password):
        api = ZabbixAPI("http://zabbix/")
        api.login(user="Admin", password="zabbix")
        api.logout()
    """

    # Zabbix severity level names and colors
    SEVERITIES = {
        0: {"name": "Not classified", "color": "#97AAB3"},
        1: {"name": "Information",    "color": "#7499FF"},
        2: {"name": "Warning",        "color": "#FFC859"},
        3: {"name": "Average",        "color": "#FFA059"},
        4: {"name": "High",           "color": "#E97659"},
        5: {"name": "Disaster",       "color": "#E45959"},
    }

    def __init__(self, url: str, verify_ssl: bool = True, timeout: int = 30):
        self.url = url.rstrip("/") + "/api_jsonrpc.php"
        self.verify_ssl = verify_ssl
        self.timeout = timeout
        self._auth: Optional[str] = None
        self._request_id = 0
        self.api_version: Optional[str] = None
        self._use_header_auth = False  # True for Zabbix 5.4+

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _ssl_context(self) -> Optional[ssl.SSLContext]:
        if not self.verify_ssl:
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            return ctx
        return None

    def _call(self, method: str, params: Any = None, auth: bool = True) -> Any:
        """Execute a JSON-RPC call and return the result."""
        self._request_id += 1

        payload: Dict[str, Any] = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params if params is not None else {},
            "id": self._request_id,
        }

        # Legacy auth in payload for Zabbix < 5.4
        if auth and self._auth and not self._use_header_auth:
            payload["auth"] = self._auth

        data = json.dumps(payload).encode("utf-8")

        headers = {
            "Content-Type": "application/json-rpc",
            "Accept": "application/json",
            "User-Agent": "ZBX-HTML-Reporter/1.0",
        }

        # Bearer token auth for Zabbix 5.4+
        if auth and self._auth and self._use_header_auth:
            headers["Authorization"] = f"Bearer {self._auth}"

        req = urllib.request.Request(
            self.url, data=data, headers=headers, method="POST"
        )

        try:
            with urllib.request.urlopen(
                req, timeout=self.timeout, context=self._ssl_context()
            ) as resp:
                body = resp.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            raise ZabbixAPIError(f"HTTP {exc.code}: {exc.reason}") from exc
        except urllib.error.URLError as exc:
            raise ZabbixAPIError(f"Connection error: {exc.reason}") from exc

        try:
            result = json.loads(body)
        except json.JSONDecodeError as exc:
            raise ZabbixAPIError(f"Invalid JSON response: {exc}") from exc

        if "error" in result:
            err = result["error"]
            raise ZabbixAPIError(
                err.get("message", "API error"),
                code=err.get("code"),
                data=err.get("data"),
            )

        return result.get("result")

    def _major_version(self) -> int:
        if self.api_version:
            return int(self.api_version.split(".")[0])
        return 0

    # ------------------------------------------------------------------
    # Authentication
    # ------------------------------------------------------------------

    def get_api_version(self) -> str:
        """Return Zabbix API version string, e.g. '7.0.0'."""
        self.api_version = self._call("apiinfo.version", auth=False)
        # Zabbix 5.4+ uses header-based auth
        self._use_header_auth = self._major_version() >= 5
        return self.api_version

    def login(
        self,
        user: str = None,
        password: str = None,
        api_token: str = None,
    ) -> bool:
        """
        Authenticate with Zabbix.

        For Zabbix 7.0/8.0, prefer api_token.
        User/password fallback is also supported for all versions.
        """
        if not self.api_version:
            self.get_api_version()

        if api_token:
            self._auth = api_token
            self._use_header_auth = True
            return True

        if user and password:
            # Zabbix 5.2 renamed 'user' → 'username'
            user_key = "username" if self._major_version() >= 5 else "user"
            result = self._call(
                "user.login",
                {user_key: user, "password": password},
                auth=False,
            )
            self._auth = result
            return True

        raise ZabbixAPIError(
            "Provide either api_token or user+password."
        )

    def logout(self):
        """Invalidate a session token (not needed for API tokens)."""
        if self._auth and not self._use_header_auth:
            try:
                self._call("user.logout", {})
            except ZabbixAPIError:
                pass
        self._auth = None

    # ------------------------------------------------------------------
    # Problem & Event queries
    # ------------------------------------------------------------------

    def get_problems(
        self,
        time_from: int = None,
        time_till: int = None,
        severities: List[int] = None,
        limit: int = 0,
    ) -> List[Dict]:
        """
        Fetch problems (unresolved + recently resolved).

        Returns list of problem objects with host/trigger detail.
        """
        params: Dict[str, Any] = {
            "output": "extend",
            "selectTags": "extend",
            "selectAcknowledges": ["userid", "message", "clock", "action"],
            "recent": False,
            "sortfield": ["eventid"],
            "sortorder": "DESC",
        }

        if severities is not None:
            params["severities"] = severities
        else:
            params["severities"] = list(range(0, 6))

        if time_from:
            params["time_from"] = time_from
        if time_till:
            params["time_till"] = time_till
        if limit > 0:
            params["limit"] = limit

        return self._call("problem.get", params)

    def get_events(
        self,
        time_from: int = None,
        time_till: int = None,
        severities: List[int] = None,
        limit: int = 10000,
    ) -> List[Dict]:
        """
        Fetch trigger events (PROBLEM and RECOVERY) in the given window.

        Returns list of event objects with host/trigger detail.
        """
        params: Dict[str, Any] = {
            "output": "extend",
            "selectHosts": ["hostid", "name"],
            "selectRelatedObject": ["triggerid", "description", "priority", "url"],
            "source": 0,   # trigger-based events
            "object": 0,   # trigger object
            "value": [0, 1],  # 0=PROBLEM, 1=RECOVERED
            "sortfield": ["clock"],
            "sortorder": "DESC",
            "limit": limit,
        }

        if severities is not None:
            params["severities"] = severities
        else:
            params["severities"] = list(range(0, 6))

        if time_from:
            params["time_from"] = time_from
        if time_till:
            params["time_till"] = time_till

        return self._call("event.get", params)

    # ------------------------------------------------------------------
    # Trigger queries
    # ------------------------------------------------------------------

    def get_triggers(
        self,
        triggerids: List[str] = None,
        min_priority: int = 0,
        only_problems: bool = False,
        with_hosts_and_groups: bool = True,
    ) -> List[Dict]:
        """Fetch trigger objects with expanded descriptions."""
        params: Dict[str, Any] = {
            "output": "extend",
            "expandDescription": True,
            "expandComment": True,
            "monitored": True,
            "min_severity": min_priority,
            "sortfield": ["priority"],
            "sortorder": "DESC",
        }

        if with_hosts_and_groups:
            params["selectHosts"] = ["hostid", "name", "status"]
            params["selectGroups"] = ["groupid", "name"]

        if only_problems:
            params["value"] = 1

        if triggerids:
            params["triggerids"] = triggerids

        return self._call("trigger.get", params)

    # ------------------------------------------------------------------
    # Host / Group queries
    # ------------------------------------------------------------------

    def get_host_groups(self) -> List[Dict]:
        return self._call(
            "hostgroup.get",
            {"output": ["groupid", "name"], "monitored_hosts": True, "sortfield": "name"},
        )

    def get_hosts(self, groupids: List[str] = None) -> List[Dict]:
        params: Dict[str, Any] = {
            "output": ["hostid", "name", "status"],
            "monitored": True,
        }
        if groupids:
            params["groupids"] = groupids
        return self._call("host.get", params)
