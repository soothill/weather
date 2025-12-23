"""
Pytest configuration and fixtures for Weather Collector tests

Copyright (c) 2025 Darren Soothill
Email: darren [at] soothill [dot] com
All rights reserved.
"""

import os
import tempfile
import pytest
from pathlib import Path


@pytest.fixture
def temp_config_path():
    """Create a temporary config file for testing"""
    fd, path = tempfile.mkstemp(suffix='.yml', prefix='test_config_')
    os.close(fd)
    yield Path(path)
    os.unlink(path)


@pytest.fixture
def temp_cache_path():
    """Create a temporary cache file for testing"""
    fd, path = tempfile.mkstemp(suffix='.json', prefix='test_cache_')
    os.close(fd)
    yield Path(path)
    os.unlink(path)


@pytest.fixture
def sample_weather_data():
    """Sample weather data for testing"""
    return {
        'timestamp': '2024-12-15T10:00:00Z',
        'location_name': 'Test Location',
        'latitude': 52.0867,
        'longitude': -0.7231,
        'temperature': 15.5,
        'humidity': 65,
        'msl_pressure': 1013.2,
        'pressure_tendency': 'rising',
        'visibility': 10000,
        'weather_code': 1,
        'wind_direction': 180,
        'wind_gust': 12.5,
        'wind_speed': 8.3
    }


@pytest.fixture
def sample_met_office_response():
    """Sample Met Office API response for testing"""
    return [
        {
            'datetime': '2024-12-15T10:00:00Z',
            'temperature': 15.5,
            'humidity': 65,
            'mslp': 1013.2,
            'pressure_tendency': 'rising',
            'visibility': 10000,
            'weather_code': 1,
            'wind_direction': 180,
            'wind_gust': 12.5,
            'wind_speed': 8.3
        },
        {
            'datetime': '2024-12-15T09:00:00Z',
            'temperature': 14.8,
            'humidity': 68,
            'mslp': 1012.8,
            'pressure_tendency': 'steady',
            'visibility': 9500,
            'weather_code': 2,
            'wind_direction': 175,
            'wind_gust': 11.2,
            'wind_speed': 7.5
        }
    ]


@pytest.fixture
def sample_nearest_response():
    """Sample Met Office nearest station response for testing"""
    return [
        {
            'geohash': 'gcpm4w',
            'area': 'Newport Pagnell',
            'name': 'Newport Pagnell',
            'latitude': 52.0867,
            'longitude': -0.7231
        }
    ]
