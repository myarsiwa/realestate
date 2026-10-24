"""
Pulls active single-family rental listings from the RentCast API for defined
regions (radius search), and appends a timestamped snapshot to a running
history file per region — for tracking asking rents over time.

Quota note: each region = 1 API request, regardless of result count (up to
500 listings/call). Run this on whatever cadence keeps you within your
RentCast monthly quota (50/month on the free tier).

Auth: reads the API key from the RENTCAST_API_KEY environment variable.
Set it yourself before running, e.g. (PowerShell):
    $env:RENTCAST_API_KEY = "your-key-here"

Usage:
    python rentcast_tracker.py
"""
import csv
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.parse import urlencode
from urllib.error import HTTPError

API_BASE = "https://api.rentcast.io/v1/listings/rental/long-term"
OUT_DIR = Path(__file__).parent / "rentcast_data"

# Each region = 1 API request per run.
REGIONS = [
    {
        "name": "Grand_Prairie_TX",
        "city": "Grand Prairie",
        "state": "TX",
    },
    {
        "name": "Duncanville_TX",
        "city": "Duncanville",
        "state": "TX",
    },
    {
        "name": "South_Charlotte_NC_28277",
        "zipCode": "28277",     # Ballantyne, exact zip match
    },
]

COMMON_PARAMS = {
    "propertyType": "Single Family",
    "status": "Active",
    "limit": 500,
}


LOCATION_KEYS = ("latitude", "longitude", "radius", "zipCode", "city", "state", "address")


def fetch_region(api_key: str, region: dict) -> dict:
    params = dict(COMMON_PARAMS)
    for key in LOCATION_KEYS:
        if key in region:
            params[key] = region[key]

    url = f"{API_BASE}?{urlencode(params)}"
    req = Request(url, headers={"X-Api-Key": api_key, "Accept": "application/json"})
    try:
        with urlopen(req, timeout=30) as resp:
            body = resp.read().decode("utf-8")
            return {"ok": True, "status": resp.status, "data": json.loads(body)}
    except HTTPError as e:
        return {"ok": False, "status": e.code, "data": e.read().decode("utf-8", errors="replace")}


def flatten_listing(listing: dict, region_name: str, snapshot_date: str) -> dict:
    return {
        "snapshot_date": snapshot_date,
        "region": region_name,
        "id": listing.get("id"),
        "address": listing.get("formattedAddress") or listing.get("addressLine1"),
        "city": listing.get("city"),
        "state": listing.get("state"),
        "zipCode": listing.get("zipCode"),
        "latitude": listing.get("latitude"),
        "longitude": listing.get("longitude"),
        "price": listing.get("price"),
        "bedrooms": listing.get("bedrooms"),
        "bathrooms": listing.get("bathrooms"),
        "squareFootage": listing.get("squareFootage"),
        "yearBuilt": listing.get("yearBuilt"),
        "listedDate": listing.get("listedDate"),
        "daysOnMarket": listing.get("daysOnMarket"),
        "status": listing.get("status"),
        "listingUrl": listing.get("listingUrl") or listing.get("url"),
    }


def main():
    api_key = os.environ.get("RENTCAST_API_KEY")
    if not api_key:
        print("ERROR: RENTCAST_API_KEY environment variable is not set.", file=sys.stderr)
        sys.exit(1)

    OUT_DIR.mkdir(exist_ok=True)
    snapshot_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # Optional CLI args: names (or substrings) of regions to run, to avoid
    # spending quota on regions you don't want to re-pull this run.
    filters = [a.lower() for a in sys.argv[1:]]
    regions_to_run = [
        r for r in REGIONS
        if not filters or any(f in r["name"].lower() for f in filters)
    ]
    if not regions_to_run:
        print(f"No regions matched filters {filters}. Available: {[r['name'] for r in REGIONS]}")
        sys.exit(1)

    for region in regions_to_run:
        location_desc = ", ".join(f"{k}={region[k]}" for k in LOCATION_KEYS if k in region)
        print(f"Fetching {region['name']} ({location_desc})...")
        result = fetch_region(api_key, region)

        if not result["ok"]:
            print(f"  FAILED: status={result['status']} body={result['data'][:300]}")
            continue

        listings = result["data"]
        if isinstance(listings, dict):
            listings = listings.get("listings", listings.get("data", []))

        print(f"  Retrieved {len(listings)} listings")

        city_filter = region.get("city_filter")
        if city_filter:
            allowed = {c.lower() for c in city_filter}
            listings = [l for l in listings if (l.get("city") or "").lower() in allowed]
            print(f"  {len(listings)} match city filter {city_filter}")

        rows = [flatten_listing(l, region["name"], snapshot_date) for l in listings]

        # Append to a running per-region history CSV
        history_file = OUT_DIR / f"{region['name']}_history.csv"
        file_exists = history_file.exists()
        with open(history_file, "a", newline="", encoding="utf-8") as f:
            fieldnames = list(rows[0].keys()) if rows else [
                "snapshot_date", "region", "id", "address", "city", "state", "zipCode",
                "price", "bedrooms", "bathrooms", "squareFootage", "yearBuilt",
                "listedDate", "daysOnMarket", "status", "listingUrl",
            ]
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            if not file_exists:
                writer.writeheader()
            writer.writerows(rows)

        # Also keep a raw JSON snapshot for this run
        raw_file = OUT_DIR / f"{region['name']}_{snapshot_date}.json"
        with open(raw_file, "w", encoding="utf-8") as f:
            json.dump(listings, f, indent=2)

        print(f"  Appended to {history_file.name}, raw snapshot saved to {raw_file.name}")

    print("Done.")


if __name__ == "__main__":
    main()
