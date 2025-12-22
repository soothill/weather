#!/usr/bin/env python3
"""
Weather Data Collector
Fetches weather data from Met Office DataHub and stores it in InfluxDB v2.
Falls back to local file cache when InfluxDB is unavailable.

Copyright (c) 2025 Darren Soothill
Email: darren [at] soothill [dot] com
All rights reserved.
"""

import sys
import time
import json
import logging
import tempfile
import shutil
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from pathlib import Path

import yaml
import requests
from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS
from influxdb_client.client.exceptions import InfluxDBError

# Constants for security
MAX_CACHE_SIZE_MB = 10  # Maximum cache file size
MAX_CACHE_ENTRIES = 1000  # Maximum number of cached entries
MAX_JSON_SIZE_MB = 50  # Maximum JSON response size


class Config:
    """Configuration loader and validator"""
    
    def __init__(self, config_path: str = "config.yml"):
        self.config_path = config_path
        self.config = self._load_config()
        self._validate_config()
    
    def _load_config(self) -> Dict[str, Any]:
        """Load configuration from YAML file"""
        try:
            config_path = Path(self.config_path)
            
            # Security: Check file permissions (should not be world-readable)
            if config_path.exists():
                stat_info = config_path.stat()
                if stat_info.st_mode & 0o004:  # World readable
                    logging.warning(f"Config file {self.config_path} is world-readable! "
                                   "Run: chmod 600 {self.config_path}")
            
            with open(self.config_path, 'r') as f:
                config = yaml.safe_load(f)
            
            # Security: Validate API key is not placeholder
            api_key = config.get('met_office', {}).get('api_key', '')
            if 'YOUR_' in api_key or 'HERE' in api_key:
                logging.error("API key appears to be a placeholder. Please configure your actual API key.")
                sys.exit(1)
            
            return config
            
        except FileNotFoundError:
            logging.error(f"Configuration file not found: {self.config_path}")
            logging.error("Please copy config.sample.yml to config.yml and configure it")
            sys.exit(1)
        except yaml.YAMLError as e:
            logging.error(f"Error parsing configuration file: {e}")
            sys.exit(1)
    
    def _validate_config(self):
        """Validate required configuration fields"""
        required_fields = {
            'met_office': ['api_key', 'base_url', 'location', 'timeout', 'retry'],
            'influxdb': ['url', 'org', 'bucket', 'token', 'timeout'],
            'cache': ['file_path'],
            'logging': ['level']
        }
        
        for section, fields in required_fields.items():
            if section not in self.config:
                logging.error(f"Missing configuration section: {section}")
                sys.exit(1)
            
            for field in fields:
                if field not in self.config[section]:
                    logging.error(f"Missing configuration field: {section}.{field}")
                    sys.exit(1)
    
    def get(self, *keys):
        """Get nested configuration value"""
        value = self.config
        for key in keys:
            value = value.get(key)
            if value is None:
                return None
        return value


class RetryableHTTPClient:
    """HTTP client with exponential backoff retry logic"""
    
    def __init__(self, max_attempts: int, initial_backoff: float, 
                 max_backoff: float, max_total_time: float, timeout: int):
        self.max_attempts = max_attempts
        self.initial_backoff = initial_backoff
        self.max_backoff = max_backoff
        self.max_total_time = max_total_time
        self.timeout = timeout
    
    def get(self, url: str, headers: Optional[Dict] = None, 
            params: Optional[Dict] = None) -> Optional[requests.Response]:
        """Perform GET request with exponential backoff retry"""
        
        attempt = 0
        backoff = self.initial_backoff
        start_time = time.time()
        
        while attempt < self.max_attempts:
            try:
                logging.info(f"Attempting request (attempt {attempt + 1}/{self.max_attempts}): {url}")
                response = requests.get(
                    url, 
                    headers=headers, 
                    params=params, 
                    timeout=self.timeout
                )
                
                # Check for specific HTTP errors
                if response.status_code == 401:
                    logging.error("Authentication failed (401). Check your API key.")
                    return None
                elif response.status_code == 403:
                    logging.error("Access forbidden (403). Check your API permissions.")
                    return None
                elif 400 <= response.status_code < 500:
                    logging.error(f"Client error ({response.status_code}): {response.text}")
                    return None
                
                # Success or retryable error
                response.raise_for_status()
                logging.info(f"Request successful (status {response.status_code})")
                return response
                
            except requests.exceptions.Timeout:
                logging.warning(f"Request timeout after {self.timeout}s")
            except requests.exceptions.ConnectionError as e:
                logging.warning(f"Connection error: {e}")
            except requests.exceptions.HTTPError as e:
                if e.response.status_code >= 500:
                    logging.warning(f"Server error ({e.response.status_code}): Retrying...")
                else:
                    logging.error(f"HTTP error: {e}")
                    return None
            except Exception as e:
                logging.error(f"Unexpected error: {e}")
                return None
            
            attempt += 1
            
            # Calculate next backoff
            if attempt < self.max_attempts:
                elapsed = time.time() - start_time
                next_backoff = min(backoff, self.max_backoff)
                
                # Check if we have time for another retry
                if elapsed + next_backoff > self.max_total_time:
                    logging.error(f"Max total retry time ({self.max_total_time}s) would be exceeded. Aborting.")
                    return None
                
                logging.info(f"Retrying in {next_backoff}s...")
                time.sleep(next_backoff)
                backoff *= 2  # Double for next iteration
        
        logging.error(f"All {self.max_attempts} attempts failed")
        return None


class MetOfficeClient:
    """Client for Met Office DataHub API"""
    
    def __init__(self, config: Config):
        self.config = config
        self.api_key = config.get('met_office', 'api_key')
        self.base_url = config.get('met_office', 'base_url')
        self.location = config.get('met_office', 'location')
        
        retry_config = config.get('met_office', 'retry')
        self.http_client = RetryableHTTPClient(
            max_attempts=retry_config['max_attempts'],
            initial_backoff=retry_config['initial_backoff'],
            max_backoff=retry_config['max_backoff'],
            max_total_time=retry_config['max_total_time'],
            timeout=config.get('met_office', 'timeout')
        )
    
    def fetch_weather_data(self) -> Optional[Dict[str, Any]]:
        """Fetch weather observations from Met Office API (two-step process)"""
        
        # Step 1: Get geohash for the location
        # API requires coordinates with at most 2 decimal places
        lat = round(self.location['latitude'], 2)
        lon = round(self.location['longitude'], 2)
        
        nearest_url = f"{self.base_url}/observation-land/1/nearest"
        headers = {
            'apikey': self.api_key,
            'Accept': 'application/json'
        }
        params = {
            'lat': lat,
            'lon': lon
        }
        
        logging.info("Step 1: Getting geohash for location...")
        response = self.http_client.get(nearest_url, headers=headers, params=params)
        
        if response is None:
            logging.error("Failed to get geohash from Met Office")
            return None
        
        try:
            nearest_data = response.json()
            if not nearest_data or len(nearest_data) == 0:
                logging.error("No location data returned from nearest endpoint")
                return None
            
            geohash = nearest_data[0].get('geohash')
            if not geohash:
                logging.error("No geohash found in nearest response")
                return None
            
            logging.info(f"Found geohash: {geohash} (area: {nearest_data[0].get('area', 'Unknown')})")
            
        except (json.JSONDecodeError, KeyError, IndexError) as e:
            logging.error(f"Failed to parse nearest endpoint response: {e}")
            return None
        
        # Step 2: Get weather observations for the geohash
        logging.info(f"Step 2: Fetching weather observations for geohash {geohash}...")
        observations_url = f"{self.base_url}/observation-land/1/{geohash}"
        
        response = self.http_client.get(observations_url, headers=headers, params={})
        
        if response is None:
            logging.error("Failed to fetch weather observations from Met Office")
            return None
        
        try:
            data = response.json()
            logging.info("Successfully fetched weather observations")
            logging.debug(f"Response data: {json.dumps(data, indent=2)}")
            return data
        except json.JSONDecodeError as e:
            logging.error(f"Failed to parse observations JSON response: {e}")
            return None
    
    def parse_weather_data(self, raw_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Parse and validate weather data from API response"""
        
        try:
            # API returns a simple list of observation objects
            if not isinstance(raw_data, list) or len(raw_data) == 0:
                logging.error("No observations found in response")
                return None
            
            # The API returns a list of observations (typically ordered oldest -> newest).
            # Do not assume ordering; instead, pick the observation with the newest datetime.
            def _parse_dt(dt: str) -> datetime:
                # Met Office uses RFC3339/ISO8601 with trailing 'Z' for UTC
                return datetime.fromisoformat(dt.replace('Z', '+00:00'))

            observations_with_dt = [o for o in raw_data if isinstance(o, dict) and o.get('datetime')]
            if not observations_with_dt:
                logging.error("No observations with a 'datetime' field found in response")
                return None

            latest = max(observations_with_dt, key=lambda o: _parse_dt(o['datetime']))
            latest_dt = _parse_dt(latest['datetime'])

            # Extract weather parameters from the flat structure
            parsed_data = {
                'timestamp': latest_dt.isoformat().replace('+00:00', 'Z'),
                'location_name': self.location.get('name', 'Unknown'),
                'latitude': self.location['latitude'],
                'longitude': self.location['longitude'],
                'temperature': latest.get('temperature'),
                'humidity': latest.get('humidity'),
                'msl_pressure': latest.get('mslp'),
                'pressure_tendency': latest.get('pressure_tendency'),
                'visibility': latest.get('visibility'),
                'weather_code': latest.get('weather_code'),
                'wind_direction': latest.get('wind_direction'),
                'wind_gust': latest.get('wind_gust'),
                'wind_speed': latest.get('wind_speed')
            }
            
            # Remove None values
            parsed_data = {k: v for k, v in parsed_data.items() if v is not None}
            
            logging.info(f"Parsed weather data for {parsed_data.get('location_name')}")
            logging.info(f"Observation time: {parsed_data.get('timestamp')}")
            return parsed_data
            
        except Exception as e:
            logging.error(f"Error parsing weather data: {e}")
            return None


class InfluxDBWriter:
    """Writer for InfluxDB v2 with retry logic"""
    
    def __init__(self, config: Config):
        self.config = config
        self.url = config.get('influxdb', 'url')
        self.org = config.get('influxdb', 'org')
        self.bucket = config.get('influxdb', 'bucket')
        self.token = config.get('influxdb', 'token')
        self.timeout = config.get('influxdb', 'timeout') * 1000  # Convert to ms
        
        retry_config = config.get('influxdb', 'retry')
        self.max_attempts = retry_config['max_attempts']
        self.initial_backoff = retry_config['initial_backoff']
        self.max_backoff = retry_config['max_backoff']
    
    def write_data(self, weather_data: Dict[str, Any]) -> bool:
        """Write weather data to InfluxDB with retry logic"""
        
        attempt = 0
        backoff = self.initial_backoff
        
        while attempt < self.max_attempts:
            try:
                logging.info(f"Attempting to write to InfluxDB (attempt {attempt + 1}/{self.max_attempts})")
                
                with InfluxDBClient(
                    url=self.url,
                    token=self.token,
                    org=self.org,
                    timeout=self.timeout
                ) as client:
                    write_api = client.write_api(write_options=SYNCHRONOUS)
                    
                    # Create point
                    point = Point("weather_observation")
                    
                    # Add tags
                    point.tag("location", weather_data.get('location_name', 'Unknown'))
                    point.tag("source", "met_office")
                    
                    # Add fields
                    for key, value in weather_data.items():
                        if key not in ['timestamp', 'location_name', 'latitude', 'longitude']:
                            if isinstance(value, (int, float)):
                                point.field(key, float(value))
                            elif isinstance(value, str) and key != 'timestamp':
                                point.field(key, value)
                    
                    # Set timestamp
                    if 'timestamp' in weather_data:
                        timestamp = datetime.fromisoformat(weather_data['timestamp'].replace('Z', '+00:00'))
                        point.time(timestamp)
                    
                    # Write to InfluxDB
                    write_api.write(bucket=self.bucket, record=point)
                    
                    logging.info("Successfully wrote data to InfluxDB")
                    return True
                    
            except InfluxDBError as e:
                logging.warning(f"InfluxDB error: {e}")
            except Exception as e:
                logging.warning(f"Error writing to InfluxDB: {e}")
            
            attempt += 1
            
            if attempt < self.max_attempts:
                next_backoff = min(backoff, self.max_backoff)
                logging.info(f"Retrying in {next_backoff}s...")
                time.sleep(next_backoff)
                backoff *= 2
        
        logging.error(f"Failed to write to InfluxDB after {self.max_attempts} attempts")
        return False


class CacheManager:
    """Manages local file cache for failed InfluxDB writes"""
    
    def __init__(self, config: Config):
        self.cache_path = Path(config.get('cache', 'file_path'))
        self._ensure_cache_directory()
    
    def _ensure_cache_directory(self):
        """Ensure cache directory exists"""
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
    
    def save_to_cache(self, weather_data: Dict[str, Any]):
        """Save weather data to local cache file with atomic write"""
        try:
            # Load existing cache
            cached_data = []
            if self.cache_path.exists():
                # Security: Check cache file size
                cache_size_mb = self.cache_path.stat().st_size / (1024 * 1024)
                if cache_size_mb > MAX_CACHE_SIZE_MB:
                    logging.error(f"Cache file exceeds maximum size ({MAX_CACHE_SIZE_MB}MB). "
                                 "Clearing old entries.")
                    # Keep only the most recent entries
                    with open(self.cache_path, 'r') as f:
                        all_entries = json.load(f)
                    cached_data = all_entries[-MAX_CACHE_ENTRIES//2:] if len(all_entries) > MAX_CACHE_ENTRIES//2 else []
                else:
                    with open(self.cache_path, 'r') as f:
                        cached_data = json.load(f)
                
                # Security: Limit number of cached entries
                if len(cached_data) >= MAX_CACHE_ENTRIES:
                    logging.warning(f"Cache has reached maximum entries ({MAX_CACHE_ENTRIES}). "
                                   "Removing oldest entries.")
                    cached_data = cached_data[-(MAX_CACHE_ENTRIES-1):]
            
            # Add new data with metadata
            cache_entry = {
                'data': weather_data,
                'cached_at': datetime.now(timezone.utc).isoformat()
            }
            cached_data.append(cache_entry)
            
            # Security: Atomic write using temporary file
            temp_fd, temp_path = tempfile.mkstemp(
                dir=self.cache_path.parent,
                prefix='.cache_',
                suffix='.tmp'
            )
            try:
                with open(temp_fd, 'w') as f:
                    json.dump(cached_data, f, indent=2)
                
                # Set secure permissions (owner read/write only)
                Path(temp_path).chmod(0o600)
                
                # Atomic rename
                shutil.move(temp_path, self.cache_path)
                
                logging.info(f"Saved data to cache: {self.cache_path}")
                logging.info(f"Total cached entries: {len(cached_data)}")
            finally:
                # Clean up temp file if it still exists
                try:
                    Path(temp_path).unlink()
                except FileNotFoundError:
                    pass
            
        except Exception as e:
            logging.error(f"Failed to save to cache: {e}")
    
    def load_cached_data(self) -> List[Dict[str, Any]]:
        """Load all cached weather data"""
        try:
            if not self.cache_path.exists():
                return []
            
            with open(self.cache_path, 'r') as f:
                cached_data = json.load(f)
            
            logging.info(f"Loaded {len(cached_data)} cached entries")
            return cached_data
            
        except Exception as e:
            logging.error(f"Failed to load cache: {e}")
            return []
    
    def clear_cache(self):
        """Clear the cache file"""
        try:
            if self.cache_path.exists():
                self.cache_path.unlink()
                logging.info("Cache cleared")
        except Exception as e:
            logging.error(f"Failed to clear cache: {e}")
    
    def has_cached_data(self) -> bool:
        """Check if there is cached data"""
        return self.cache_path.exists() and self.cache_path.stat().st_size > 0


class WeatherCollector:
    """Main weather collection orchestrator"""
    
    def __init__(self, config_path: str = "config.yml"):
        self.config = Config(config_path)
        self._setup_logging()
        
        self.met_office = MetOfficeClient(self.config)
        self.influxdb = InfluxDBWriter(self.config)
        self.cache = CacheManager(self.config)
    
    def _setup_logging(self):
        """Configure logging"""
        log_level = self.config.get('logging', 'level')
        logging.basicConfig(
            level=getattr(logging, log_level),
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.StreamHandler(sys.stdout)
            ]
        )
    
    def process_cached_data(self):
        """Process and upload any cached data"""
        if not self.cache.has_cached_data():
            logging.info("No cached data to process")
            return
        
        logging.info("Processing cached data...")
        cached_entries = self.cache.load_cached_data()
        
        if not cached_entries:
            return
        
        successful = 0
        failed_entries = []
        
        for entry in cached_entries:
            weather_data = entry.get('data')
            cached_at = entry.get('cached_at')
            
            logging.info(f"Attempting to upload cached entry from {cached_at}")
            
            if self.influxdb.write_data(weather_data):
                successful += 1
            else:
                failed_entries.append(entry)
        
        logging.info(f"Successfully uploaded {successful}/{len(cached_entries)} cached entries")
        
        if failed_entries:
            # Save failed entries back to cache
            try:
                with open(self.cache.cache_path, 'w') as f:
                    json.dump(failed_entries, f, indent=2)
                logging.warning(f"{len(failed_entries)} entries remain in cache")
            except Exception as e:
                logging.error(f"Failed to update cache: {e}")
        else:
            # Clear cache if all successful
            self.cache.clear_cache()
    
    def collect(self):
        """Main collection workflow"""
        logging.info("=" * 60)
        logging.info("Weather Collection Started")
        logging.info("=" * 60)
        
        # Step 1: Fetch weather data
        raw_data = self.met_office.fetch_weather_data()
        if raw_data is None:
            logging.error("Failed to fetch weather data. Exiting.")
            sys.exit(1)
        
        # Step 2: Parse weather data
        weather_data = self.met_office.parse_weather_data(raw_data)
        if weather_data is None:
            logging.error("Failed to parse weather data. Exiting.")
            sys.exit(1)
        
        # Step 3: Try to write to InfluxDB
        if self.influxdb.write_data(weather_data):
            logging.info("Successfully wrote current data to InfluxDB")
            
            # Step 4: Process any cached data
            self.process_cached_data()
        else:
            logging.warning("Failed to write to InfluxDB. Saving to cache.")
            self.cache.save_to_cache(weather_data)
        
        logging.info("=" * 60)
        logging.info("Weather Collection Completed")
        logging.info("=" * 60)


def main():
    """Main entry point"""
    try:
        collector = WeatherCollector()
        collector.collect()
    except KeyboardInterrupt:
        logging.info("Collection interrupted by user")
        sys.exit(0)
    except Exception as e:
        logging.error(f"Unexpected error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
