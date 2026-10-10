#!/usr/bin/env python3
"""Seed demo reports to a running DisasterLens API.

Usage: python seed_demo.py [base_url]
Default base_url: http://127.0.0.1:8001
"""
import json
import sys
import time
import urllib.request
import urllib.error


REPORTS = [
    {
        "description": "Bagmati river overflowing near Balkhu bridge, water entering houses, 2 kids stuck on a roof, need boat urgently",
        "latitude": 27.6850,
        "longitude": 85.3150,
    },
    {
        "description": "Flood near Balkhu, river water rising fast, families on rooftops asking for rescue boats",
        "latitude": 27.6865,
        "longitude": 85.3142,
    },
    {
        "description": "बनेपामा पहिरो गएर बाटो बन्द भएको छ, गाडी जान सकेको छैन",
        "latitude": 27.6330,
        "longitude": 85.5180,
    },
    {
        "description": "Kalamati ma pahiro gayo, dui jana manche faseko cha, bato band cha, gadi haru jana sakdenan",
        "latitude": 27.6920,
        "longitude": 85.3080,
    },
    {
        "description": "Smoke and flames visible from a warehouse in Teku, fire brigade on site but spreading fast",
        "latitude": 27.6980,
        "longitude": 85.3040,
    },
    {
        "description": "Building collapsed after the earthquake in Chabahil, I can hear people shouting under the rubble, road is blocked by debris",
        "latitude": 27.7120,
        "longitude": 85.3450,
    },
    {
        "description": "A fallen tree is blocking the road near Swayambhu, cars cannot pass, need road clearing",
        "latitude": 27.7150,
        "longitude": 85.2900,
    },
    {
        "description": "Something happened near the market, not sure what, maybe check it out",
        "latitude": 27.7030,
        "longitude": 85.3120,
    },
]


def post_report(base_url: str, report: dict) -> dict:
    url = f"{base_url.rstrip('/')}/reports"
    data = json.dumps(report).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main() -> int:
    base_url = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8001"

    for i, report in enumerate(REPORTS, 1):
        try:
            result = post_report(base_url, report)
            analysis_status = result.get("report", {}).get("analysis_status", "unknown")
            print(f"[{i}/8] {analysis_status}")
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8")
            print(f"[{i}/8] HTTP {e.code}: {body}")
        except Exception as e:
            print(f"[{i}/8] ERROR: {e}")
        time.sleep(1.5)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())