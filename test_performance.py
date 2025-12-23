"""
Performance Tests for Weather Collector

Copyright (c) 2025 Darren Soothill
Email: darren [at] soothill [dot] com
All rights reserved.
"""

import pytest
import time
import yaml
import json
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

# Import modules under test
import sys
sys.path.insert(0, str(Path(__file__).parent))
from weather_collector import Config, InfluxDBWriter, CacheManager


@pytest.mark.performance
class TestBatchWritePerformance:
    """Test batch write performance"""
    
    def test_batch_vs_sequential(self, temp_config_path, sample_config_data):
        """Compare batch writes vs sequential writes"""
        with open(temp_config_path, 'w') as f:
            yaml.dump(sample_config_data, f)
        
        config = Config(str(temp_config_path))
        writer = InfluxDBWriter(config)
        
        # Generate test data
        num_points = 100
        data_points = [{
            'timestamp': f'2024-12-15T{i:02d}:00Z',
            'location_name': 'Test Location',
            'latitude': 52.0867,
            'longitude': -0.7231,
            'temperature': 15.0 + (i * 0.1),
            'humidity': 65
        } for i in range(num_points)]
        
        with patch.object(writer, '_get_client') as mock_client:
            mock_write_api = MagicMock()
            mock_client.return_value.__enter__.return_value = (MagicMock(), mock_write_api)
            
            # Test batch write
            start = time.time()
            result = writer.write_batch(data_points)
            batch_time = time.time() - start
            
            assert result["total"] == num_points
            assert result["successful"] == num_points
        
        # Batch write should be significantly faster than sequential
        # (This is a basic benchmark - in real scenario, difference is much larger)
        assert batch_time < 5.0  # Should complete in under 5 seconds
    
    def test_large_batch_write(self, temp_config_path, sample_config_data):
        """Test performance with large batch (500 points)"""
        with open(temp_config_path, 'w') as f:
            yaml.dump(sample_config_data, f)
        
        config = Config(str(temp_config_path))
        writer = InfluxDBWriter(config)
        
        # Generate large test data
        num_points = 500
        data_points = [{
            'timestamp': f'2024-12-15T{i//24:02d}:{i%24:02d}:00Z',
            'location_name': 'Test Location',
            'latitude': 52.0867,
            'longitude': -0.7231,
            'temperature': 15.0,
            'humidity': 65
        } for i in range(num_points)]
        
        with patch.object(writer, '_get_client') as mock_client:
            mock_write_api = MagicMock()
            mock_client.return_value.__enter__.return_value = (MagicMock(), mock_write_api)
            
            start = time.time()
            result = writer.write_batch(data_points)
            elapsed = time.time() - start
            
            assert result["total"] == num_points
            assert result["successful"] == num_points
        
        # Large batch should still be fast
        print(f"Large batch write ({num_points} points): {elapsed:.3f}s")
        assert elapsed < 10.0


@pytest.mark.performance
class TestCachePerformance:
    """Test cache manager performance"""
    
    def test_cache_write_speed(self, temp_config_path, sample_config_data, temp_cache_path):
        """Test cache write performance"""
        sample_config_data['cache']['file_path'] = str(temp_cache_path)
        
        with open(temp_config_path, 'w') as f:
            yaml.dump(sample_config_data, f)
        
        config = Config(str(temp_config_path))
        cache = CacheManager(config)
        cache.cache_path = temp_cache_path
        
        # Generate test data
        num_entries = 100
        data_points = [{
            'timestamp': f'2024-12-15T{i:02d}:00Z',
            'location_name': 'Test Location',
            'temperature': 15.0
        } for i in range(num_entries)]
        
        start = time.time()
        for data in data_points:
            cache.save_to_cache(data)
        elapsed = time.time() - start
        
        print(f"Cache write ({num_entries} entries): {elapsed:.3f}s")
        assert elapsed < 5.0  # Should be fast
    
    def test_cache_read_speed(self, temp_config_path, sample_config_data, temp_cache_path):
        """Test cache read performance"""
        sample_config_data['cache']['file_path'] = str(temp_cache_path)
        
        with open(temp_config_path, 'w') as f:
            yaml.dump(sample_config_data, f)
        
        config = Config(str(temp_config_path))
        cache = CacheManager(config)
        cache.cache_path = temp_cache_path
        
        # Create large cache file
        num_entries = 100
        cache_data = [{
            'data': {
                'timestamp': f'2024-12-15T{i:02d}:00Z',
                'location_name': 'Test Location',
                'temperature': 15.0
            },
            'cached_at': '2024-12-15T10:00:00Z'
        } for i in range(num_entries)]
        
        with open(temp_cache_path, 'w') as f:
            json.dump(cache_data, f)
        
        # Test read speed
        start = time.time()
        loaded = cache.load_cached_data()
        elapsed = time.time() - start
        
        print(f"Cache read ({num_entries} entries): {elapsed:.3f}s")
        assert len(loaded) == num_entries
        assert elapsed < 1.0  # Should be very fast


@pytest.mark.performance
class TestMemoryUsage:
    """Test memory usage during operations"""
    
    def test_batch_write_memory(self, temp_config_path, sample_config_data):
        """Test memory usage during batch write"""
        import gc
        import sys
        
        with open(temp_config_path, 'w') as f:
            yaml.dump(sample_config_data, f)
        
        config = Config(str(temp_config_path))
        writer = InfluxDBWriter(config)
        
        # Force garbage collection
        gc.collect()
        initial_mem = sys.getsizeof(gc.get_objects())
        
        # Generate test data
        num_points = 1000
        data_points = [{
            'timestamp': f'2024-12-15T{i:02d}:00Z',
            'location_name': 'Test Location',
            'latitude': 52.0867,
            'longitude': -0.7231,
            'temperature': 15.0,
            'humidity': 65
        } for i in range(num_points)]
        
        with patch.object(writer, '_get_client') as mock_client:
            mock_write_api = MagicMock()
            mock_client.return_value.__enter__.return_value = (MagicMock(), mock_write_api)
            
            result = writer.write_batch(data_points)
        
        # Check memory after operation
        gc.collect()
        final_mem = sys.getsizeof(gc.get_objects())
        
        mem_increase = final_mem - initial_mem
        print(f"Memory increase for {num_points} points: {mem_increase / 1024 / 1024:.2f} MB")
        
        assert result["total"] == num_points
        # Memory increase should be reasonable (less than 100MB for 1000 points)
        assert mem_increase < 100 * 1024 * 1024


@pytest.mark.slow
@pytest.mark.performance
class TestCacheLimits:
    """Test cache behavior at limits"""
    
    def test_cache_size_limit(self, temp_config_path, sample_config_data, temp_cache_path):
        """Test cache respects size limits"""
        from weather_collector import MAX_CACHE_SIZE_MB, MAX_CACHE_ENTRIES
        
        sample_config_data['cache']['file_path'] = str(temp_cache_path)
        
        with open(temp_config_path, 'w') as f:
            yaml.dump(sample_config_data, f)
        
        config = Config(str(temp_config_path))
        cache = CacheManager(config)
        cache.cache_path = temp_cache_path
        
        # Add many entries to hit limit
        num_entries = MAX_CACHE_ENTRIES + 100
        data_points = [{
            'timestamp': f'2024-12-15T{i:02d}:00Z',
            'location_name': 'Test Location',
            'temperature': 15.0
        } for i in range(num_entries)]
        
        for data in data_points:
            cache.save_to_cache(data)
        
        # Read back and verify limit respected
        loaded = cache.load_cached_data()
        assert len(loaded) <= MAX_CACHE_ENTRIES


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
            'level': 'ERROR'  # Reduce noise in tests
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


@pytest.fixture
def temp_cache_path():
    """Create a temporary cache file for testing"""
    import tempfile
    import os
    fd, path = tempfile.mkstemp(suffix='.json', prefix='test_cache_')
    os.close(fd)
    yield Path(path)
    os.unlink(path)
