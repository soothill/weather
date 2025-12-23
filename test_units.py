"""
Unit Tests for Weather Collector

Copyright (c) 2025 Darren Soothill
Email: darren [at] soothill [dot] com
All rights reserved.
"""

import pytest
import yaml
import sys
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
import responses

# Import modules under test
sys.path.insert(0, str(Path(__file__).parent))
from weather_collector import (
    Config, RetryableHTTPClient, MetOfficeClient,
    InfluxDBWriter, CacheManager, MetOfficeClient
)


class TestConfigValidator:
    """Test Config class validation"""
    
    def test_valid_config(self, temp_config_path, sample_config_data):
        """Test loading valid configuration"""
        with open(temp_config_path, 'w') as f:
            yaml.dump(sample_config_data, f)
        
        config = Config(str(temp_config_path))
        assert config.config is not None
        assert config.get('met_office', 'api_key') == 'test_api_key_123456789012345678901234567890123456'
    
    def test_missing_config_file(self):
        """Test handling of missing config file"""
        with pytest.raises(SystemExit):
            Config('nonexistent.yml')
    
    def test_placeholder_api_key(self, temp_config_path, sample_config_data):
        """Test detection of placeholder API key"""
        sample_config_data['met_office']['api_key'] = 'YOUR_API_KEY_HERE'
        with open(temp_config_path, 'w') as f:
            yaml.dump(sample_config_data, f)
        
        with pytest.raises(SystemExit):
            Config(str(temp_config_path))
    
    def test_missing_required_field(self, temp_config_path, sample_config_data):
        """Test detection of missing required field"""
        del sample_config_data['met_office']['timeout']
        with open(temp_config_path, 'w') as f:
            yaml.dump(sample_config_data, f)
        
        with pytest.raises(SystemExit):
            Config(str(temp_config_path))
    
    def test_get_nested_value(self, temp_config_path, sample_config_data):
        """Test getting nested configuration values"""
        with open(temp_config_path, 'w') as f:
            yaml.dump(sample_config_data, f)
        
        config = Config(str(temp_config_path))
        assert config.get('met_office', 'timeout') == 30
        assert config.get('influxdb', 'url') == 'http://localhost:8086'
        assert config.get('nonexistent', 'key') is None


class TestInfluxDBWriter:
    """Test InfluxDBWriter class"""
    
    def test_write_data_success(self, temp_config_path, sample_config_data, sample_weather_data):
        """Test successful single data write"""
        with open(temp_config_path, 'w') as f:
            yaml.dump(sample_config_data, f)
        
        config = Config(str(temp_config_path))
        writer = InfluxDBWriter(config)
        
        with patch.object(writer, 'write_batch') as mock_batch:
            mock_batch.return_value = {"total": 1, "successful": 1, "failed": 0}
            result = writer.write_data(sample_weather_data)
            assert result is True
            mock_batch.assert_called_once_with([sample_weather_data])
    
    def test_write_data_failure(self, temp_config_path, sample_config_data, sample_weather_data):
        """Test failed single data write"""
        with open(temp_config_path, 'w') as f:
            yaml.dump(sample_config_data, f)
        
        config = Config(str(temp_config_path))
        writer = InfluxDBWriter(config)
        
        with patch.object(writer, 'write_batch') as mock_batch:
            mock_batch.return_value = {"total": 1, "successful": 0, "failed": 1}
            result = writer.write_data(sample_weather_data)
            assert result is False
    
    def test_write_batch_empty(self, temp_config_path, sample_config_data):
        """Test batch write with empty data"""
        with open(temp_config_path, 'w') as f:
            yaml.dump(sample_config_data, f)
        
        config = Config(str(temp_config_path))
        writer = InfluxDBWriter(config)
        
        result = writer.write_batch([])
        assert result == {"total": 0, "successful": 0, "failed": 0}
    
    def test_write_batch_multiple(self, temp_config_path, sample_config_data, sample_weather_data):
        """Test batch write with multiple data points"""
        with open(temp_config_path, 'w') as f:
            yaml.dump(sample_config_data, f)
        
        config = Config(str(temp_config_path))
        writer = InfluxDBWriter(config)
        
        data_points = [sample_weather_data, {**sample_weather_data, 'timestamp': '2024-12-15T11:00:00Z'}]
        
        with patch.object(writer, '_get_client') as mock_client:
            mock_write_api = MagicMock()
            mock_client.return_value.__enter__.return_value = (MagicMock(), mock_write_api)
            
            result = writer.write_batch(data_points)
            assert result["total"] == 2
            assert result["successful"] == 2
            assert result["failed"] == 0


class TestCacheManager:
    """Test CacheManager class"""
    
    def test_save_to_cache(self, temp_cache_path, sample_weather_data):
        """Test saving data to cache"""
        with open(temp_config_path, 'w') as f:
            yaml.dump(sample_config_data, f)
        
        config = Config(str(temp_config_path))
        cache = CacheManager(config)
        cache.cache_path = temp_cache_path
        
        cache.save_to_cache(sample_weather_data)
        
        assert temp_cache_path.exists()
        import json
        with open(temp_cache_path, 'r') as f:
            cached_data = json.load(f)
        assert len(cached_data) == 1
        assert cached_data[0]['data'] == sample_weather_data
    
    def test_load_cached_data(self, temp_cache_path, sample_weather_data):
        """Test loading data from cache"""
        import json
        from datetime import timezone
        
        # Create cache file
        cache_entry = {
            'data': sample_weather_data,
            'cached_at': '2024-12-15T10:00:00Z'
        }
        with open(temp_cache_path, 'w') as f:
            json.dump([cache_entry], f)
        
        with open(temp_config_path, 'w') as f:
            yaml.dump(sample_config_data, f)
        
        config = Config(str(temp_config_path))
        cache = CacheManager(config)
        cache.cache_path = temp_cache_path
        
        data = cache.load_cached_data()
        assert len(data) == 1
        assert data[0]['data'] == sample_weather_data
    
    def test_has_cached_data(self, temp_cache_path, sample_weather_data):
        """Test checking if cache has data"""
        import json
        
        with open(temp_config_path, 'w') as f:
            yaml.dump(sample_config_data, f)
        
        config = Config(str(temp_config_path))
        cache = CacheManager(config)
        cache.cache_path = temp_cache_path
        
        assert not cache.has_cached_data()
        
        # Write cache file
        with open(temp_cache_path, 'w') as f:
            json.dump([{'data': sample_weather_data}], f)
        
        assert cache.has_cached_data()
    
    def test_clear_cache(self, temp_cache_path, sample_weather_data):
        """Test clearing cache"""
        import json
        
        # Create cache file
        with open(temp_cache_path, 'w') as f:
            json.dump([{'data': sample_weather_data}], f)
        
        with open(temp_config_path, 'w') as f:
            yaml.dump(sample_config_data, f)
        
        config = Config(str(temp_config_path))
        cache = CacheManager(config)
        cache.cache_path = temp_cache_path
        
        cache.clear_cache()
        assert not temp_cache_path.exists()


class TestRetryableHTTPClient:
    """Test RetryableHTTPClient class"""
    
    def test_success_on_first_attempt(self):
        """Test successful request on first attempt"""
        client = RetryableHTTPClient(
            max_attempts=3,
            initial_backoff=1,
            max_backoff=10,
            max_total_time=30,
            timeout=10
        )
        
        with responses.RequestsMock() as rsps:
            rsps.add(
                responses.GET,
                'http://test.com/api',
                json={'data': 'test'},
                status=200
            )
            
            response = client.get('http://test.com/api')
            assert response is not None
            assert response.status_code == 200
    
    def test_retry_on_500_error(self):
        """Test retry on server error"""
        client = RetryableHTTPClient(
            max_attempts=3,
            initial_backoff=0.1,  # Fast for testing
            max_backoff=0.5,
            max_total_time=5,
            timeout=10
        )
        
        with responses.RequestsMock() as rsps:
            rsps.add(responses.GET, 'http://test.com/api', status=500)
            rsps.add(responses.GET, 'http://test.com/api', status=500)
            rsps.add(
                responses.GET,
                'http://test.com/api',
                json={'data': 'test'},
                status=200
            )
            
            response = client.get('http://test.com/api')
            assert response is not None
            assert response.status_code == 200
            assert len(rsps.calls) == 3
    
    def test_no_retry_on_401_error(self):
        """Test no retry on authentication error"""
        client = RetryableHTTPClient(
            max_attempts=3,
            initial_backoff=0.1,
            max_backoff=0.5,
            max_total_time=5,
            timeout=10
        )
        
        with responses.RequestsMock() as rsps:
            rsps.add(responses.GET, 'http://test.com/api', status=401)
            
            response = client.get('http://test.com/api')
            assert response is None
            assert len(rsps.calls) == 1
    
    def test_max_attempts_exceeded(self):
        """Test behavior when max attempts exceeded"""
        client = RetryableHTTPClient(
            max_attempts=2,
            initial_backoff=0.1,
            max_backoff=0.5,
            max_total_time=5,
            timeout=10
        )
        
        with responses.RequestsMock() as rsps:
            rsps.add(responses.GET, 'http://test.com/api', status=500)
            rsps.add(responses.GET, 'http://test.com/api', status=500)
            
            response = client.get('http://test.com/api')
            assert response is None
            assert len(rsps.calls) == 2


class TestMetOfficeClient:
    """Test MetOfficeClient class"""
    
    def test_parse_weather_data_valid(self, temp_config_path, sample_config_data, sample_met_office_response):
        """Test parsing valid weather data"""
        with open(temp_config_path, 'w') as f:
            yaml.dump(sample_config_data, f)
        
        config = Config(str(temp_config_path))
        client = MetOfficeClient(config)
        
        parsed = client.parse_weather_data(sample_met_office_response)
        assert parsed is not None
        assert 'temperature' in parsed
        assert 'humidity' in parsed
        assert parsed['location_name'] == 'Newport Pagnell'
    
    def test_parse_weather_data_empty(self, temp_config_path, sample_config_data):
        """Test parsing empty response"""
        with open(temp_config_path, 'w') as f:
            yaml.dump(sample_config_data, f)
        
        config = Config(str(temp_config_path))
        client = MetOfficeClient(config)
        
        parsed = client.parse_weather_data([])
        assert parsed is None
    
    def test_parse_weather_data_no_datetime(self, temp_config_path, sample_config_data):
        """Test parsing response without datetime"""
        with open(temp_config_path, 'w') as f:
            yaml.dump(sample_config_data, f)
        
        config = Config(str(temp_config_path))
        client = MetOfficeClient(config)
        
        response = [{'temperature': 15.5, 'humidity': 65}]
        parsed = client.parse_weather_data(response)
        assert parsed is None


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
    import tempfile
    import os
    fd, path = tempfile.mkstemp(suffix='.yml', prefix='test_config_')
    os.close(fd)
    yield Path(path)
    os.unlink(path)
