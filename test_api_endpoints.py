#!/usr/bin/env python3
"""
Met Office API Endpoint Tester
Tests various endpoint patterns to find the correct one.
"""

import requests
import yaml
import json
from datetime import datetime, timezone

# Load config
with open('config.yml', 'r') as f:
    config = yaml.safe_load(f)

api_key = config['met_office']['api_key']
base_url = config['met_office']['base_url']
lat = config['met_office']['location']['latitude']
lon = config['met_office']['location']['longitude']

headers = {
    'apikey': api_key,
    'Accept': 'application/json'
}

# Test different endpoint patterns
# First get the geohash from nearest
nearest_url = f"{base_url}/observation-land/1/nearest"
nearest_params = {'lat': round(lat, 2), 'lon': round(lon, 2)}
print("Getting nearest station info...")
resp = requests.get(nearest_url, headers=headers, params=nearest_params, timeout=10)
geohash = None
if resp.status_code == 200:
    data = resp.json()
    if data and len(data) > 0:
        geohash = data[0].get('geohash')
        print(f"Found geohash: {geohash}")
        print()

endpoints_to_test = [
    ("/observation-land/1/observations", {'geohash': geohash} if geohash else {}),
    (f"/observation-land/1/observations/{geohash}", {}) if geohash else ("/skip", {}),
    ("/observation-land/1/hourly", {'geohash': geohash} if geohash else {}),
    (f"/observation-land/1/hourly/{geohash}", {}) if geohash else ("/skip", {}),
    ("/observation-land/1/latest", {'geohash': geohash} if geohash else {}),
    ("/observation-land/1/stations", {}),
]

print("Testing Met Office API Endpoints")
print("=" * 70)
print()

for endpoint, params in endpoints_to_test:
    url = f"{base_url}{endpoint}"
    print(f"Testing: {url}")
    if params:
        print(f"Params: {params}")
    
    try:
        response = requests.get(url, headers=headers, params=params, timeout=10)
        print(f"Status: {response.status_code}")
        
        if response.status_code == 200:
            print("✓ SUCCESS!")
            print("Response preview:")
            data = response.json()
            print(json.dumps(data, indent=2)[:500])

            # If this is the main observation list endpoint, validate ordering/recency.
            # The API may return many hours and may be sorted oldest -> newest.
            if isinstance(data, list) and data and isinstance(data[0], dict) and data[0].get("datetime"):
                def parse_dt(s: str) -> datetime:
                    return datetime.fromisoformat(s.replace('Z', '+00:00'))

                dts = [parse_dt(o["datetime"]) for o in data if isinstance(o, dict) and o.get("datetime")]
                if dts:
                    oldest = min(dts)
                    newest = max(dts)
                    now = datetime.now(timezone.utc)
                    print(f"\nDatetime range: {oldest.isoformat()} -> {newest.isoformat()}")
                    print(f"Newest age (hours): {(now - newest).total_seconds()/3600:.2f}")

            print("\n" + "=" * 70)
            print(f"✓ WORKING ENDPOINT FOUND: {endpoint}")
            print("=" * 70)
            break
        elif response.status_code == 404:
            print("✗ 404 - Not Found")
        elif response.status_code == 401:
            print("✗ 401 - Authentication failed")
        elif response.status_code == 403:
            print("✗ 403 - Forbidden")
        else:
            print(f"Response: {response.text[:200]}")
    except Exception as e:
        print(f"✗ Error: {e}")
    
    print("-" * 70)
    print()

print("\nTest complete. If no working endpoint found, please check Met Office documentation.")
