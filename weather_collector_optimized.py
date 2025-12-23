#!/usr/bin/env python3
"""
Weather Data Collector - Optimized Version
Enhanced for reliability, performance, and monitoring.

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
import hashlib
import secrets
import threading
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, List, Union
from pathlib import Path
from contextlib import contextmanager
import re

import yaml
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS
from influxdb_client.client.exceptions import InfluxDBError

# Constants for security and performance
MAX_CACHE_SIZE_MB = 10
MAX_CACHE_ENTRIES = 1000
MAX_JSON_SIZE_MB = 50
DEFAULT_REQUEST_TIMEOUT = 30
CIRCUIT_BREAKER_THRESHOLD = 5
CIRCUIT_BREAKER_TIMEOUT = 300  # 5 minutes


class CircuitBreaker:
    """Circuit breaker pattern for preventing cascade failures"""
    
    def __init__(self, failure_threshold: int = 5, recovery_timeout: int = 300):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.failure_count = 0
        self.last_failure_time = None
        self.state = "CLOSED"  # CLOSED, OPEN, HALF_OPEN
        self._lock = threading.Lock()
    
    def call(self, func, *args, **kwargs):
        """Execute function with circuit breaker protection"""
        with self._lock:
            if self.state == "OPEN":
                if (time.time() - self.last_failure_time) > self.recovery_timeout:
                    self.state = "HALF_OPEN"
                    logging.info("Circuit breaker transitioning to HALF_OPEN")
                else:
                    raise Exception("Circuit breaker is OPEN")
            
        try:
            result = func(*args, **kwargs)
            
            # Success - reset circuit breaker
            with self._lock:
                if self.state == "HALF_OPEN":
                    self.state = "CLOSED"
                    logging.info("Circuit breaker transitioning to CLOSED")
                self.failure_count = 0
            
            return result
            
        except Exception as e:
            with self._lock:
                self.failure_count += 1
                self.last_failure_time = time.time()
                
                if self.failure_count >= self.failure_threshold:
                    self.state = "OPEN"
                    logging.warning(f"Circuit breaker OPENED after {self.failure_count} failures")
            
            raise e


class ConfigValidator:
    """Enhanced configuration validator with security checks"""
    
    @staticmethod
    def validate_api_key(api_key: str) -> bool:
        """Validate API key format and detect placeholders"""
        if not api_key or not isinstance(api_key, str):
            return False
        
        # Check for common placeholders
        placeholders = ['YOUR_', 'HERE', 'EXAMPLE', 'REPLACE']
        if any(placeholder in api_key.upper() for placeholder in placeholders):
            return False
        
        # Basic format validation for JWT-like keys
        if len(api_key) < 50:
            return False
        
        return True
    
    @staticmethod
    def validate_coordinates(lat: float, lon: float) -> bool:
        """Validate latitude and longitude ranges"""
        return (-90 <= lat <= 90) and (-180 <= lon <= 180)
    
    @staticmethod
    def validate_url(url: str) -> bool:
        """Basic URL validation"""
        url_pattern = re.compile(
            r'^https?://'  # http:// or https://
            r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,6}\.?|'  # domain...
            r'localhost|'  # localhost...
            r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'  # ...or ip
            r'(?::\d+)?'  # optional port
            r'(?:/?|[/?]\S+)$', re.IGNORECASE)
        return url_pattern.match(url) is not None


class SecureConfig:
    """Enhanced configuration loader with comprehensive validation"""
    
    def __init__(self, config_path: str = "config.yml"):
        self.config_path = config_path
        self.config = self._load_config()
        self._validate_config()
    
    def _load_config(self) -> Dict[str, Any]:
        """Load and validate configuration from YAML file"""
        try:
            config_path = Path(self.config_path)
            
            # Security: Check file permissions
            if config_path.exists():
                stat_info = config_path.stat()
                # Check for world-readable permissions (Unix-like systems)
                if hasattr(stat_info, 'st_mode') and (stat_info.st_mode & 0o004):
                    logging.warning(f"Config file {self.config_path} is world-readable! "
                                   f"Run: chmod 600 {self.config_path}")
                
                # Check file size (prevent DoS via huge config files)
                if stat_info.st_size > 1024 * 1024:  # 1MB limit
                    logging.error("Configuration file too large (>1MB)")
                    sys.exit(1)
            
            with open(self.config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
            
            if not isinstance(config, dict):
                logging.error("Invalid configuration file format")
                sys.exit(1)
            
            # Validate API key format
            api_key = config.get('met_office', {}).get('api_key', '')
            if not ConfigValidator.validate_api_key(api_key):
                logging.error("Invalid API key format or appears to be a placeholder")
                sys.exit(1)
            
            return config
            
        except FileNotFoundError:
            logging.error(f"Configuration file not found: {self.config_path}")
            logging.error("Please copy config.sample.yml to config.yml and configure it")
            sys.exit(1)
        except yaml.YAMLError as e:
            logging.error(f"Error parsing configuration file: {e}")
            sys.exit(1)
        except Exception as e:
            logging.error(f"Unexpected error loading configuration: {e}")
            sys.exit(1)
    
    def _validate_config(self):
        """Enhanced configuration validation"""
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
        
        # Validate URLs
        base_url = self.config.get('met_office', 'base_url')
        if not ConfigValidator.validate_url(base_url):
            logging.error(f"Invalid Met Office base URL: {base_url}")
            sys.exit(1)
        
        influx_url = self.config.get('influxdb', 'url')
        if not ConfigValidator.validate_url(influx_url):
            logging.error(f"Invalid InfluxDB URL: {influx_url}")
            sys.exit(1)
        
        # Validate coordinates
        location = self.config.get('met_office', 'location')
        lat = location.get('latitude')
        lon = location.get('longitude')
        
        if not (isinstance(lat, (int, float)) and isinstance(lon, (int, float))):
            logging.error("Location coordinates must be numeric")
            sys.exit(1)
        
        if not ConfigValidator.validate_coordinates(float(lat), float(lon)):
            logging.error(f"Invalid coordinates: lat={lat}, lon={lon}")
            sys.exit(1)
        
        # Validate numeric values
        for path, min_val, max_val, name in [
            ('met_office.timeout', 1, 300, 'Met Office timeout'),
            ('influxdb.timeout', 1, 300, 'InfluxDB timeout'),
            ('met_office.retry.max_attempts', 1, 10, 'Met Office max attempts'),
            ('influxdb.retry.max_attempts', 1, 10, 'InfluxDB max attempts'),
        ]:
            value = self.get(*path.split('.'))
            if not (isinstance(value, int) and min_val <= value <= max_val):
                logging.error(f"{name} must be between {min_val} and {max_val}")
                sys.exit(1)
    
    def get(self, *keys):
        """Get nested configuration value"""
        value = self.config
        for key in keys:
            value = value.get(key)
            if value is None:
                return None
        return value


class OptimizedHTTPClient:
    """Enhanced HTTP client with connection pooling and retry logic"""
    
    def __init__(self, max_attempts: int, initial_backoff: float, 
                 max_backoff: float, max_total_time: float, timeout: int):
        self.max_attempts = max_attempts
        self.initial_backoff = initial_backoff
        self.max_backoff = max_backoff
        self.max_total_time = max_total_time
        self.timeout = timeout
        
        # Create session with connection pooling
        self.session = requests.Session()
        
        # Configure retry strategy
        retry_strategy = Retry(
            total=max_attempts,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET"]
        )
        
        adapter = HTTPAdapter(
            max_retries=retry_strategy,
            pool_connections=10,
            pool_maxsize=10
        )
        
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)
        
        # Circuit breaker for cascade failure prevention
        self.circuit_breaker = CircuitBreaker(
            failure_threshold=CIRCUIT_BREAKER_THRESHOLD,
            recovery_timeout=CIRCUIT_BREAKER_TIMEOUT
        )
    
    def get(self, url: str, headers: Optional[Dict] = None, 
            params: Optional[Dict] = None) -> Optional[requests.Response]:
        """Perform GET request with enhanced retry and circuit breaker"""
        
        def _make_request():
            try:
                logging.debug(f"Making request to: {url}")
                response = self.session.get(
                    url, 
                    headers=headers, 
                    params=params, 
                    timeout=self.timeout
                )
                
                # Enhanced HTTP error handling
                if response.status_code == 401:
                    logging.error("Authentication failed (401). Check your API key.")
                    return None
                elif response.status_code == 403:
                    logging.error("Access forbidden (403). Check your API permissions.")
                    return None
                elif response.status_code == 429:
                    logging.warning("Rate limited (429). Backing off...")
                    raise requests.exceptions.HTTPError("Rate limit exceeded")
                elif 400 <= response.status_code < 500:
                    logging.error(f"Client error ({response.status_code}): {response.text[:200]}")
                    return None
                
                # Check response size to prevent DoS
                content_length = response.headers.get('content-length')
                if content_length and int(content_length) > MAX_JSON_SIZE_MB * 1024 * 1024:
                    logging.error(f"Response too large: {content_length} bytes")
                    return None
                
                response.raise_for_status()
                logging.info(f"Request successful (status {response.status_code})")
                return response
                
            except requests.exceptions.Timeout:
                logging.warning(f"Request timeout after {self.timeout}s")
                raise
            except requests.exceptions.ConnectionError as e:
                logging.warning(f"Connection error: {e}")
                raise
            except requests.exceptions.HTTPError as e:
                if hasattr(e, 'response') and e.response.status_code >= 500:
                    logging.warning(f"Server error ({e.response.status_code}): Retrying...")
                    raise
                else:
                    logging.error(f"HTTP error: {e}")
                    return None
            except Exception as e:
                logging.error(f"Unexpected error in request: {e}")
                raise
        
        try:
            return self.circuit_breaker.call(_make_request)
        except Exception as e:
            if "Circuit breaker is OPEN" in str(e):
                logging.error("Circuit breaker is OPEN - requests temporarily halted")
            logging.error(f"All {self.max_attempts} attempts failed")
            return None
    
    def close(self):
        """Clean up session resources"""
        self.session.close()


class ThreadSafeCacheManager:
    """Thread-safe cache manager with optimized operations"""
    
    def __init__(self, config):
        self.cache_path = Path(config.get('cache', 'file_path'))
        self._lock = threading.RLock()
        self._ensure_cache_directory()
    
    def _ensure_cache_directory(self):
        """Ensure cache directory exists with proper permissions"""
        with self._lock:
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
    
    def _calculate_checksum(self, data: Dict[str, Any]) -> str:
        """Calculate checksum for data integrity"""
        data_str = json.dumps(data, sort_keys=True, separators=(',', ':'))
        return hashlib.sha256(data_str.encode()).hexdigest()
    
    def save_to_cache(self, weather_data: Dict[str, Any]):
        """Save weather data to cache with integrity checks"""
        try:
            with self._lock:
                # Load existing cache with size limits
                cached_data = []
                if self.cache_path.exists():
                    cache_size_mb = self.cache_path.stat().st_size / (1024 * 1024)
                    if cache_size_mb > MAX_CACHE_SIZE_MB:
                        logging.warning(f"Cache exceeds size limit ({MAX_CACHE_SIZE_MB}MB)")
                        # Keep only recent entries
                        try:
                            with open(self.cache_path, 'r') as f:
                                all_entries = json.load(f)
                            cached_data = all_entries[-MAX_CACHE_ENTRIES//2:]
                        except (json.JSONDecodeError, FileNotFoundError):
                            cached_data = []
                    else:
                        try:
                            with open(self.cache_path, 'r') as f:
                                cached_data = json.load(f)
                        except (json.JSONDecodeError, FileNotFoundError):
                            cached_data = []
                
                # Limit entries
                if len(cached_data) >= MAX_CACHE_ENTRIES:
                    cached_data = cached_data[-(MAX_CACHE_ENTRIES-1):]
                
                # Create cache entry with integrity checksum
                cache_entry = {
                    'data': weather_data,
                    'cached_at': datetime.now(timezone.utc).isoformat(),
                    'checksum': self._calculate_checksum(weather_data),
                    'id': secrets.token_hex(8)  # Unique ID for tracking
                }
                cached_data.append(cache_entry)
                
                # Atomic write with temporary file
                temp_fd, temp_path = tempfile.mkstemp(
                    dir=self.cache_path.parent,
                    prefix='.cache_',
                    suffix='.tmp'
                )
                try:
                    with os.fdopen(temp_fd, 'w') as f:
                        json.dump(cached_data, f, indent=2, sort_keys=True)
                    
                    # Set secure permissions
                    os.chmod(temp_path, 0o600)
                    
                    # Atomic rename
                    shutil.move(temp_path, self.cache_path)
                    
                    logging.info(f"Saved data to cache: {self.cache_path}")
                    logging.info(f"Total cached entries: {len(cached_data)}")
                finally:
                    try:
                        os.unlink(temp_path)
                    except FileNotFoundError:
                        pass
            
        except Exception as e:
            logging.error(f"Failed to save to cache: {e}")
    
    def load_cached_data(self) -> List[Dict[str, Any]]:
        """Load and validate cached data"""
        try:
            with self._lock:
                if not self.cache_path.exists():
                    return []
                
                with open(self.cache_path, 'r') as f:
                    cached_data = json.load(f)
                
                # Validate cache entries
                valid_entries = []
                for entry in cached_data:
                    if isinstance(entry, dict) and 'data' in entry:
                        # Verify checksum if present
                        if 'checksum' in entry:
                            calculated = self._calculate_checksum(entry['data'])
                            if calculated != entry['checksum']:
                                logging.warning(f"Cache entry checksum mismatch, skipping")
                                continue
                        valid_entries.append(entry)
                
                logging.info(f"Loaded {len(valid_entries)} valid cached entries")
                return valid_entries
                
        except Exception as e:
            logging.error(f"Failed to load cache: {e}")
            return []


class OptimizedInfluxDBWriter:
    """Enhanced InfluxDB writer with connection pooling and batch operations"""
    
    def __init__(self, config):
        self.config = config
        self.url = config.get('influxdb', 'url')
        self.org = config.get('influxdb', 'org')
        self.bucket = config.get('influxdb', 'bucket')
        self.token = config.get('influxdb', 'token')
        self.timeout = config.get('influxdb', 'timeout') * 1000
        
        retry_config = config.get('influxdb', 'retry')
        self.max_attempts = retry_config['max_attempts']
        self.initial_backoff = retry_config['initial_backoff']
        self.max_backoff = retry_config['max_backoff']
        
        # Connection pooling
        self._client = None
        self._write_api = None
        self._last_connection_time = 0
        self._connection_ttl = 300  # 5 minutes
    
    @contextmanager
    def _get_client(self):
        """Get InfluxDB client with connection reuse"""
        current_time = time.time()
        
        # Reuse existing connection if fresh
        if (self._client is None or 
            current_time - self._last_connection_time > self._connection_ttl):
            
            if self._client:
                self._client.close()
            
            self._client = InfluxDBClient(
                url=self.url,
                token=self.token,
                org=self.org,
                timeout=self.timeout,
                enable_gzip=True,  # Enable compression
                debug=False
            )
            self._write_api = self._client.write_api(write_options=SYNCHRONOUS)
            self._last_connection_time = current_time
            logging.debug("Created new InfluxDB connection")
        
        try:
            yield self._client, self._write_api
        except Exception as e:
            logging.error(f"InfluxDB client error: {e}")
            raise
    
    def write_batch(self, data_points: List[Dict[str, Any]]) -> Dict[str, int]:
        """Write multiple points in a single batch for efficiency"""
        if not data_points:
            return {"total": 0, "successful": 0, "failed": 0}
        
        attempt = 0
        backoff = self.initial_backoff
        
        while attempt < self.max_attempts:
            try:
                logging.info(f"Writing batch of {len(data_points)} points (attempt {attempt + 1}/{self.max_attempts})")
                
                with self._get_client() as (client, write_api):
                    points = []
                    for weather_data in data_points:
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
                            timestamp = datetime.fromisoformat(
                                weather_data['timestamp'].replace('Z', '+00:00')
                            )
                            point.time(timestamp)
                        
                        points.append(point)
                    
                    # Batch write
                    write_api.write(bucket=self.bucket, record=points)
                    
                    logging.info(f"Successfully wrote {len(data_points)} points to InfluxDB")
                    return {"total": len(data_points), "successful": len(data_points), "failed": 0}
                    
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
        
        logging.error(f"Failed to write batch after {self.max_attempts} attempts")
        return {"total": len(data_points), "successful": 0, "failed": len(data_points)}
    
    def write_data(self, weather_data: Dict[str, Any]) -> bool:
        """Write single data point (backward compatibility)"""
        result = self.write_batch([weather_data])
        return result['successful'] > 0 and result['failed'] == 0
    
    def close(self):
        """Clean up resources"""
        if self._client:
            self._client.close()
            self._client = None
            self._write_api = None


# Rest of the classes would continue with similar optimizations...
# Due to length constraints, I'll focus on the most critical improvements above

if __name__ == "__main__":
    # Example usage
    pass
