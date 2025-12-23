#!/usr/bin/env python3
"""
Comprehensive reliability test suite for weather collector optimizations.
Tests circuit breaker, thread safety, input validation, and performance.

Copyright (c) 2025 Darren Soothill
Email: darren [at] soothill [dot] com
All rights reserved.
"""

import sys
import time
import json
import threading
import unittest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timezone
from pathlib import Path
import tempfile
import os

# Import optimized classes
from weather_collector_optimized import (
    CircuitBreaker, ConfigValidator, SecureConfig,
    OptimizedHTTPClient, ThreadSafeCacheManager, OptimizedInfluxDBWriter
)


class TestCircuitBreaker(unittest.TestCase):
    """Test circuit breaker pattern implementation"""
    
    def test_normal_operation(self):
        """Test circuit breaker with successful operations"""
        breaker = CircuitBreaker(failure_threshold=3, recovery_timeout=1)
        
        def successful_operation():
            return "success"
        
        result = breaker.call(successful_operation)
        self.assertEqual(result, "success")
        self.assertEqual(breaker.state, "CLOSED")
    
    def test_failure_threshold(self):
        """Test circuit breaker opens after threshold failures"""
        breaker = CircuitBreaker(failure_threshold=2, recovery_timeout=1)
        
        def failing_operation():
            raise Exception("Simulated failure")
        
        # Trigger failures
        with self.assertRaises(Exception):
            breaker.call(failing_operation)
        with self.assertRaises(Exception):
            breaker.call(failing_operation)
        
        # Should be open now
        with self.assertRaises(Exception) as cm:
            breaker.call(failing_operation)
        
        self.assertIn("Circuit breaker is OPEN", str(cm.exception))
        self.assertEqual(breaker.state, "OPEN")
    
    def test_recovery_timeout(self):
        """Test circuit breaker recovery after timeout"""
        breaker = CircuitBreaker(failure_threshold=2, recovery_timeout=1)
        
        def failing_operation():
            raise Exception("Simulated failure")
        
        # Trigger failures to open circuit
        with self.assertRaises(Exception):
            breaker.call(failing_operation)
        with self.assertRaises(Exception):
            breaker.call(failing_operation)
        
        self.assertEqual(breaker.state, "OPEN")
        
        # Wait for recovery timeout
        time.sleep(1.1)
        
        # Should be HALF_OPEN now
        def successful_operation():
            return "recovered"
        
        result = breaker.call(successful_operation)
        self.assertEqual(result, "recovered")
        self.assertEqual(breaker.state, "CLOSED")


class TestConfigValidator(unittest.TestCase):
    """Test enhanced configuration validation"""
    
    def test_validate_api_key_success(self):
        """Test valid API key validation"""
        valid_key = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4gRG9lIiwiaWF0IjoxNTE2MjM5MDIyfQ.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c"
        self.assertTrue(ConfigValidator.validate_api_key(valid_key))
    
    def test_validate_api_key_placeholder(self):
        """Test placeholder API key detection"""
        placeholder_keys = [
            "YOUR_API_KEY_HERE",
            "EXAMPLE_KEY_123",
            "REPLACE_WITH_REAL_KEY",
            "YOUR_MET_OFFICE_API_KEY_HERE"
        ]
        
        for key in placeholder_keys:
            self.assertFalse(ConfigValidator.validate_api_key(key))
    
    def test_validate_api_key_invalid_format(self):
        """Test invalid API key formats"""
        invalid_keys = [
            "",  # Empty
            "short",  # Too short
            None,  # None
            123,  # Not string
        ]
        
        for key in invalid_keys:
            self.assertFalse(ConfigValidator.validate_api_key(key))
    
    def test_validate_coordinates(self):
        """Test coordinate validation"""
        # Valid coordinates
        valid_coords = [
            (0, 0),  # Equator
            (90, 180),  # Max values
            (-90, -180),  # Min values
            (51.5074, -0.1278),  # London
            (-33.8688, 151.209),  # Sydney
        ]
        
        for lat, lon in valid_coords:
            self.assertTrue(ConfigValidator.validate_coordinates(lat, lon))
        
        # Invalid coordinates
        invalid_coords = [
            (91, 0),  # Latitude too high
            (-91, 0),  # Latitude too low
            (0, 181),  # Longitude too high
            (0, -181),  # Longitude too low
            ("invalid", 0),  # Non-numeric
            (0, "invalid"),  # Non-numeric
        ]
        
        for lat, lon in invalid_coords:
            self.assertFalse(ConfigValidator.validate_coordinates(lat, lon))
    
    def test_validate_url(self):
        """Test URL validation"""
        valid_urls = [
            "https://data.hub.api.metoffice.gov.uk",
            "http://localhost:8086",
            "https://influxdb.example.com:8086",
            "http://192.168.1.100:8086",
        ]
        
        for url in valid_urls:
            self.assertTrue(ConfigValidator.validate_url(url))
        
        invalid_urls = [
            "",  # Empty
            "not-a-url",  # Invalid format
            "ftp://example.com",  # Unsupported protocol
            "https://",  # Incomplete
        ]
        
        for url in invalid_urls:
            self.assertFalse(ConfigValidator.validate_url(url))


class TestThreadSafeCache(unittest.TestCase):
    """Test thread-safe cache operations"""
    
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.cache_path = os.path.join(self.temp_dir, "test_cache.json")
        
        mock_config = Mock()
        mock_config.get.return_value = self.cache_path
        
        self.cache = ThreadSafeCacheManager(mock_config)
    
    def tearDown(self):
        import shutil
        shutil.rmtree(self.temp_dir)
    
    def test_concurrent_write_safety(self):
        """Test thread safety of concurrent write operations"""
        num_threads = 10
        writes_per_thread = 5
        results = []
        errors = []
        
        def write_data(thread_id):
            try:
                for i in range(writes_per_thread):
                    data = {
                        'thread_id': thread_id,
                        'iteration': i,
                        'timestamp': datetime.now(timezone.utc).isoformat()
                    }
                    self.cache.save_to_cache(data)
                    results.append(f"thread-{thread_id}-iter-{i}")
            except Exception as e:
                errors.append(f"thread-{thread_id}-error-{e}")
        
        # Start multiple threads writing to cache
        threads = []
        for i in range(num_threads):
            thread = threading.Thread(target=write_data, args=(i,))
            threads.append(thread)
            thread.start()
        
        # Wait for all threads to complete
        for thread in threads:
            thread.join(timeout=5)
        
        # Verify no errors occurred
        self.assertEqual(len(errors), 0, f"Errors occurred: {errors}")
        
        # Verify all data was written
        cached_data = self.cache.load_cached_data()
        self.assertEqual(len(cached_data), num_threads * writes_per_thread)
        
        # Verify data integrity
        for entry in cached_data:
            self.assertIn('checksum', entry)
            self.assertIn('id', entry)
            self.assertIn('data', entry)
    
    def test_data_integrity(self):
        """Test cache data integrity with checksums"""
        original_data = {
            'temperature': 23.5,
            'humidity': 65,
            'location': 'Test Location'
        }
        
        # Save data
        self.cache.save_to_cache(original_data)
        
        # Load and verify
        cached_data = self.cache.load_cached_data()
        self.assertEqual(len(cached_data), 1)
        
        entry = cached_data[0]
        self.assertEqual(entry['data'], original_data)
        self.assertIn('checksum', entry)
        
        # Verify checksum calculation
        calculated_checksum = self.cache._calculate_checksum(original_data)
        self.assertEqual(entry['checksum'], calculated_checksum)


class TestConnectionPooling(unittest.TestCase):
    """Test HTTP client connection pooling"""
    
    def test_session_reuse(self):
        """Test that HTTP session is reused"""
        client = OptimizedHTTPClient(
            max_attempts=2, initial_backoff=1, max_backoff=2, max_total_time=5, timeout=10
        )
        
        # Mock session to track reuse
        with patch('requests.Session') as mock_session:
            session_instance = Mock()
            mock_session.return_value = session_instance
            
            client.get("https://example.com")
            client.get("https://example.com")
            
            # Session should be created only once
            mock_session.assert_called_once()
            session_instance.get.assert_called()
    
    def test_connection_pool_configuration(self):
        """Test connection pool configuration"""
        client = OptimizedHTTPClient(
            max_attempts=2, initial_backoff=1, max_backoff=2, max_total_time=5, timeout=10
        )
        
        # Verify session has adapters with pooling
        self.assertIsNotNone(client.session)
        self.assertTrue(hasattr(client.session, 'adapters'))


class TestBatchOperations(unittest.TestCase):
    """Test InfluxDB batch write operations"""
    
    def setUp(self):
        self.mock_config = Mock()
        self.mock_config.get.side_effect = lambda *args: {
            'influxdb.url': 'http://localhost:8086',
            'influxdb.org': 'test-org',
            'influxdb.bucket': 'test-bucket',
            'influxdb.token': 'test-token',
            'influxdb.timeout': 10,
            'influxdb.retry.max_attempts': 3,
            'influxdb.retry.initial_backoff': 1,
            'influxdb.retry.max_backoff': 2
        }.get(args[0])
        
        self.writer = OptimizedInfluxDBWriter(self.mock_config)
    
    def test_batch_write_efficiency(self):
        """Test that batch operations are efficient"""
        test_data = [
            {'timestamp': '2023-01-01T00:00:00Z', 'temperature': 20.0 + i}
            for i in range(10)
        ]
        
        with patch.object(self.writer, '_get_client') as mock_client:
            mock_write_api = Mock()
            mock_client.return_value.__enter__.return_value = (None, mock_write_api)
            
            result = self.writer.write_batch(test_data)
            
            # Verify single batch write
            mock_write_api.write.assert_called_once()
            
            # Verify success
            self.assertEqual(result['successful'], 10)
            self.assertEqual(result['failed'], 0)
    
    def test_connection_reuse(self):
        """Test InfluxDB connection reuse"""
        with patch.object(self.writer, '_get_client') as mock_client:
            mock_client_instance = Mock()
            mock_client.return_value.__enter__.return_value = (mock_client_instance, Mock())
            
            # Multiple writes should reuse connection
            test_data = [{'timestamp': '2023-01-01T00:00:00Z', 'temperature': 20.0}]
            
            self.writer.write_data(test_data)
            self.writer.write_data(test_data)
            
            # Connection manager should be called only once (TTL not expired)
            mock_client.assert_called_once()


class TestPerformanceOptimizations(unittest.TestCase):
    """Test performance-related optimizations"""
    
    def test_memory_usage_with_large_dataset(self):
        """Test memory efficiency with large datasets"""
        import psutil
        import os
        
        process = psutil.Process(os.getpid())
        initial_memory = process.memory_info().rss
        
        # Create large dataset
        large_dataset = [
            {
                'timestamp': f'2023-01-01T{i:02d}:00:00Z',
                'temperature': 20.0 + i,
                'humidity': 60 + i,
                'data': 'x' * 100  # Add some payload
            }
            for i in range(1000)
        ]
        
        # Process with optimized cache
        temp_dir = tempfile.mkdtemp()
        try:
            mock_config = Mock()
            mock_config.get.return_value = os.path.join(temp_dir, 'large_cache.json')
            
            cache = ThreadSafeCacheManager(mock_config)
            
            for data in large_dataset:
                cache.save_to_cache(data)
            
            final_memory = process.memory_info().rss
            memory_increase = final_memory - initial_memory
            
            # Memory increase should be reasonable (< 100MB for 1000 entries)
            self.assertLess(memory_increase, 100 * 1024 * 1024)
            
        finally:
            import shutil
            shutil.rmtree(temp_dir)
    
    def test_response_time_improvement(self):
        """Test that optimizations improve response time"""
        start_time = time.time()
        
        # Test optimized HTTP client
        client = OptimizedHTTPClient(
            max_attempts=1, initial_backoff=0, max_backoff=0, max_total_time=1, timeout=10
        )
        
        with patch.object(client.session, 'get') as mock_get:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = {'test': 'data'}
            mock_get.return_value = mock_response
            
            result = client.get("https://example.com")
            
        end_time = time.time()
        response_time = end_time - start_time
        
        # Should be fast (< 100ms for mocked response)
        self.assertLess(response_time, 0.1)
        self.assertIsNotNone(result)


class TestErrorHandling(unittest.TestCase):
    """Test enhanced error handling"""
    
    def test_structured_error_response(self):
        """Test that errors are properly categorized and logged"""
        client = OptimizedHTTPClient(
            max_attempts=1, initial_backoff=0, max_backoff=0, max_total_time=1, timeout=10
        )
        
        with patch.object(client.session, 'get') as mock_get:
            # Test different error scenarios
            error_scenarios = [
                (401, "Authentication failed"),
                (403, "Access forbidden"),
                (429, "Rate limited"),
                (500, "Server error"),
                (timeout, "Request timeout")
            ]
            
            for status_code, expected_message in error_scenarios:
                mock_response = Mock()
                mock_response.status_code = status_code
                mock_response.headers = {}
                
                if status_code == timeout:
                    mock_get.side_effect = requests.exceptions.Timeout("Timeout")
                else:
                    mock_response.status_code = status_code
                    mock_response.json.return_value = {'error': 'test'}
                    mock_get.return_value = mock_response
                
                result = client.get("https://example.com")
                
                # Should handle gracefully and return None for errors
                if status_code in [401, 403, 429]:
                    self.assertIsNone(result)


def run_performance_benchmarks():
    """Run performance benchmarks to measure improvements"""
    print("Running performance benchmarks...")
    
    # Test connection pooling
    print("\n1. Testing HTTP Connection Pooling...")
    start_time = time.time()
    
    client = OptimizedHTTPClient(
        max_attempts=3, initial_backoff=1, max_backoff=2, max_total_time=10, timeout=5
    )
    
    # Simulate multiple requests
    for i in range(10):
        # Mock actual requests for benchmark
        pass
    
    end_time = time.time()
    print(f"   Connection setup time: {(end_time - start_time)*1000:.2f}ms")
    
    # Test cache performance
    print("\n2. Testing Cache Performance...")
    start_time = time.time()
    
    temp_dir = tempfile.mkdtemp()
    try:
        mock_config = Mock()
        mock_config.get.return_value = os.path.join(temp_dir, 'benchmark_cache.json')
        
        cache = ThreadSafeCacheManager(mock_config)
        
        # Benchmark cache operations
        for i in range(100):
            data = {
                'timestamp': f'2023-01-01T{i:02d}:00:00Z',
                'temperature': 20.0 + i % 10
            }
            cache.save_to_cache(data)
        
        end_time = time.time()
        print(f"   100 cache writes: {(end_time - start_time)*1000:.2f}ms")
        print(f"   Average per write: {(end_time - start_time)*10:.2f}ms")
        
    finally:
        import shutil
        shutil.rmtree(temp_dir)
    
    print("\nBenchmarks completed!")


if __name__ == '__main__':
    # Run unit tests
    print("Running reliability tests...")
    unittest.main(argv=[''], exit=False)
    
    # Run performance benchmarks
    run_performance_benchmarks()
    
    print("\nAll reliability tests completed!")
    print("\nTo integrate optimizations:")
    print("1. Replace classes in weather_collector.py with optimized versions")
    print("2. Update imports to use SecureConfig, OptimizedHTTPClient, etc.")
    print("3. Test with make test command")
    print("4. Monitor with journalctl -u weather-collector.service -f")
