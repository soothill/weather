#!/usr/bin/env python3
"""Debug script to see the actual API response structure"""

import requests
import yaml
import json

# Load config
with open('config.yml', 'r') as f:
    config = yaml.safe_load(f)

api_key = config['met_office']['api_key']
base_url = config['met_office']['base_url']
lat = round(config['met_office']['location']['latitude'], 2)
lon = round(config['met_office']['location']['longitude'], 2)

headers = {
    'apikey': api_key,
    'Accept': 'application/json'
}

params = {
    'lat': lat,
    'lon': lon
}

url = f"{base_url}/observation-land/1/nearest"
print(f"Fetching: {url}")
print(f"Params: {params}")
print()

response = requests.get(url, headers=headers, params=params, timeout=30)
print(f"Status: {response.status_code}")
print()

if response.status_code == 200:
    data = response.json()
    print("=" * 70)
    print("FULL RESPONSE STRUCTURE:")
    print("=" * 70)
    print(json.dumps(data, indent=2))
else:
    print(f"Error: {response.text}")
