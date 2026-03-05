#!/usr/bin/env python3
"""
zbx_reporter.py — Zabbix HTML Report Generator
================================================
Generates Hourly, 4-Hour, 8-Hour, and Top-20 Trigger reports
from a live Zabbix 7.0 / 8.0 server.

Outputs: HTML file, CSV file(s), or email (or all three).

Quick start
-----------
    # 1. Copy and edit the config
    cp config.ini.example config.ini
    vim config.ini

    # 2. Generate all reports and save locally
    python zbx_reporter.py --type all --format both --output-dir ./reports

    # 3. Send hourly report via email
    python zbx_reporter.py --type hourly --send-email

    # 4. Run non-interactively (e.g. from cron)
    python zbx_reporter.py --type 4hr --format html --send-email --quiet
"""

import argparse
import configparser
import logging
import os
import sys
from typing import Dict, List, Optional

from zbx_report.api import ZabbixAPI, ZabbixAPIError
from zbx_report.collector import DataCollector
from zbx_report.renderer import ReportRenderer
from zbx_report.mailer import Mailer, MailerError

# ─────────────────────────────────────────────────────────────────────────────
# Logging
# ─────────────────────────────────────────────────────────────────────────────

logger = logging.getLogger("zbx_reporter")


def _setup_logging(quiet: bool, debug: bool):
    level = logging.WARNING if quiet else (logging.DEBUG if debug else logging.INFO)
    logging.basicConfig(
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        level=level,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Config
# ─────────────────────────────────────────────────────────────────────────────

DEFAULT_CONFIG = "config.ini"


def _load_config(path: str) -> configparser.ConfigParser:
    cfg = configparser.ConfigParser(inline_comment_prefixes=(";", "#"))
    if not os.path.isfile(path):
        logger.error("Config file not found: %s", path)
        logger.error("Copy config.ini.example → config.ini and fill in your values.")
        sys.exit(1)
    cfg.read(path, encoding="utf-8")
    return cfg


def _get(cfg: configparser.ConfigParser, section: str, key: str, fallback=None):
    return cfg.get(section, key, fallback=fallback)


def _getbool(cfg: configparser.ConfigParser, section: str, key: str, fallback=False):
    return cfg.getboolean(section, key, fallback=fallback)


def _getint(cfg: configparser.ConfigParser, section: str, key: str, fallback=0):
    return cfg.getint(section, key, fallback=fallback)


# ─────────────────────────────────────────────────────────────────────────────
# Build objects from config
# ─────────────────────────────────────────────────────────────────────────────

def _build_api(cfg: configparser.ConfigParser) -> ZabbixAPI:
    url        = _get(cfg, "zabbix", "url")
    verify_ssl = _getbool(cfg, "zabbix", "verify_ssl", fallback=True)
    timeout    = _getint(cfg, "zabbix", "timeout", fallback=30)

    if not url:
        logger.error("[zabbix] url is required in config.ini")
        sys.exit(1)

    return ZabbixAPI(url=url, verify_ssl=verify_ssl, timeout=timeout)


def _login(api: ZabbixAPI, cfg: configparser.ConfigParser):
    api_token = _get(cfg, "zabbix", "api_token", fallback="")
    user      = _get(cfg, "zabbix", "user",      fallback="")
    password  = _get(cfg, "zabbix", "password",  fallback="")

    try:
        if api_token:
            logger.info("Authenticating with API token …")
            api.login(api_token=api_token)
        elif user and password:
            logger.info("Authenticating with user/password …")
            api.login(user=user, password=password)
        else:
            logger.error("Provide api_token or user+password in [zabbix] config section.")
            sys.exit(1)
        logger.info("Connected to Zabbix API v%s", api.api_version)
    except ZabbixAPIError as exc:
        logger.error("Zabbix API login failed: %s", exc)
        sys.exit(1)


def _build_mailer(cfg: configparser.ConfigParser) -> Optional[Mailer]:
    if "smtp" not in cfg:
        return None

    host      = _get(cfg, "smtp", "host",         fallback="")
    port      = _getint(cfg, "smtp", "port",       fallback=25)
    from_addr = _get(cfg, "smtp", "from",          fallback="zabbix@localhost")
    username  = _get(cfg, "smtp", "username",      fallback="")
    password  = _get(cfg, "smtp", "password",      fallback="")
    tls       = _getbool(cfg, "smtp", "tls",       fallback=False)
    starttls  = _getbool(cfg, "smtp", "starttls",  fallback=False)
    verify    = _getbool(cfg, "smtp", "verify_ssl",fallback=True)
    timeout   = _getint(cfg, "smtp", "timeout",    fallback=30)

    if not host:
        return None

    return Mailer(
        host=host,
        port=port,
        from_addr=from_addr,
        username=username or None,
        password=password or None,
        use_tls=tls,
        use_starttls=starttls,
        verify_ssl=verify,
        timeout=timeout,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Report runners
# ─────────────────────────────────────────────────────────────────────────────

REPORT_CHOICES = ["hourly", "4hr", "8hr", "top20", "all"]
FORMAT_CHOICES = ["html", "csv", "both"]


def _collect(report_type: str, collector: DataCollector, cfg: configparser.ConfigParser) -> Dict:
    top20_window = _getint(cfg, "reports", "top20_window_hours", fallback=24)
    if report_type == "hourly":
        return collector.collect_hourly()
    if report_type == "4hr":
        return collector.collect_4hr()
    if report_type == "8hr":
        return collector.collect_8hr()
    if report_type == "top20":
        return collector.collect_top20(window_hours=top20_window)
    raise ValueError(f"Unknown report type: {report_type}")


def _run_report(
    report_type: str,
    collector: DataCollector,
    renderer: ReportRenderer,
    mailer: Optional[Mailer],
    cfg: configparser.ConfigParser,
    args: argparse.Namespace,
) -> None:
    logger.info("Collecting data for: %s …", report_type)

    try:
        data = _collect(report_type, collector, cfg)
    except ZabbixAPIError as exc:
        logger.error("API error while collecting %s: %s", report_type, exc)
        return

    # summary log
    summary = data.get("summary", {})
    if summary:
        logger.info(
            "  %s — total=%d  problems=%d  recovered=%d  hosts=%d",
            report_type,
            summary.get("total", 0),
            summary.get("problems", 0),
            summary.get("recovered", 0),
            summary.get("affected_hosts", 0),
        )

    # Generate HTML
    html_body = renderer.render_html(data)

    # Generate CSVs
    csv_files = renderer.render_csv(data)

    # Save to disk
    if args.output_dir:
        saved = renderer.save(data, output_dir=args.output_dir, fmt=args.format)
        if "html" in saved:
            logger.info("  HTML saved: %s", saved["html"])
        for p in saved.get("csv", []):
            logger.info("  CSV  saved: %s", p)

    # Send email (triggered by --send-email flag OR send_email=true in config)
    if args.send_email:
        if mailer is None:
            logger.error(
                "Email requested but [smtp] section is missing or incomplete in config.ini.\n"
                "  Ensure [smtp] host, port, from, and credentials are set."
            )
            return

        recipients = _get(cfg, "reports", "email_to", fallback="").strip()
        if not recipients:
            logger.error(
                "No recipients found. Set 'email_to' under [reports] in config.ini.\n"
                "  Example:  email_to = ops@example.com, mgr@example.com"
            )
            return

        subject_prefix = _get(cfg, "reports", "subject_prefix", fallback="[Zabbix]")
        attach_csv     = _getbool(cfg, "reports", "attach_csv", fallback=True)
        attachments    = csv_files if attach_csv else None
        to_list        = [r.strip() for r in recipients.split(",") if r.strip()]

        logger.info("  Sending email → %s", ", ".join(to_list))
        try:
            mailer.send_report(
                report_data=data,
                html_body=html_body,
                csv_files=attachments,
                to=to_list,
                subject_prefix=subject_prefix,
            )
            logger.info("  Email sent successfully to %d recipient(s).", len(to_list))
        except MailerError as exc:
            logger.error("  Email failed: %s", exc)
            logger.error(
                "  Check [smtp] settings in config.ini:\n"
                "    host=%s  port=%s  tls=%s  starttls=%s  username=%s",
                _get(cfg, "smtp", "host", fallback="?"),
                _get(cfg, "smtp", "port", fallback="?"),
                _get(cfg, "smtp", "tls",      fallback="?"),
                _get(cfg, "smtp", "starttls", fallback="?"),
                _get(cfg, "smtp", "username", fallback="(none)"),
            )


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="zbx_reporter",
        description=(
            "Zabbix HTML/CSV Report Generator\n"
            "Supports Zabbix 7.0 and 8.0\n\n"
            "Report types:\n"
            "  hourly  — Last 1-hour alert summary with event detail\n"
            "  4hr     — Last 4-hour problem summary\n"
            "  8hr     — Last 8-hour problem summary\n"
            "  top20   — Top 20 most-fired triggers (configurable window)\n"
            "  all     — Run all four reports\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    p.add_argument(
        "--type", "-t",
        choices=REPORT_CHOICES,
        default="all",
        help="Report type to generate (default: all)",
    )
    p.add_argument(
        "--format", "-f",
        choices=FORMAT_CHOICES,
        default="both",
        dest="format",
        help="Output format: html | csv | both (default: both)",
    )
    p.add_argument(
        "--output-dir", "-o",
        default="./reports",
        help="Directory to save output files (default: ./reports)",
    )
    p.add_argument(
        "--send-email", "-e",
        action="store_true",
        default=False,
        help="Send report(s) via email (requires [smtp] config)",
    )
    p.add_argument(
        "--config", "-c",
        default=DEFAULT_CONFIG,
        help=f"Path to config file (default: {DEFAULT_CONFIG})",
    )
    p.add_argument(
        "--no-save",
        action="store_true",
        default=False,
        help="Do not save files to disk (useful with --send-email only)",
    )
    p.add_argument(
        "--quiet", "-q",
        action="store_true",
        default=False,
        help="Suppress informational output (warnings and errors only)",
    )
    p.add_argument(
        "--debug",
        action="store_true",
        default=False,
        help="Enable debug logging",
    )

    args = p.parse_args()

    # If --no-save, clear output_dir so renderer.save() is not called
    if args.no_save:
        args.output_dir = None

    return args


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────

def main():
    args = _parse_args()
    _setup_logging(quiet=args.quiet, debug=args.debug)

    cfg = _load_config(args.config)

    # Build API client and authenticate
    api = _build_api(cfg)
    _login(api, cfg)

    # Build collector and renderer
    collector = DataCollector(api)
    renderer  = ReportRenderer(server_url=_get(cfg, "zabbix", "url", fallback=""))
    mailer    = _build_mailer(cfg)

    # Allow send_email to be enabled via config without needing the CLI flag
    if not args.send_email:
        args.send_email = _getbool(cfg, "reports", "send_email", fallback=False)

    # Determine which report types to run
    if args.type == "all":
        report_types = ["hourly", "4hr", "8hr", "top20"]
    else:
        report_types = [args.type]

    logger.info("Zabbix HTML Reporter starting — reports: %s", report_types)

    # Run each report
    for rtype in report_types:
        _run_report(rtype, collector, renderer, mailer, cfg, args)

    # Logout (no-op for API tokens)
    api.logout()

    logger.info("Done.")


if __name__ == "__main__":
    main()
