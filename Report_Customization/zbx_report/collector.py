"""
Data Collector
Fetches and normalises Zabbix data for all report types.

Report windows
--------------
  hourly   – last 1 hour
  4hr      – last 4 hours
  8hr      – last 8 hours
  top20    – configurable window (default 24 h), top 20 triggers by fire count
"""

import time
from collections import defaultdict
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

from .api import ZabbixAPI, ZabbixAPIError


# ─────────────────────────────────────────────────────────────────────────────
# helpers
# ─────────────────────────────────────────────────────────────────────────────

def _now_ts() -> int:
    return int(time.time())


def _ts_to_dt(ts: int) -> datetime:
    return datetime.fromtimestamp(int(ts), tz=timezone.utc).astimezone()


def _duration_str(seconds: int) -> str:
    """Convert a duration in seconds to a human-readable string."""
    if seconds < 0:
        seconds = 0
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}h {m:02d}m {s:02d}s"
    if m:
        return f"{m}m {s:02d}s"
    return f"{s}s"


SEVERITY_NAMES = {
    0: "Not classified",
    1: "Information",
    2: "Warning",
    3: "Average",
    4: "High",
    5: "Disaster",
}

SEVERITY_COLORS = {
    0: "#97AAB3",
    1: "#7499FF",
    2: "#FFC859",
    3: "#FFA059",
    4: "#E97659",
    5: "#E45959",
}


# ─────────────────────────────────────────────────────────────────────────────
# Collector
# ─────────────────────────────────────────────────────────────────────────────

class DataCollector:
    """
    High-level collector that wraps ZabbixAPI queries and returns
    pre-processed dicts suitable for the renderer.
    """

    def __init__(self, api: ZabbixAPI):
        self.api = api

    # ------------------------------------------------------------------
    # Window helpers
    # ------------------------------------------------------------------

    @staticmethod
    def window(hours: float) -> Tuple[int, int]:
        """Return (time_from, time_till) for the last <hours> hours."""
        till = _now_ts()
        frm = till - int(hours * 3600)
        return frm, till

    # ------------------------------------------------------------------
    # Enrichment
    # ------------------------------------------------------------------

    def _enrich_problems(self, problems: List[Dict]) -> List[Dict]:
        """
        Add human-readable fields to raw problem objects.

        Adds: severity_name, severity_color, start_dt, duration_str,
              r_clock_dt (if recovered), host_name, trigger_desc.
        """
        if not problems:
            return []

        # Bulk-fetch triggers for all objectids
        objectids = list({p["objectid"] for p in problems})
        try:
            triggers = self.api.get_triggers(triggerids=objectids)
            trigger_map = {t["triggerid"]: t for t in triggers}
        except ZabbixAPIError:
            trigger_map = {}

        now = _now_ts()
        out = []
        for p in problems:
            sev = int(p.get("severity", 0))
            clock = int(p.get("clock", 0))
            r_clock = int(p.get("r_clock", 0))

            end_ts = r_clock if r_clock else now
            duration = end_ts - clock

            trigger = trigger_map.get(p["objectid"], {})
            hosts = trigger.get("hosts", [])
            host_name = ", ".join(h["name"] for h in hosts) if hosts else "—"
            groups = trigger.get("groups", [])
            group_name = ", ".join(g["name"] for g in groups) if groups else "—"

            enriched = {
                **p,
                "severity_name":  SEVERITY_NAMES.get(sev, "Unknown"),
                "severity_color": SEVERITY_COLORS.get(sev, "#aaa"),
                "severity_int":   sev,
                "start_dt":       _ts_to_dt(clock).strftime("%Y-%m-%d %H:%M:%S"),
                "r_clock_dt":     _ts_to_dt(r_clock).strftime("%Y-%m-%d %H:%M:%S") if r_clock else "—",
                "duration_str":   _duration_str(duration),
                "duration_sec":   duration,
                "resolved":       bool(r_clock),
                "host_name":      host_name,
                "group_name":     group_name,
                "trigger_desc":   trigger.get("description", p.get("name", "—")),
                "trigger_url":    trigger.get("url", ""),
                "ack_count":      len(p.get("acknowledges", [])),
            }
            out.append(enriched)
        return out

    def _enrich_events(self, events: List[Dict]) -> List[Dict]:
        """Add human-readable fields to raw event objects."""
        out = []
        for ev in events:
            sev = int(ev.get("severity", 0))
            clock = int(ev.get("clock", 0))
            value = int(ev.get("value", 0))  # 0=PROBLEM, 1=OK

            hosts = ev.get("hosts", [])
            host_name = ", ".join(h["name"] for h in hosts) if hosts else "—"

            rel = ev.get("relatedObject", {}) or {}
            trigger_desc = rel.get("description", ev.get("name", "—"))

            enriched = {
                **ev,
                "severity_name":  SEVERITY_NAMES.get(sev, "Unknown"),
                "severity_color": SEVERITY_COLORS.get(sev, "#aaa"),
                "severity_int":   sev,
                "event_dt":       _ts_to_dt(clock).strftime("%Y-%m-%d %H:%M:%S"),
                "status":         "RESOLVED" if value == 1 else "PROBLEM",
                "status_color":   "#4CAF50" if value == 1 else SEVERITY_COLORS.get(sev, "#aaa"),
                "host_name":      host_name,
                "trigger_desc":   trigger_desc,
            }
            out.append(enriched)
        return out

    # ------------------------------------------------------------------
    # Summary statistics
    # ------------------------------------------------------------------

    @staticmethod
    def build_summary(events: List[Dict]) -> Dict:
        """
        Build a severity-bucketed summary dict from enriched events.

        Returns:
            {
              "total": int,
              "problems": int,
              "recovered": int,
              "by_severity": {int: {"name": str, "count": int, "color": str}},
              "affected_hosts": int,
            }
        """
        by_sev: Dict[int, int] = defaultdict(int)
        hosts = set()
        problems = 0
        recovered = 0

        for ev in events:
            sev = ev.get("severity_int", 0)
            by_sev[sev] += 1
            for h in ev.get("hosts", []):
                hosts.add(h.get("name", ""))
            if ev.get("status") == "RESOLVED":
                recovered += 1
            else:
                problems += 1

        by_severity_out = {}
        for sev in range(6):
            by_severity_out[sev] = {
                "name":  SEVERITY_NAMES[sev],
                "color": SEVERITY_COLORS[sev],
                "count": by_sev.get(sev, 0),
            }

        return {
            "total":          len(events),
            "problems":       problems,
            "recovered":      recovered,
            "by_severity":    by_severity_out,
            "affected_hosts": len(hosts),
        }

    # ------------------------------------------------------------------
    # Top-N trigger analysis
    # ------------------------------------------------------------------

    def get_top_triggers(
        self,
        time_from: int = None,
        time_till: int = None,
        limit: int = 20,
    ) -> List[Dict]:
        """
        Return the top <limit> most-fired triggers in the window,
        sorted by fire count descending.
        """
        if time_from is None or time_till is None:
            time_from, time_till = self.window(24)

        events = self.api.get_events(
            time_from=time_from,
            time_till=time_till,
            limit=50000,
        )

        # Count by trigger id
        counts: Dict[str, int] = defaultdict(int)
        last_seen: Dict[str, int] = {}
        trigger_info: Dict[str, Dict] = {}
        host_map: Dict[str, set] = defaultdict(set)

        for ev in events:
            rel = ev.get("relatedObject") or {}
            tid = rel.get("triggerid") or ev.get("objectid", "")
            if not tid:
                continue
            counts[tid] += 1
            clock = int(ev.get("clock", 0))
            if tid not in last_seen or clock > last_seen[tid]:
                last_seen[tid] = clock
            if tid not in trigger_info:
                trigger_info[tid] = {
                    "triggerid":   tid,
                    "description": rel.get("description", "—"),
                    "priority":    int(rel.get("priority", 0)),
                }
            for h in ev.get("hosts", []):
                host_map[tid].add(h.get("name", ""))

        # Sort by count
        sorted_tids = sorted(counts, key=lambda t: counts[t], reverse=True)[:limit]

        result = []
        for rank, tid in enumerate(sorted_tids, start=1):
            sev = trigger_info[tid]["priority"]
            ls_ts = last_seen.get(tid, 0)
            result.append({
                "rank":           rank,
                "triggerid":      tid,
                "description":    trigger_info[tid]["description"],
                "severity_int":   sev,
                "severity_name":  SEVERITY_NAMES.get(sev, "Unknown"),
                "severity_color": SEVERITY_COLORS.get(sev, "#aaa"),
                "fire_count":     counts[tid],
                "last_seen_dt":   _ts_to_dt(ls_ts).strftime("%Y-%m-%d %H:%M:%S") if ls_ts else "—",
                "hosts":          sorted(host_map[tid]),
                "host_count":     len(host_map[tid]),
            })
        return result

    # ------------------------------------------------------------------
    # Public report-data builders
    # ------------------------------------------------------------------

    def collect_hourly(self) -> Dict:
        """Collect data for the Hourly Alert Summary report."""
        time_from, time_till = self.window(1)
        events = self._enrich_events(
            self.api.get_events(time_from=time_from, time_till=time_till)
        )
        return {
            "report_type":  "hourly",
            "title":        "Hourly Alert Summary",
            "period_label": "Last 1 Hour",
            "time_from":    time_from,
            "time_till":    time_till,
            "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "summary":      self.build_summary(events),
            "events":       events,
        }

    def collect_4hr(self) -> Dict:
        """Collect data for the 4-Hour Problem Summary report."""
        time_from, time_till = self.window(4)
        events = self._enrich_events(
            self.api.get_events(time_from=time_from, time_till=time_till)
        )
        problems = self._enrich_problems(
            self.api.get_problems(time_from=time_from, time_till=time_till)
        )
        return {
            "report_type":  "4hr",
            "title":        "4-Hour Problem Summary",
            "period_label": "Last 4 Hours",
            "time_from":    time_from,
            "time_till":    time_till,
            "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "summary":      self.build_summary(events),
            "events":       events,
            "problems":     problems,
        }

    def collect_8hr(self) -> Dict:
        """Collect data for the 8-Hour Problem Summary report."""
        time_from, time_till = self.window(8)
        events = self._enrich_events(
            self.api.get_events(time_from=time_from, time_till=time_till)
        )
        problems = self._enrich_problems(
            self.api.get_problems(time_from=time_from, time_till=time_till)
        )
        return {
            "report_type":  "8hr",
            "title":        "8-Hour Problem Summary",
            "period_label": "Last 8 Hours",
            "time_from":    time_from,
            "time_till":    time_till,
            "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "summary":      self.build_summary(events),
            "events":       events,
            "problems":     problems,
        }

    def collect_top20(self, window_hours: int = 24) -> Dict:
        """Collect data for the Top 20 Triggers report."""
        time_from, time_till = self.window(window_hours)
        top_triggers = self.get_top_triggers(
            time_from=time_from, time_till=time_till, limit=20
        )
        return {
            "report_type":    "top20",
            "title":          "Top 20 Triggers",
            "period_label":   f"Last {window_hours} Hours",
            "time_from":      time_from,
            "time_till":      time_till,
            "generated_at":   datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "top_triggers":   top_triggers,
            "window_hours":   window_hours,
        }
