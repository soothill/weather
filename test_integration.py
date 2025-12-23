"""
Integration Tests for Weather Collector

Copyright (c) 2025 Darren Soothill
Email: darren [at] soothill [dot] com
All rights reserved.
"""

import pytest
import yaml
import json
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
import tempfile
import os

# Import modules under test
import sys
sys.path.insert(0, str(Path(__file__).parent))
from weather_collector import WeatherCollector, Config


@pytest.mark.integration
class TestCollectionWorkflow:
    """Test end-to-end collection workflow"""
    
    def test_successful_collection(self, temp_config_path, sample_config_data):
        """Test complete successful collection workflow"""
        with open(temp_config_path, 'w') as f:
            yaml.dump(sample_config_data, f)
        
        # Mock Met Office API
        sample_response = [{
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
        }]
        
        with patch('weather_collector.requests.get') as mock_get:
            mock_response = Mock()
            mock_response.json.return_value = [{'geohash': 'gcpm4w', 'area': 'Test'}]
            mock_response.raise_for_status = Mock()
            mock_get.return_value = mock_response
            
            # Mock observations response
            mock_obs = Mock()
            mock_obs.json.return_value = sample_response
            mock_obs.raise_for_status = Mock()
            
            with patch('weather_collector.requests.get') as mock_get:
                # First call gets geohash, second gets observations
                mock_get.side_effect = [mock_response, mock_obs]
                
                # Mock InfluxDB write
                with patch('weather_collector.InfluxDBClient') as mock_client:
                    mock_write_api = MagicMock()
                    mock_client.return_value.write_api.return_value = mock_write_api
                    
                    collector = WeatherCollector(str(temp_config_path))
                    
                    # Should not raise exception
                    collector.collect()
    
    def test_api_failure(self, temp_config_path, sample_config_data):
        """Test handling of API failure"""
        with open(temp_config_path, 'w') as f:
            yaml.dump(sample_config_data, f)
        
        with patch('weather_collector.requests.get') as mock_get:
            mock_get.side_effect = Exception("API Error")
            
            collector = WeatherCollector(str(temp_config_path))
            
            with pytest.raises(SystemExit):
                collector.collect()


@pytest.mark.integration
class TestCacheRecovery:
    """Test cache recovery after InfluxDB failure"""
    
    def test_cache_on_influxdb_failure(self, temp_cache_path, sample_config_data):
        """Test data is cached when InfluxDB fails"""
        sample_config_data['cache']['file_path'] = str(temp_cache_path)
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yml', delete=False) as f:
            temp_config = Path(f.name)
            yaml.dump(sample_config_data, f)
        
        try:
            # Mock successful API response
            sample_response = [{
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
            }]
            
            with patch('weather_collector.requests.get') as mock_get:
                mock_response = Mock()
                mock_response.json.return_value = [{'geohash': 'gcpm4w'}]
                mock_response.raise_for_status = Mock()
                
                mock_obs = Mock()
                mock_obs.json.return_value = sample_response
                mock_obs.raise_for_status = Mock()
                
                mock_get.side_effect = [mock_response, mock_obs]
                
                # Mock InfluxDB failure
                with patch('weather_collector.InfluxDBClient') as mock_client:
                    from influxdb_client.client.exceptions import InfluxDBError
                    mock_write_api = MagicMock()
                    mock_write_api.write.side_effect = InfluxDBError("Connection failed")
                    mock_client.return_value.write_api.return_value = mock_write_api
                    
                    collector = WeatherCollector(str(temp_config))
                    collector.collect()
                
                # Verify cache was created
                assert temp_cache_path.exists()
                with open(temp_cache_path, 'r') as f:
                    cached_data = json.load(f)
                assert len(cached_data) > 0
        finally:
            temp_config.unlink(missing_ok=True)
    
    def test_cache_recovery(self, temp_cache_path, temp_config_path, sample_config_data):
        """Test cached data is uploaded when InfluxDB is available"""
        sample_config_data['cache']['file_path'] = str(temp_cache_path)
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yml', delete=False) as f:
            temp_config = Path(f.name)
            yaml.dump(sample_config_data, f)
        
        try:
            # Create cache file with data
            cache_data = [{
                'data': {
                    'timestamp': '2024-12-15T10:00:00Z',
                    'location_name': 'Test Location',
                    'latitude': 52.0867,
                    'longitude': -0.7231,
                    'temperature': 15.5,
                    'humidity': 65,
                    'msl_pressure': 1013.2
                },
                'cached_at': '2024-12-15T10:05:00Z'
            }]
            with open(temp_cache_path, 'w') as f:
                json.dump(cache_data, f)
            
            # Mock successful API and InfluxDB
            sample_response = [{
                'datetime': '2024-12-15T11:00:00Z',
                'temperature': 16.0,
                'humidity': 64,
                'mslp': 1014.0,
                'pressure_tendency': 'rising',
                'visibility': 10000,
                'weather_code': 1,
                'wind_direction': 185,
                'wind_gust': 13.0,
                'wind_speed': 9.0
            }]
            
            with patch('weather_collector.requests.get') as mock_get:
                mock_response = Mock()
                mock_response.json.return_value = [{'geohash': 'gcpm4w'}]
                mock_response.raise_for_status = Mock()
                
                mock_obs = Mock()
                mock_obs.json.return_value = sample_response
                mock_obs.raise_for_status = Mock()
                
                mock_get.side_effect = [mock_response, mock_obs]
                
                with patch('weather_collector.InfluxDBClient') as mock_client:
                    mock_write_api = MagicMock()
                    mock_write_api.write = Mock()  # Successful write
                    mock_client.return_value.write_api.return_value = mock_write_api
                    
                    collector = WeatherCollector(str(temp_config))
                    collector.collect()
                
                # Verify cache was processed and cleared
                assert not temp_cache_path.exists()
        finally:
            temp_config.unlink(missing_ok=True)


@pytest.mark.integration
class TestHistoricalImport:
    """Test historical import process"""
    
    def test_successful_import(self, temp_config_path, sample_config_data):
        """Test successful historical data import"""
        with open(temp_config_path, 'w') as f:
            yaml.dump(sample_config_data, f)
        
        # Mock Met Office API with historical data
        historical_data = [
            {
                'datetime': '2024-12-15T08:00:00Z',
                'temperature': 14.5,
                'humidity': 70,
                'mslp': 1012.0,
                'pressure_tendency': 'steady',
                'visibility': 9000,
                'weather_code': 2,
                'wind_direction': 170,
                'wind_gust': 10.0,
                'wind_speed': 6.5
            },
            {
                'datetime': '2024-12-15T07:00:00Z',
                'temperature': 14.0,
                'humidity': 72,
                'mslp': 1011.5,
                'pressure_tendency': 'falling',
                'visibility': 8500,
                'weather_code': 3,
                'wind_direction': 165,
                'wind_gust': 9.5,
                'wind_speed': 5.8
            }
        ]
        
        with patch('weather_collector.requests.get') as mock_get:
            mock_response = Mock()
            mock_response.json.return_value = [{'geohash': 'gcpm4w'}]
            mock_response.raise_for_status = Mock()
            
            mock_obs = Mock()
            mock_obs.json.return_value = historical_data
            mock_obs.raise_for_status = Mock()
            
            mock_get.side_effect = [mock_response, mock_obs]
            
            with patch('weather_collector.InfluxDBClient') as mock_client:
                mock_write_api = MagicMock()
                mock_write_api.write = Mock()
                mock_client.return_value.write_api.return_value = mock_write_api
                
                from historical_import import HistoricalImporter
                importer = HistoricalImporter(str(temp_config_path))
                result = importer.import_historical_data()
                
                assert result == 0  # Success


# Sample config data for tests
@pytest.fixture
def sample_config_data():
    return {
        'met_office': {
            'api_key': 'test_api_key_123456789012345678901234567890123456',
            'base_url': 'https://data.hub.api.metoffice.gov.uk',
            'location': {
                'name': 'Newport Pagnell',
                'latitude': 52.0867,
                'longitude': -0.7231
            },
            'timeout': 30,
            'retry': {
                'max_attempts': 5,
                'initial_backoff': 5,
                'max_backoff': 160,
                'max_total_time': 300
            }
        },
        'influxdb': {
            'url': 'http://localhost:8086',
            'org': 'test-org',
            'bucket': 'test-bucket',
            'token': 'test-token-123456789012345678901234567890123456',
            'timeout': 10,
            'retry': {
                'max_attempts': 3,
                'initial_backoff': 2,
                'max_backoff': 8
            }
        },
        'cache': {
            'file_path': '/tmp/test_cache.json'
        },
        'logging': {
            'level': 'INFO'
        },
        'historical_import': {
            'batch_size': 100
        }
    }


@pytest.fixture
def temp_config_path():
    """Create a temporary config file for testing"""
    fd, path = tempfile.mkstemp(suffix='.yml', prefix='test_config_')
    os.close(fd)
    yield Path(path)
    os.unlink(path)
