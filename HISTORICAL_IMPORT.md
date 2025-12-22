# Historical Data Import Feature

**Copyright (c) 2025 Darren Soothill**  
**Email:** darren [at] soothill [dot] com  
**All rights reserved.**

## Overview

The historical data import feature allows you to populate your InfluxDB database with all available historical weather observations from the Met Office DataHub API in a single, efficient operation.

## Key Features

### 🚀 API-Efficient Design
- **Single API Request**: Uses only ONE API call to fetch all historical data
- **No Rate Limiting Risk**: Minimal API load, same impact as regular hourly collection
- **Fast Execution**: Completes in 30-60 seconds typically

### 📊 Data Volume
- **Typical Coverage**: 168+ hours (7 days) of historical observations
- **Data Points**: All weather parameters for each hourly observation
- **Batch Processing**: Writes to InfluxDB in configurable batches (default: 100 points)

### 🔒 Safe & Reliable
- **Idempotent**: Can be re-run safely - InfluxDB handles duplicate timestamps
- **Error Handling**: Continues on failures, reports statistics
- **Progress Tracking**: Clear progress indicators and batch status

## Usage

### Quick Start

```bash
# After setup and configuration
make import-historical
```

### Prerequisites

1. ✅ Virtual environment created (`make setup`)
2. ✅ Configuration file created and edited (`make config`)
3. ✅ Met Office API key configured
4. ✅ InfluxDB connection details configured
5. ✅ Test run successful (`make test`)

### Example Output

```
============================================================
Historical Weather Data Import
============================================================

→ Fetching all available historical data from Met Office API...
2024-12-22 02:15:30 - INFO - Attempting request (attempt 1/5): https://data.hub.api.metoffice.gov.uk/sitespecific/v0/point/hourly
2024-12-22 02:15:32 - INFO - Request successful (status 200)
2024-12-22 02:15:32 - INFO - Successfully fetched weather data

→ Parsing historical observations...
2024-12-22 02:15:32 - INFO - Found 168 historical observations
2024-12-22 02:15:32 - INFO - Date range: 2024-12-15T00:00:00Z to 2024-12-22T02:00:00Z
✓ Retrieved 168 hourly observations
✓ Date range: 2024-12-15T00:00:00Z to 2024-12-22T02:00:00Z

→ Importing to InfluxDB...
2024-12-22 02:15:32 - INFO - Writing 168 observations to InfluxDB in batches of 100...
2024-12-22 02:15:32 - INFO - Processing batch 1/2 (100 points)...
2024-12-22 02:15:35 - INFO - ✓ Batch 1/2: 100/100 points written
2024-12-22 02:15:35 - INFO - Processing batch 2/2 (68 points)...
2024-12-22 02:15:37 - INFO - ✓ Batch 2/2: 68/68 points written

============================================================
Import Complete!
============================================================
✓ Total observations:    168
✓ Successfully imported: 168

2024-12-22 02:15:37 - INFO - All historical data imported successfully!
```

## Technical Details

### Architecture

The historical import reuses existing, tested components:

```python
# Components Used
- Config: Configuration loader (shared)
- MetOfficeClient: API client with retry logic (shared)
- InfluxDBWriter: Database writer with retry (shared)
- HistoricalDataParser: New - extracts ALL time series entries
- HistoricalImporter: New - orchestrates the import process
```

### Data Flow

```
1. Single API Call
   └─> Met Office API returns complete time series

2. Parse ALL Observations
   └─> Extract every entry from timeSeries array (not just latest)

3. Sort by Timestamp
   └─> Oldest to newest for logical import order

4. Batch Write to InfluxDB
   └─> 100 points per batch (configurable)

5. Report Statistics
   └─> Success/failure counts
```

### API Efficiency

**Why Only One API Request?**

The Met Office `/sitespecific/v0/point/hourly` endpoint returns:
- Current observation
- ALL available historical observations in the `timeSeries` array
- Typically 168+ hours of data

**Comparison:**
- ❌ Traditional approach: 168 API calls (one per hour)
- ✅ Our approach: 1 API call (gets all data at once)

### Configuration

```yaml
historical_import:
  batch_size: 100  # InfluxDB write batch size
```

Adjust `batch_size` based on:
- InfluxDB performance
- Network latency
- Memory constraints

## When to Use

### ✅ Recommended Use Cases

1. **Initial Setup**: Seed database with historical data before starting regular collection
2. **Database Migration**: Repopulate after InfluxDB maintenance
3. **Gap Filling**: Recover data after extended downtime
4. **Testing**: Verify InfluxDB connection with real data

### ❌ Not Recommended

1. **Regular Updates**: Use systemd timer for ongoing collection
2. **Real-time Data**: Historical data is not current data
3. **Extending History**: API only provides limited historical window

## Limitations

### API Limitations

- **Historical Window**: Typically 7 days (168 hours)
- **Update Frequency**: Historical data doesn't extend further back over time
- **Data Availability**: Depends on Met Office DataHub API

### System Limitations

- **Single Location**: Imports data for configured location only
- **No Parallelization**: Sequential batch processing
- **Memory Usage**: ~1-2MB for typical dataset

## Troubleshooting

### Import Fails Immediately

```bash
# Check configuration
make test

# Verify config.yml exists and is valid
cat config.yml
```

### Partial Import (Some Failures)

Check InfluxDB:
```bash
# Verify InfluxDB is accessible
curl -I http://localhost:8086/health

# Check InfluxDB logs
journalctl -u influxdb -n 50
```

### No Data After Import

Verify in InfluxDB:
```bash
influx query 'from(bucket: "weather") 
  |> range(start: -7d) 
  |> filter(fn: (r) => r._measurement == "weather_observation")
  |> count()'
```

### Duplicate Data

InfluxDB handles this automatically:
- Data points with same timestamp are updated, not duplicated
- Safe to re-run import command

## Performance

### Expected Metrics

| Metric | Typical Value |
|--------|---------------|
| API Request Time | 2-5 seconds |
| Parsing Time | <1 second |
| InfluxDB Write Time | 20-40 seconds |
| **Total Time** | **30-60 seconds** |
| Data Points | 168 observations |
| API Calls | 1 |
| Memory Usage | ~2MB |

### Optimization

Already optimized:
- ✅ Single API request
- ✅ Batch writes to InfluxDB
- ✅ Minimal memory footprint
- ✅ Reuses existing retry logic

## Integration with Regular Collection

### Workflow

```bash
# 1. Setup
make setup
make config
# Edit config.yml

# 2. Test
make test

# 3. Import historical data (one-time)
make import-historical

# 4. Start regular collection
make install
make start
```

### Data Continuity

After historical import:
- Regular collection continues from current time
- No gaps between historical and current data
- InfluxDB provides seamless time-series queries

## Security Considerations

- Uses same security measures as regular collector
- Same API key and credentials
- Respects file permissions
- Logs don't contain sensitive data
- Single API call minimizes exposure

## Future Enhancements

Potential improvements (not currently implemented):

1. **Dry Run Mode**: Preview what will be imported
2. **Date Range Selection**: Import specific time periods
3. **Duplicate Detection**: Skip existing timestamps (optimization)
4. **Parallel Writes**: Concurrent InfluxDB writes
5. **Progress Bar**: Visual progress indicator
6. **Resume Support**: Continue from last successful point

## Support

For issues or questions:
1. Check `make logs` for detailed error messages
2. Verify configuration with `make test`
3. Review this documentation
4. Check CODE_REVIEW.md for security considerations

---

**Note**: This is a one-time import tool. For ongoing data collection, use the systemd timer (`make start`).
