# Weather Data Collector

An automated weather data collection system that fetches hourly weather observations from the Met Office DataHub and stores them in InfluxDB v2. Features resilient error handling with local caching fallback, exponential backoff retry logic, and optimized batch writes.

**Copyright (c) 2025 Darren Soothill**  
**Email:** darren [at] soothill [dot] com  
**All rights reserved.**

## Features

- 🌤️ **Met Office Integration**: Fetches weather data from Met Office DataHub Observation API
- 📊 **InfluxDB v2 Storage**: Stores time-series weather data in InfluxDB with batch writes
- 💾 **Local Cache Fallback**: Automatically caches data locally when InfluxDB is unavailable
- 🔄 **Auto-Recovery**: Uploads cached data in batches when InfluxDB becomes available again
- ⚡ **Optimized Performance**: Batch writes significantly improve cache recovery and import speeds
- ⏰ **Systemd Timer**: Automated hourly collection using systemd
- 🔁 **Exponential Backoff**: Configurable retry logic with increasing delays
- ⏱️ **Request Timeouts**: All HTTP requests have configurable timeouts
- 📝 **Comprehensive Logging**: Detailed logging to systemd journal
- 🔒 **Secure**: Sensitive configuration kept in git-ignored files

## Weather Parameters Collected

- Temperature
- Humidity (relative humidity)
- Wind (speed, direction, gusts)
- Pressure (mean sea level pressure, pressure tendency)
- Visibility
- Weather code

## Prerequisites

- Python 3.8 or higher
- systemd (for automated collection)
- InfluxDB v2 instance
- Met Office DataHub API key
- Linux system with systemd

## Quick Start

### 1. Clone and Setup

```bash
cd /home/darren/weather
make setup
```

This will:
- Create a Python virtual environment
- Install all required dependencies

### 2. Get Your Met Office API Key

```bash
make api-key-info
```

Follow the displayed instructions to:
1. Register at https://datahub.metoffice.gov.uk/
2. Create an API key for "Site Specific" API
3. Copy your API key

### 3. Configure

```bash
make config
```

Edit `config.yml` and configure:
- **met_office.api_key**: Your Met Office API key
- **met_office.location**: Your location coordinates (default: Newport Pagnell)
- **influxdb.url**: Your InfluxDB URL
- **influxdb.org**: Your InfluxDB organization
- **influxdb.bucket**: Your InfluxDB bucket name
- **influxdb.token**: Your InfluxDB authentication token

### 4. Test

```bash
make test
```

Run a manual collection to verify everything works correctly.

### 5. Import Historical Data (Optional)

```bash
make import-historical
```

This one-time command imports all available historical weather data from Met Office API:
- **API Efficient**: Uses geohash to fetch location-specific data
- **Bulk Import**: Imports available historical observations (typically ~48 hours)
- **Fast Batch Writes**: Optimized batch writes complete in seconds
- **Safe**: Can be re-run without creating duplicates (InfluxDB handles timestamps)

Example output:
```
Historical Weather Data Import

→ Fetching all available historical data from Met Office API...
→ Parsing historical observations...
✓ Retrieved 48 hourly observations
✓ Date range: 2024-12-15T00:00:00Z to 2024-12-17T00:00:00Z

→ Importing to InfluxDB...
✓ Batch 1/1: 48 points written

Import Complete!
✓ Total observations:    48
✓ Successfully imported: 48
```

### 6. Install and Start

```bash
make install
make start
```

The weather collector will now run automatically every hour!

## Makefile Commands

### Setup Commands
- `make setup` - Create virtual environment and install dependencies
- `make config` - Create configuration file from template
- `make api-key-info` - Show instructions for obtaining Met Office API key

### Installation Commands
- `make install` - Install systemd service and timer (user mode)
- `make start` - Enable and start the timer

### Management Commands
- `make stop` - Stop and disable the timer
- `make restart` - Restart the timer
- `make status` - Show service and timer status
- `make logs` - Show recent logs from the service

### Testing Commands
- `make test` - Run a single data collection manually

### Cleanup Commands
- `make uninstall` - Remove systemd service and timer
- `make clean` - Remove virtual environment and cache

## Configuration

### Met Office Configuration

```yaml
met_office:
  api_key: "YOUR_API_KEY"
  base_url: "https://data.hub.api.metoffice.gov.uk"
  location:
    name: "Newport Pagnell"
    latitude: 52.0867
    longitude: -0.7231
  timeout: 30
  retry:
    max_attempts: 5
    initial_backoff: 5
    max_backoff: 160
    max_total_time: 300
```

### InfluxDB Configuration

```yaml
influxdb:
  url: "http://localhost:8086"
  org: "your-org"
  bucket: "weather"
  token: "YOUR_TOKEN"
  timeout: 10
  retry:
    max_attempts: 3
    initial_backoff: 2
    max_backoff: 8
```

### Cache Configuration

```yaml
cache:
  file_path: "/var/lib/weather-collector/cache.json"
```

## How It Works

### Collection Process

1. **Fetch Data**: Connects to Met Office DataHub API with your location coordinates
2. **Parse Response**: Extracts weather parameters from JSON response
3. **Write to InfluxDB**: Attempts to store data in InfluxDB with retry logic
4. **Fallback to Cache**: If InfluxDB fails, saves data to local JSON file
5. **Auto-Recovery**: On next successful InfluxDB connection, uploads cached data

### Retry Logic

#### Met Office API
- **Max attempts**: 5 (configurable)
- **Initial backoff**: 5 seconds
- **Backoff strategy**: Exponential (doubles each retry)
- **Max backoff**: 160 seconds
- **Max total time**: 300 seconds (5 minutes)

#### InfluxDB
- **Max attempts**: 3 (configurable)
- **Initial backoff**: 2 seconds
- **Backoff strategy**: Exponential
- **Max backoff**: 8 seconds

### Error Handling

- **401/403 Errors**: No retry (authentication/permission issues)
- **4xx Errors**: No retry (client errors)
- **5xx Errors**: Retry with backoff (server errors)
- **Timeouts**: Retry with backoff
- **Connection Errors**: Retry with backoff

## Systemd Integration

### Service Unit (`weather-collector.service`)
- **Type**: oneshot (runs and exits)
- **Runs as**: Current user
- **Working Directory**: `/home/darren/weather`
- **Logging**: Outputs to systemd journal

### Timer Unit (`weather-collector.timer`)
- **Schedule**: Hourly (on the hour)
- **Persistent**: Catches up on missed runs after system boot
- **RandomizedDelay**: 60 seconds to avoid load spikes

## Viewing Logs

```bash
# Recent logs
make logs

# Follow live logs
journalctl --user -u weather-collector.service -f

# Logs from specific time
journalctl --user -u weather-collector.service --since "1 hour ago"

# All logs
journalctl --user -u weather-collector.service --no-pager
```

## Checking Status

```bash
# Overall status
make status

# Timer status only
systemctl --user status weather-collector.timer

# Service status only
systemctl --user status weather-collector.service

# List next scheduled runs
systemctl --user list-timers weather-collector.timer
```

## InfluxDB Data Structure

### Measurement
- `weather_observation`

### Tags
- `location`: Location name (e.g., "Newport Pagnell")
- `source`: Always "met_office"

### Fields
All numeric weather parameters as fields:
- `screen_temperature`
- `screen_relative_humidity`
- `wind_speed_10m`
- `wind_direction_10m`
- `msl_pressure`
- `precipitation_rate`
- `visibility`
- And more...

### Timestamp
Uses the observation time from Met Office API

## Troubleshooting

### Configuration Issues

```bash
# Verify config exists
ls -l config.yml

# Test configuration
make test
```

### API Issues

```bash
# Check if API key is valid
curl -H "apikey: YOUR_API_KEY" \
  "https://data.hub.api.metoffice.gov.uk/sitespecific/v0/point/hourly?latitude=52.0867&longitude=-0.7231"
```

### InfluxDB Issues

```bash
# Verify InfluxDB is accessible
curl -I http://localhost:8086/health

# Check cache for unsent data
cat /var/lib/weather-collector/cache.json
```

### Service Issues

```bash
# Check service status
make status

# View detailed logs
make logs

# Restart service
make restart

# Run manual test
make test
```

## Cache Management

When InfluxDB is unavailable, data is cached at:
```
/var/lib/weather-collector/cache.json
```

The cache is automatically processed and cleared when InfluxDB becomes available again.

## Security Notes

- `config.yml` is automatically excluded from git via `.gitignore`
- Never commit your API keys or tokens to version control
- The systemd service runs with limited privileges
- Cache directory has restricted permissions

## File Structure

```
weather/
├── weather_collector.py      # Main Python script
├── requirements.txt           # Python dependencies
├── config.sample.yml          # Configuration template
├── config.yml                 # Your configuration (git-ignored)
├── .gitignore                # Git ignore rules
├── Makefile                  # Automation commands
├── README.md                 # This file
├── weather-collector.service # Systemd service unit
└── weather-collector.timer   # Systemd timer unit
```

## Uninstalling

```bash
# Stop and remove systemd units
make uninstall

# Remove virtual environment and cache
make clean

# Manually remove config if needed
rm config.yml
```

## Contributing

Feel free to submit issues and enhancement requests!

## License

This project is provided as-is for personal use.

## Acknowledgments

- Weather data provided by Met Office DataHub
- Uses InfluxDB v2 for time-series storage
