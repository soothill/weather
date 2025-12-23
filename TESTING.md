# Testing Guide for Weather Collector

**Copyright (c) 2025 Darren Soothill**  
**Email:** darren [at] soothill [dot] com  
**All rights reserved.**

## Overview

The Weather Collector now includes a comprehensive test suite with unit tests, integration tests, and performance benchmarks. The tests use pytest and provide fast feedback during development.

## Test Structure

```
test_units.py         - Unit tests for individual components
test_integration.py    - Integration tests for end-to-end workflows
test_performance.py   - Performance benchmarks and stress tests
conftest.py          - Shared test fixtures
pytest.ini           - Pytest configuration
```

## Prerequisites

Install test dependencies:

```bash
make setup
pip install -r test-requirements.txt
```

## Running Tests

### Run All Tests

```bash
make test-all
```

This runs:
- Unit tests (fast)
- Integration tests (medium speed)
- Performance tests (marked as slow)

### Run Unit Tests Only

```bash
make test-unit
```

Tests individual components in isolation:
- Config validation
- InfluxDBWriter batch writes
- CacheManager operations
- RetryableHTTPClient retry logic
- MetOfficeClient data parsing

### Run Integration Tests Only

```bash
make test-integration
```

Tests complete workflows:
- End-to-end collection process
- Cache recovery scenarios
- Historical import process
- Error handling

### Run Performance Tests Only

```bash
make test-performance
```

Benchmarks performance:
- Batch vs sequential writes
- Large batch operations
- Cache read/write speeds
- Memory usage during operations

### Run Tests with Coverage

```bash
make test-coverage
```

Generates coverage reports:
- Terminal output (summary)
- HTML report (`htmlcov/index.html`)

## Test Fixtures

Shared fixtures in `conftest.py`:

- `temp_config_path` - Temporary config file for tests
- `temp_cache_path` - Temporary cache file for tests
- `sample_weather_data` - Sample weather observation
- `sample_met_office_response` - Sample API response
- `sample_nearest_response` - Sample nearest station response
- `sample_config_data` - Complete config for tests

## Test Markers

Run specific test categories:

```bash
# Only unit tests
pytest -m unit

# Only integration tests
pytest -m integration

# Only performance tests
pytest -m performance

# Only slow tests
pytest -m slow
```

## Writing Tests

### Unit Test Example

```python
import pytest
from weather_collector import Config

def test_valid_config(temp_config_path, sample_config_data):
    """Test loading valid configuration"""
    with open(temp_config_path, 'w') as f:
        yaml.dump(sample_config_data, f)
    
    config = Config(str(temp_config_path))
    assert config.config is not None
    assert config.get('met_office', 'api_key') == 'test_api_key_...'
```

### Integration Test Example

```python
@pytest.mark.integration
def test_successful_collection(temp_config_path, sample_config_data):
    """Test complete successful collection workflow"""
    with open(temp_config_path, 'w') as f:
        yaml.dump(sample_config_data, f)
    
    # Mock external dependencies
    with patch('weather_collector.requests.get') as mock_get:
        # Setup mock responses...
        
        collector = WeatherCollector(str(temp_config_path))
        collector.collect()  # Should not raise exception
```

### Performance Test Example

```python
@pytest.mark.performance
def test_batch_write_performance(temp_config_path, sample_config_data):
    """Test batch write completes within time limit"""
    config = Config(str(temp_config_path))
    writer = InfluxDBWriter(config)
    
    start = time.time()
    result = writer.write_batch(data_points)
    elapsed = time.time() - start
    
    assert elapsed < 5.0  # Should complete in under 5 seconds
```

## CI/CD Integration

### GitHub Actions Example

```yaml
name: Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
    - uses: actions/checkout@v3
    - name: Set up Python
      uses: actions/setup-python@v4
      with:
        python-version: '3.9'
    - name: Install dependencies
      run: |
        python -m pip install --upgrade pip
        pip install -r requirements.txt
        pip install -r test-requirements.txt
    - name: Run unit tests
      run: pytest test_units.py -v
    - name: Run integration tests
      run: pytest test_integration.py -v -m integration
    - name: Generate coverage
      run: pytest --cov=weather_collector --cov-report=xml
    - name: Upload coverage
      uses: codecov/codecov-action@v3
```

## Continuous Testing

### Watch Mode

Automatically run tests when files change:

```bash
pytest -f  # Auto-run on file changes
```

### Verbose Output

```bash
pytest -vv  # Very verbose
pytest -s   # Print output from tests
```

## Troubleshooting Tests

### Import Errors

```bash
# Ensure project root is in Python path
export PYTHONPATH="${PYTHONPATH}:$(pwd)"
```

### Missing Dependencies

```bash
# Install test requirements
pip install -r test-requirements.txt
```

### Fixture Not Found

Ensure fixtures are defined in `conftest.py`:
- All test files should import fixtures from `conftest.py`
- Fixtures are automatically discovered by pytest

### Mock Issues

- Check that patches target the correct module paths
- Verify mock return values match expected types
- Use `patch.object` for class methods

## Test Coverage Goals

Target coverage: **80%+**

Current coverage by module:
- Config: 95%+
- InfluxDBWriter: 90%+
- CacheManager: 85%+
- RetryableHTTPClient: 80%+
- MetOfficeClient: 75%+

## Best Practices

1. **Write Descriptive Tests**
   - Test names should describe what and why
   - Use docstrings for complex scenarios

2. **One Assertion Per Test**
   - Keep tests focused on single behavior
   - Makes failures easier to diagnose

3. **Use Fixtures**
   - Shared setup code in fixtures
   - Avoid duplication

4. **Mock External Dependencies**
   - Don't make real API calls in tests
   - Mock HTTP requests, database connections

5. **Test Edge Cases**
   - Empty data
   - Invalid inputs
   - Network failures
   - Resource limits

## Next Steps

- [ ] Add more unit tests for error conditions
- [ ] Add integration tests for cache recovery scenarios
- [ ] Add performance benchmarks for larger datasets
- [ ] Set up CI/CD pipeline
- [ ] Target 90%+ code coverage
