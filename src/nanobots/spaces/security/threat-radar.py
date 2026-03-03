#!/usr/bin/env python3
"""
threat_radar.py - Cybersecurity threat radar nanobot

Scans three sources and produces a unified markdown report:
  1. NVD (National Vulnerability Database) - CVEs by keyword
  2. CISA KEV (Known Exploited Vulnerabilities) catalog
  3. arXiv cs.CR - Recent security research papers

Uses only Python stdlib (urllib, json, ssl). No external deps.

Usage:
    nanobot security/threat-radar <keyword> [days]

Examples:
    nanobot security/threat-radar linux 7
    nanobot security/threat-radar openssl 30

Environment:
    NANOBOT_OUTPUT   - Path to write the markdown report
    NANOBOT_RUN_ID   - Unique run identifier
"""

from __future__ import annotations

import json
import os
import ssl
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

def _make_ssl_context() -> ssl.SSLContext:
    """Create a permissive SSL context for API calls."""
    ctx = ssl.create_default_context()
    return ctx


def fetch_json(url: str, timeout: int = 30) -> dict | list | None:
    """GET a URL and parse the response as JSON."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "nanobots/0.1"})
        ctx = _make_ssl_context()
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
            data = resp.read().decode("utf-8", errors="replace")
            return json.loads(data)
    except (urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError, OSError) as exc:
        return {"_error": str(exc)}


def fetch_text(url: str, timeout: int = 30) -> str | None:
    """GET a URL and return raw text."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "nanobots/0.1"})
        ctx = _make_ssl_context()
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except Exception:
        return None


# ---------------------------------------------------------------------------
# NVD - National Vulnerability Database
# ---------------------------------------------------------------------------

def search_nvd(keyword: str, days: int = 7, max_results: int = 20) -> list[dict]:
    """
    Search NVD 2.0 API for CVEs matching a keyword.
    Returns a list of simplified CVE dicts.
    """
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=days)

    params = urllib.parse.urlencode({
        "keywordSearch": keyword,
        "pubStartDate": start.strftime("%Y-%m-%dT%H:%M:%S.000"),
        "pubEndDate": end.strftime("%Y-%m-%dT%H:%M:%S.000"),
        "resultsPerPage": str(max_results),
    })
    url = f"https://services.nvd.nist.gov/rest/json/cves/2.0?{params}"

    data = fetch_json(url, timeout=45)
    if not data or "_error" in data:
        return [{"_error": data.get("_error", "Unknown error") if data else "No response"}]

    results = []
    for item in data.get("vulnerabilities", []):
        cve = item.get("cve", {})
        cve_id = cve.get("id", "Unknown")

        # Extract description (English preferred)
        desc = ""
        for d in cve.get("descriptions", []):
            if d.get("lang") == "en":
                desc = d.get("value", "")
                break
        if not desc:
            descs = cve.get("descriptions", [])
            desc = descs[0].get("value", "") if descs else ""

        # Extract CVSS score
        score = None
        severity = ""
        metrics = cve.get("metrics", {})
        for version_key in ("cvssMetricV31", "cvssMetricV30", "cvssMetricV2"):
            metric_list = metrics.get(version_key, [])
            if metric_list:
                cvss_data = metric_list[0].get("cvssData", {})
                score = cvss_data.get("baseScore")
                severity = cvss_data.get("baseSeverity", "")
                break

        published = cve.get("published", "")[:10]

        results.append({
            "id": cve_id,
            "description": desc[:200] + ("..." if len(desc) > 200 else ""),
            "score": score,
            "severity": severity,
            "published": published,
        })

    return results


# ---------------------------------------------------------------------------
# CISA KEV - Known Exploited Vulnerabilities
# ---------------------------------------------------------------------------

def check_cisa_kev(keyword: str, max_results: int = 15) -> list[dict]:
    """
    Fetch the CISA KEV catalog and filter by keyword.
    The catalog is a single JSON file, so we download and search locally.
    """
    url = "https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json"
    data = fetch_json(url, timeout=30)

    if not data or "_error" in data:
        return [{"_error": data.get("_error", "Unknown error") if data else "No response"}]

    keyword_lower = keyword.lower()
    results = []
    for vuln in data.get("vulnerabilities", []):
        searchable = " ".join([
            vuln.get("vendorProject", ""),
            vuln.get("product", ""),
            vuln.get("vulnerabilityName", ""),
            vuln.get("shortDescription", ""),
        ]).lower()

        if keyword_lower in searchable:
            results.append({
                "cve": vuln.get("cveID", ""),
                "vendor": vuln.get("vendorProject", ""),
                "product": vuln.get("product", ""),
                "name": vuln.get("vulnerabilityName", ""),
                "date_added": vuln.get("dateAdded", ""),
                "due_date": vuln.get("dueDate", ""),
                "description": vuln.get("shortDescription", "")[:200],
            })

        if len(results) >= max_results:
            break

    return results


# ---------------------------------------------------------------------------
# arXiv cs.CR - Cryptography and Security papers
# ---------------------------------------------------------------------------

def search_arxiv(keyword: str, max_results: int = 10) -> list[dict]:
    """
    Search arXiv for recent cs.CR (Cryptography and Security) papers.
    Uses the Atom API and parses XML manually (no lxml needed).
    """
    import xml.etree.ElementTree as ET

    query = urllib.parse.quote(f"all:{keyword} AND cat:cs.CR")
    url = (
        f"http://export.arxiv.org/api/query?"
        f"search_query={query}&start=0&max_results={max_results}"
        f"&sortBy=submittedDate&sortOrder=descending"
    )

    text = fetch_text(url, timeout=30)
    if not text:
        return [{"_error": "Failed to fetch arXiv API"}]

    try:
        root = ET.fromstring(text)
    except ET.ParseError as exc:
        return [{"_error": f"XML parse error: {exc}"}]

    ns = {"atom": "http://www.w3.org/2005/Atom"}
    results = []

    for entry in root.findall("atom:entry", ns):
        title_el = entry.find("atom:title", ns)
        summary_el = entry.find("atom:summary", ns)
        published_el = entry.find("atom:published", ns)

        title = title_el.text.strip().replace("\n", " ") if title_el is not None and title_el.text else ""
        summary = summary_el.text.strip().replace("\n", " ") if summary_el is not None and summary_el.text else ""
        published = published_el.text[:10] if published_el is not None and published_el.text else ""

        # Get the paper link
        link = ""
        for link_el in entry.findall("atom:link", ns):
            if link_el.get("title") == "pdf":
                link = link_el.get("href", "")
                break
        if not link:
            for link_el in entry.findall("atom:link", ns):
                href = link_el.get("href", "")
                if "abs" in href:
                    link = href
                    break

        # Authors
        authors = []
        for author_el in entry.findall("atom:author", ns):
            name_el = author_el.find("atom:name", ns)
            if name_el is not None and name_el.text:
                authors.append(name_el.text.strip())

        results.append({
            "title": title,
            "authors": ", ".join(authors[:3]) + (" et al." if len(authors) > 3 else ""),
            "published": published,
            "summary": summary[:200] + ("..." if len(summary) > 200 else ""),
            "link": link,
        })

    return results


# ---------------------------------------------------------------------------
# Report builder
# ---------------------------------------------------------------------------

def build_report(keyword: str, days: int) -> str:
    """Assemble the full threat radar markdown report."""
    run_id = os.environ.get("NANOBOT_RUN_ID", "unknown")
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    lines: list[str] = []
    lines.append("# Threat Radar Report")
    lines.append("")
    lines.append(f"**Keyword:** `{keyword}`  ")
    lines.append(f"**Lookback:** {days} days  ")
    lines.append(f"**Generated:** {now}")
    lines.append("")

    # --- NVD CVEs ---
    lines.append("## NVD - Recent CVEs")
    lines.append("")
    nvd_results = search_nvd(keyword, days)

    if nvd_results and "_error" in nvd_results[0]:
        lines.append(f"> NVD query failed: {nvd_results[0]['_error']}")
    elif not nvd_results:
        lines.append(f"No CVEs found for `{keyword}` in the last {days} days.")
    else:
        lines.append(f"| CVE ID | Score | Severity | Published | Description |")
        lines.append(f"|--------|-------|----------|-----------|-------------|")
        for cve in nvd_results:
            score_str = f"{cve['score']}" if cve["score"] is not None else "-"
            sev = cve.get("severity", "-") or "-"
            lines.append(
                f"| {cve['id']} | {score_str} | {sev} "
                f"| {cve['published']} | {cve['description']} |"
            )
    lines.append("")

    # --- CISA KEV ---
    lines.append("## CISA - Known Exploited Vulnerabilities")
    lines.append("")
    kev_results = check_cisa_kev(keyword)

    if kev_results and "_error" in kev_results[0]:
        lines.append(f"> CISA KEV query failed: {kev_results[0]['_error']}")
    elif not kev_results:
        lines.append(f"No known exploited vulnerabilities matching `{keyword}`.")
    else:
        lines.append(f"Found **{len(kev_results)}** exploited vulnerabilities matching `{keyword}`:")
        lines.append("")
        lines.append(f"| CVE | Vendor | Product | Added | Due Date |")
        lines.append(f"|-----|--------|---------|-------|----------|")
        for kev in kev_results:
            lines.append(
                f"| {kev['cve']} | {kev['vendor']} | {kev['product']} "
                f"| {kev['date_added']} | {kev['due_date']} |"
            )
    lines.append("")

    # --- arXiv cs.CR ---
    lines.append("## arXiv cs.CR - Security Research")
    lines.append("")
    arxiv_results = search_arxiv(keyword)

    if arxiv_results and "_error" in arxiv_results[0]:
        lines.append(f"> arXiv query failed: {arxiv_results[0]['_error']}")
    elif not arxiv_results:
        lines.append(f"No recent security papers found for `{keyword}`.")
    else:
        for paper in arxiv_results:
            lines.append(f"### {paper['title']}")
            lines.append(f"")
            lines.append(f"**Authors:** {paper['authors']}  ")
            lines.append(f"**Published:** {paper['published']}  ")
            if paper["link"]:
                lines.append(f"**Link:** {paper['link']}")
            lines.append(f"")
            lines.append(f"> {paper['summary']}")
            lines.append(f"")
    lines.append("")

    # --- Footer ---
    lines.append("---")
    lines.append(f"*nanobot run `{run_id}` | security/threat-radar | {now}*")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    if len(sys.argv) < 2:
        print("Usage: nanobot security/threat-radar <keyword> [days]", file=sys.stderr)
        print("  keyword  - Search term (e.g. linux, openssl, chrome)", file=sys.stderr)
        print("  days     - Lookback period in days (default: 7)", file=sys.stderr)
        sys.exit(1)

    keyword = sys.argv[1]
    days = 7
    if len(sys.argv) > 2:
        try:
            days = int(sys.argv[2])
        except ValueError:
            print(f"Invalid days value: {sys.argv[2]}", file=sys.stderr)
            sys.exit(1)

    report = build_report(keyword, days)

    output_path = os.environ.get("NANOBOT_OUTPUT")
    if output_path:
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        Path(output_path).write_text(report)
    else:
        print(report)


if __name__ == "__main__":
    main()
