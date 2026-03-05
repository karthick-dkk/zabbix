"""
Report Renderer
Generates HTML and CSV outputs from collected Zabbix data.

HTML output:
  - Full standalone HTML document with embedded CSS
  - Severity-colour-coded rows and summary cards
  - Responsive tables

CSV output:
  - UTF-8 with BOM (Excel-compatible)
  - One CSV per logical section (events, problems, top-triggers)
"""

import csv
import io
import os
from datetime import datetime
from typing import Dict, List, Optional


# ─────────────────────────────────────────────────────────────────────────────
# CSS / HTML helpers
# ─────────────────────────────────────────────────────────────────────────────

_CSS = """
/* ── Reset & base ── */
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
body {
  font-family: 'Segoe UI', Arial, sans-serif;
  font-size: 13px;
  background: #f4f6f9;
  color: #333;
}
a { color: #1a73e8; text-decoration: none; }
a:hover { text-decoration: underline; }

/* ── Layout ── */
.page-wrapper { max-width: 1400px; margin: 0 auto; padding: 20px; }

/* ── Header ── */
.report-header {
  background: linear-gradient(135deg, #1f2d40 0%, #2c3e50 100%);
  color: #fff;
  padding: 24px 32px;
  border-radius: 8px;
  margin-bottom: 20px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 12px;
}
.report-header h1 { font-size: 22px; font-weight: 600; letter-spacing: .5px; }
.report-header .zbx-logo {
  font-size: 28px;
  font-weight: 800;
  color: #d40000;
  letter-spacing: -1px;
}
.report-meta { font-size: 12px; color: #aac; line-height: 1.8; }
.report-meta span::before { content: "▸ "; color: #556; }

/* ── Summary cards ── */
.cards-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
  gap: 12px;
  margin-bottom: 24px;
}
.card {
  border-radius: 8px;
  padding: 16px;
  color: #fff;
  text-align: center;
  box-shadow: 0 2px 8px rgba(0,0,0,.15);
}
.card .card-count { font-size: 32px; font-weight: 700; line-height: 1; }
.card .card-label { font-size: 11px; opacity: .9; margin-top: 6px; text-transform: uppercase; letter-spacing: .5px; }
.card-total      { background: #1f2d40; }
.card-problems   { background: #c0392b; }
.card-recovered  { background: #27ae60; }
.card-hosts      { background: #2980b9; }

/* ── Severity cards row ── */
.sev-cards {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 24px;
}
.sev-card {
  border-radius: 6px;
  padding: 10px 18px;
  color: #fff;
  text-align: center;
  min-width: 110px;
  box-shadow: 0 2px 6px rgba(0,0,0,.12);
}
.sev-card .sev-count { font-size: 24px; font-weight: 700; }
.sev-card .sev-name  { font-size: 10px; opacity: .9; margin-top: 3px; text-transform: uppercase; letter-spacing: .4px; }

/* ── Section ── */
.section {
  background: #fff;
  border-radius: 8px;
  box-shadow: 0 2px 8px rgba(0,0,0,.08);
  margin-bottom: 24px;
  overflow: hidden;
}
.section-title {
  background: #2c3e50;
  color: #fff;
  padding: 12px 20px;
  font-size: 14px;
  font-weight: 600;
  display: flex;
  align-items: center;
  gap: 8px;
}
.section-title .badge {
  background: rgba(255,255,255,.15);
  border-radius: 12px;
  padding: 2px 10px;
  font-size: 11px;
}

/* ── Table ── */
.tbl-wrap { overflow-x: auto; }
table {
  width: 100%;
  border-collapse: collapse;
  font-size: 12px;
}
th {
  background: #ecf0f1;
  color: #555;
  padding: 10px 14px;
  text-align: left;
  font-weight: 600;
  white-space: nowrap;
  border-bottom: 2px solid #ddd;
  position: sticky;
  top: 0;
}
td {
  padding: 9px 14px;
  border-bottom: 1px solid #f0f0f0;
  vertical-align: middle;
}
tr:last-child td { border-bottom: none; }
tr:hover td { background: #f8fafd; }
tr.resolved td { opacity: .72; }

/* ── Severity badge ── */
.sev-badge {
  display: inline-block;
  border-radius: 4px;
  padding: 2px 8px;
  font-size: 11px;
  font-weight: 600;
  color: #fff;
  white-space: nowrap;
}

/* ── Status badge ── */
.status-badge {
  display: inline-block;
  border-radius: 4px;
  padding: 2px 8px;
  font-size: 11px;
  font-weight: 600;
  color: #fff;
  white-space: nowrap;
}

/* ── Rank ── */
.rank {
  font-size: 16px;
  font-weight: 700;
  color: #999;
}
.rank-1, .rank-2, .rank-3 { color: #e67e22; }
.rank-1::before { content: "🥇 "; }
.rank-2::before { content: "🥈 "; }
.rank-3::before { content: "🥉 "; }

/* ── Progress bar (fire count) ── */
.bar-cell { min-width: 120px; }
.bar-bg {
  background: #eee;
  border-radius: 4px;
  height: 8px;
  overflow: hidden;
}
.bar-fill {
  height: 100%;
  border-radius: 4px;
  background: linear-gradient(90deg, #e74c3c, #c0392b);
  transition: width .3s;
}

/* ── Hosts pill list ── */
.host-list { display: flex; flex-wrap: wrap; gap: 4px; }
.host-pill {
  background: #e8f4fd;
  color: #1a6fa8;
  border-radius: 12px;
  padding: 2px 8px;
  font-size: 10px;
  white-space: nowrap;
}

/* ── Footer ── */
.footer {
  text-align: center;
  color: #aaa;
  font-size: 11px;
  margin-top: 12px;
  padding: 16px;
}

/* ── Empty state ── */
.empty-state {
  padding: 40px;
  text-align: center;
  color: #aaa;
  font-size: 14px;
}

/* ── Print ── */
@media print {
  body { background: #fff; }
  .section { box-shadow: none; border: 1px solid #ccc; }
}
"""

# ─────────────────────────────────────────────────────────────────────────────
# HTML generation helpers
# ─────────────────────────────────────────────────────────────────────────────

def _h(text: str) -> str:
    """HTML-escape a string."""
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _sev_badge(sev_name: str, color: str) -> str:
    return f'<span class="sev-badge" style="background:{color}">{_h(sev_name)}</span>'


def _status_badge(status: str, color: str) -> str:
    return f'<span class="status-badge" style="background:{color}">{_h(status)}</span>'


def _cards_html(summary: Dict) -> str:
    s = summary
    cards = (
        f'<div class="cards-grid">'
        f'  <div class="card card-total">'
        f'    <div class="card-count">{s["total"]}</div>'
        f'    <div class="card-label">Total Events</div></div>'
        f'  <div class="card card-problems">'
        f'    <div class="card-count">{s["problems"]}</div>'
        f'    <div class="card-label">Problems</div></div>'
        f'  <div class="card card-recovered">'
        f'    <div class="card-count">{s["recovered"]}</div>'
        f'    <div class="card-label">Recovered</div></div>'
        f'  <div class="card card-hosts">'
        f'    <div class="card-count">{s["affected_hosts"]}</div>'
        f'    <div class="card-label">Hosts Affected</div></div>'
        f'</div>'
    )

    sev_cards = '<div class="sev-cards">'
    for sev_int, info in s["by_severity"].items():
        if info["count"] == 0:
            continue
        sev_cards += (
            f'<div class="sev-card" style="background:{info["color"]}">'
            f'  <div class="sev-count">{info["count"]}</div>'
            f'  <div class="sev-name">{_h(info["name"])}</div>'
            f'</div>'
        )
    sev_cards += "</div>"

    return cards + sev_cards


def _events_table_html(events: List[Dict], show_status: bool = True) -> str:
    if not events:
        return '<div class="empty-state">No events in this period.</div>'

    rows = []
    for ev in events:
        resolved_cls = ' class="resolved"' if ev.get("status") == "RESOLVED" else ""
        rows.append(
            f"<tr{resolved_cls}>"
            f"<td>{_h(ev['event_dt'])}</td>"
            f"<td>{_sev_badge(ev['severity_name'], ev['severity_color'])}</td>"
            f"<td>{_h(ev['host_name'])}</td>"
            f"<td>{_h(ev['trigger_desc'])}</td>"
            f"<td>{_status_badge(ev['status'], ev['status_color'])}</td>"
            f"</tr>"
        )

    return (
        '<div class="tbl-wrap"><table>'
        "<thead><tr>"
        "<th>Time</th><th>Severity</th><th>Host</th>"
        "<th>Problem / Description</th><th>Status</th>"
        "</tr></thead>"
        "<tbody>" + "\n".join(rows) + "</tbody>"
        "</table></div>"
    )


def _problems_table_html(problems: List[Dict]) -> str:
    if not problems:
        return '<div class="empty-state">No open problems in this period.</div>'

    rows = []
    for p in problems:
        ack_icon = "✔" if p.get("ack_count", 0) > 0 else "—"
        resolved_cls = ' class="resolved"' if p.get("resolved") else ""
        rows.append(
            f"<tr{resolved_cls}>"
            f"<td>{_h(p['start_dt'])}</td>"
            f"<td>{_sev_badge(p['severity_name'], p['severity_color'])}</td>"
            f"<td>{_h(p['host_name'])}</td>"
            f"<td>{_h(p['group_name'])}</td>"
            f"<td>{_h(p['trigger_desc'])}</td>"
            f"<td>{_h(p['duration_str'])}</td>"
            f"<td>{_h(p['r_clock_dt'])}</td>"
            f"<td style='text-align:center'>{ack_icon}</td>"
            f"</tr>"
        )

    return (
        '<div class="tbl-wrap"><table>'
        "<thead><tr>"
        "<th>Start</th><th>Severity</th><th>Host</th><th>Group</th>"
        "<th>Problem</th><th>Duration</th><th>Resolved At</th><th>ACK</th>"
        "</tr></thead>"
        "<tbody>" + "\n".join(rows) + "</tbody>"
        "</table></div>"
    )


def _top_triggers_table_html(triggers: List[Dict]) -> str:
    if not triggers:
        return '<div class="empty-state">No trigger data available.</div>'

    max_count = triggers[0]["fire_count"] if triggers else 1

    rows = []
    for t in triggers:
        pct = int(t["fire_count"] / max(max_count, 1) * 100)
        rank_cls = f'rank rank-{t["rank"]}' if t["rank"] <= 3 else "rank"
        host_pills = "".join(
            f'<span class="host-pill">{_h(h)}</span>' for h in t["hosts"][:10]
        )
        more = f'+{len(t["hosts"]) - 10} more' if len(t["hosts"]) > 10 else ""
        host_cell = f'<div class="host-list">{host_pills}'
        if more:
            host_cell += f'<span class="host-pill" style="background:#ddd;color:#555">{more}</span>'
        host_cell += "</div>"

        rows.append(
            f"<tr>"
            f'<td class="{rank_cls}">{t["rank"]}</td>'
            f"<td>{_sev_badge(t['severity_name'], t['severity_color'])}</td>"
            f"<td>{_h(t['description'])}</td>"
            f'<td style="text-align:center;font-weight:700;color:#c0392b">{t["fire_count"]}</td>'
            f'<td class="bar-cell">'
            f'  <div class="bar-bg"><div class="bar-fill" style="width:{pct}%"></div></div>'
            f"</td>"
            f"<td>{_h(t['last_seen_dt'])}</td>"
            f"<td>{host_cell}</td>"
            f"</tr>"
        )

    return (
        '<div class="tbl-wrap"><table>'
        "<thead><tr>"
        "<th>#</th><th>Severity</th><th>Trigger</th>"
        "<th>Fires</th><th>Frequency</th><th>Last Seen</th><th>Hosts</th>"
        "</tr></thead>"
        "<tbody>" + "\n".join(rows) + "</tbody>"
        "</table></div>"
    )


def _section(title: str, count: int, body_html: str) -> str:
    return (
        '<div class="section">'
        f'<div class="section-title">{_h(title)}'
        f' <span class="badge">{count}</span></div>'
        f"{body_html}"
        "</div>"
    )


def _html_page(title: str, body: str, meta: Dict) -> str:
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{_h(title)}</title>
  <style>{_CSS}</style>
</head>
<body>
<div class="page-wrapper">

  <div class="report-header">
    <div>
      <div class="zbx-logo">ZABBIX</div>
      <h1>{_h(title)}</h1>
    </div>
    <div class="report-meta">
      <div><span>Period: {_h(meta.get('period_label', ''))}</span></div>
      <div><span>Generated: {_h(meta.get('generated_at', ''))}</span></div>
      <div><span>Server: {_h(meta.get('server', 'N/A'))}</span></div>
    </div>
  </div>

  {body}

  <div class="footer">
    Zabbix HTML Reporter &mdash; Generated at {_h(meta.get('generated_at', ''))}
    &mdash; Zabbix 7.0 / 8.0 compatible
  </div>
</div>
</body>
</html>"""


# ─────────────────────────────────────────────────────────────────────────────
# Public renderer
# ─────────────────────────────────────────────────────────────────────────────

class ReportRenderer:
    """
    Renders collected data into HTML strings and CSV bytes.

    Usage:
        renderer = ReportRenderer(server_url="http://zabbix")
        html = renderer.render_html(data)
        csvs = renderer.render_csv(data)   # dict of {filename: bytes}
    """

    def __init__(self, server_url: str = ""):
        self.server_url = server_url.rstrip("/")

    # ── HTML ──────────────────────────────────────────────────────────────────

    def render_html(self, data: Dict) -> str:
        rtype = data.get("report_type", "")
        meta = {
            "period_label": data.get("period_label", ""),
            "generated_at": data.get("generated_at", ""),
            "server":       self.server_url,
        }

        if rtype == "hourly":
            body = self._body_events_only(data)
        elif rtype in ("4hr", "8hr"):
            body = self._body_full(data)
        elif rtype == "top20":
            body = self._body_top20(data)
        else:
            body = "<p>Unknown report type.</p>"

        return _html_page(data.get("title", "Zabbix Report"), body, meta)

    def _body_events_only(self, data: Dict) -> str:
        summary = data.get("summary", {})
        events  = data.get("events", [])
        parts   = [_cards_html(summary)]

        parts.append(_section(
            "Alert Detail",
            len(events),
            _events_table_html(events),
        ))
        return "\n".join(parts)

    def _body_full(self, data: Dict) -> str:
        summary  = data.get("summary", {})
        events   = data.get("events", [])
        problems = data.get("problems", [])
        parts    = [_cards_html(summary)]

        parts.append(_section(
            "Event Timeline",
            len(events),
            _events_table_html(events),
        ))
        parts.append(_section(
            "Open / Recent Problems",
            len(problems),
            _problems_table_html(problems),
        ))
        return "\n".join(parts)

    def _body_top20(self, data: Dict) -> str:
        triggers = data.get("top_triggers", [])
        return _section(
            f'Top 20 Triggers — Last {data.get("window_hours", 24)} Hours',
            len(triggers),
            _top_triggers_table_html(triggers),
        )

    # ── CSV ───────────────────────────────────────────────────────────────────

    def render_csv(self, data: Dict) -> Dict[str, bytes]:
        """
        Returns a dict mapping filename → CSV bytes (UTF-8 with BOM).
        Multiple CSVs may be returned for rich report types.
        """
        rtype = data.get("report_type", "unknown")
        result: Dict[str, bytes] = {}

        if rtype == "hourly":
            result[f"hourly_events.csv"] = self._csv_events(data.get("events", []))

        elif rtype in ("4hr", "8hr"):
            label = rtype
            result[f"{label}_events.csv"]   = self._csv_events(data.get("events", []))
            result[f"{label}_problems.csv"] = self._csv_problems(data.get("problems", []))

        elif rtype == "top20":
            result["top20_triggers.csv"] = self._csv_top_triggers(data.get("top_triggers", []))

        return result

    # ── CSV helpers ───────────────────────────────────────────────────────────

    @staticmethod
    def _csv_bytes(rows: List[List], headers: List[str]) -> bytes:
        buf = io.StringIO()
        buf.write("\ufeff")  # UTF-8 BOM for Excel compatibility
        w = csv.writer(buf, lineterminator="\r\n")
        w.writerow(headers)
        w.writerows(rows)
        return buf.getvalue().encode("utf-8")

    def _csv_events(self, events: List[Dict]) -> bytes:
        headers = [
            "Time", "Severity", "Host", "Problem / Description", "Status",
        ]
        rows = [
            [
                ev.get("event_dt", ""),
                ev.get("severity_name", ""),
                ev.get("host_name", ""),
                ev.get("trigger_desc", ""),
                ev.get("status", ""),
            ]
            for ev in events
        ]
        return self._csv_bytes(rows, headers)

    def _csv_problems(self, problems: List[Dict]) -> bytes:
        headers = [
            "Start Time", "Severity", "Host", "Group", "Problem",
            "Duration", "Resolved At", "Acknowledged",
        ]
        rows = [
            [
                p.get("start_dt", ""),
                p.get("severity_name", ""),
                p.get("host_name", ""),
                p.get("group_name", ""),
                p.get("trigger_desc", ""),
                p.get("duration_str", ""),
                p.get("r_clock_dt", ""),
                "Yes" if p.get("ack_count", 0) > 0 else "No",
            ]
            for p in problems
        ]
        return self._csv_bytes(rows, headers)

    def _csv_top_triggers(self, triggers: List[Dict]) -> bytes:
        headers = [
            "Rank", "Severity", "Trigger", "Fire Count",
            "Last Seen", "Host Count", "Hosts",
        ]
        rows = [
            [
                t.get("rank", ""),
                t.get("severity_name", ""),
                t.get("description", ""),
                t.get("fire_count", ""),
                t.get("last_seen_dt", ""),
                t.get("host_count", ""),
                "; ".join(t.get("hosts", [])),
            ]
            for t in triggers
        ]
        return self._csv_bytes(rows, headers)

    # ── Save helpers ──────────────────────────────────────────────────────────

    def save(
        self,
        data: Dict,
        output_dir: str = ".",
        fmt: str = "both",
    ) -> Dict[str, str]:
        """
        Save HTML and/or CSV files to output_dir.

        Parameters
        ----------
        data       : collected report data dict
        output_dir : directory to write files into
        fmt        : "html" | "csv" | "both"

        Returns
        -------
        dict of { "html": path, "csv": [paths...] }
        """
        os.makedirs(output_dir, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        rtype = data.get("report_type", "report")
        saved: Dict = {}

        if fmt in ("html", "both"):
            html_path = os.path.join(output_dir, f"{rtype}_{ts}.html")
            with open(html_path, "w", encoding="utf-8") as f:
                f.write(self.render_html(data))
            saved["html"] = html_path

        if fmt in ("csv", "both"):
            csv_files = self.render_csv(data)
            saved["csv"] = []
            for fname, content in csv_files.items():
                base, ext = os.path.splitext(fname)
                csv_path = os.path.join(output_dir, f"{base}_{ts}{ext}")
                with open(csv_path, "wb") as f:
                    f.write(content)
                saved["csv"].append(csv_path)

        return saved
