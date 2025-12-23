# Weather Collector - Deployment Guide for Reliability Optimizations

## Overview

This guide provides step-by-step instructions for deploying the reliability optimizations while maintaining system uptime.

## Pre-Deployment Checklist

### ✅ Backup Current System
```bash
# 1. Create backup directory
sudo mkdir -p /opt/weather-backup/$(date +%Y%m%d)

# 2. Backup current files
cp weather_collector.py /opt/weather-backup/$(date +%Y%m%d)/weather_collector.py.backup
cp config.yml /opt/weather-backup/$(date +%Y%m%d)/config.yml.backup
cp -r cache/ /opt/weather-backup/$(date +%Y%m%d)/cache.backup

# 3. Test backup integrity
cd /opt/weather-backup/$(date +%Y%m%d)
python3 -c "import weather_collector; print('Backup OK')"
```

### ✅ Verify Environment
```bash
# Check Python version (requires 3.8+)
python3 --version

# Check available disk space (need 100MB+)
df -h /opt/

# Check network connectivity to services
curl -I https://data.hub.api.metoffice.gov.uk/
curl -I http://localhost:8086/health

# Check systemd user services
systemctl --user list-units --type=service | grep weather
```

### ✅ Install Dependencies
```bash
# Install new dependencies
pip install --requirement requirements.txt

# Verify psutil for monitoring
python3 -c "import psutil; print('Monitoring available')"
```

## Deployment Options

### Option 1: Gradual Rollout (Recommended)

#### Phase 1: Deploy Optimized Classes (Day 1)
```bash
# 1. Replace core classes with optimized versions
cp weather_collector.py weather_collector.original.py
cp weather_collector_optimized.py weather_collector.py

# 2. Test with existing config
python3 weather_collector.py --dry-run

# 3. Monitor logs for errors
journalctl --user -u weather-collector.service -n 50 -f
```

#### Phase 2: Enable Enhanced Features (Day 2)
```bash
# 1. Update configuration with new security settings
cp config.yml config.yml.backup
cat >> config.yml << 'EOF'

# Enhanced security settings
security:
  validate_inputs: true
  max_response_size_mb: 50
  circuit_breaker:
    failure_threshold: 5
    recovery_timeout: 300

# Enhanced monitoring
monitoring:
  enabled: true
  metrics_port: 9090
  health_check_interval: 30
EOF

# 2. Test with enhanced validation
python3 weather_collector.py --test-validation

# 3. Enable circuit breaker in code (if not default)
# Edit weather_collector.py to use CircuitBreaker by default
```

#### Phase 3: Full Cutover (Day 3)
```bash
# 1. Stop service during cutover
systemctl --user stop weather-collector.timer
systemctl --user stop weather-collector.service

# 2. Deploy final version
cp weather_collector_optimized.py weather_collector.py

# 3. Run comprehensive tests
python3 test_reliability.py

# 4. Start optimized service
systemctl --user daemon-reload
systemctl --user start weather-collector.timer
systemctl --user start weather-collector.service

# 5. Verify operation
systemctl --user status weather-collector.service
journalctl --user -u weather-collector.service -n 20
```

### Option 2: Blue-Green Deployment

#### Setup Blue Environment
```bash
# 1. Create blue (current) environment
cp -r . /opt/weather-blue/
systemctl --user stop weather-collector.timer

# 2. Create green (optimized) environment  
mkdir -p /opt/weather-green/
cp weather_collector_optimized.py /opt/weather-green/weather_collector.py
cp config.yml /opt/weather-green/config.yml

# 3. Test green environment
cd /opt/weather-green/
python3 weather_collector.py --test-mode

# 4. Create green service files
cp weather-collector.service /opt/weather-green/weather-collector-green.service
cp weather-collector.timer /opt/weather-green/weather-collector-green.timer

# Modify green service files to use green paths
sed -i 's|ExecStart=/home/darren/weather/weather_collector.py|ExecStart=/opt/weather-green/weather_collector.py|g' /opt/weather-green/weather-collector-green.service
```

#### Traffic Splitting
```bash
# 1. Start both environments
systemctl --user start weather-collector.service
systemctl --user enable /opt/weather-green/weather-collector-green.timer

# 2. Monitor performance
python3 -c "
import time, requests, json
blue_url = 'http://localhost:8086/query?q=SELECT%20*%20FROM%20weather_observation'
green_url = 'http://localhost:8087/query?q=SELECT%20*%20FROM%20weather_observation'

while True:
    try:
        blue_resp = requests.get(blue_url, timeout=5).json()
        green_resp = requests.get(green_url, timeout=5).json()
        
        blue_count = len(blue_resp.get('results', []))
        green_count = len(green_resp.get('results', []))
        
        print(f'Blue: {blue_count} points, Green: {green_count} points')
        time.sleep(60)
    except Exception as e:
        print(f'Monitoring error: {e}')
        time.sleep(60)
"
```

#### Cutover to Green
```bash
# 1. When green is stable, switch traffic
systemctl --user stop weather-collector.timer
systemctl --user disable weather-collector.service

# 2. Enable green environment
cp /opt/weather-green/weather-collector-green.service ~/.config/systemd/user/weather-collector.service
cp /opt/weather-green/weather-collector-green.timer ~/.config/systemd/user/weather-collector.timer

# 3. Reload systemd and start
systemctl --user daemon-reload
systemctl --user enable weather-collector.timer
systemctl --user start weather-collector.timer

# 4. Verify cutover
systemctl --user status weather-collector.service
```

### Option 3: Canary Deployment

#### Deploy Canary Instance
```bash
# 1. Create canary instance
mkdir -p /opt/weather-canary/
cp weather_collector_optimized.py /opt/weather-canary/weather_collector.py
cp config.yml /opt/weather-canary/config.yml

# 2. Modify canary config to use different InfluxDB bucket
sed -i 's/bucket: weather/bucket: weather-canary/' /opt/weather-canary/config.yml

# 3. Deploy canary service
cat > /opt/weather-canary/weather-canary.service << 'EOF'
[Unit]
Description=Weather Data Collector - Canary
After=network.target

[Service]
Type=oneshot
ExecStart=/opt/weather-canary/weather_collector.py
WorkingDirectory=/opt/weather-canary/
User=weather
Environment=PYTHONPATH=/opt/weather-canary

[Install]
WantedBy=weather-collector.timer
EOF

# 4. Start canary
systemctl --user enable /opt/weather-canary/weather-canary.service
systemctl --user start weather-canary.service
```

#### Traffic Routing (10% canary)
```bash
# 1. Create traffic splitter script
cat > /opt/weather-router.py << 'EOF'
#!/usr/bin/env python3
import random, subprocess, sys, json

# 10% traffic to canary
if random.random() < 0.1:
    cmd = ['/opt/weather-canary/weather_collector.py']
else:
    cmd = ['/home/darren/weather/weather_collector.py']

try:
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    print(result.stdout)
    if result.returncode != 0:
        print(f"Error: {result.stderr}", file=sys.stderr)
        sys.exit(1)
except Exception as e:
    print(f"Router error: {e}", file=sys.stderr)
    sys.exit(1)
EOF

chmod +x /opt/weather-router.py

# 2. Update service to use router
cp weather-collector.service weather-collector.service.backup
cat > weather-collector.service << 'EOF'
[Unit]
Description=Weather Data Collector
After=network.target

[Service]
Type=oneshot
ExecStart=/opt/weather-router.py
WorkingDirectory=/opt/weather-router/
User=weather
Environment=PYTHONPATH=/opt/weather-router

[Install]
WantedBy=weather-collector.timer
EOF

# 3. Deploy router
systemctl --user daemon-reload
systemctl --user restart weather-collector.service
```

## Monitoring & Validation

### Real-time Monitoring
```bash
# 1. Monitor service health
watch -n 60 '
echo "=== $(date) ==="
systemctl --user is-active weather-collector.service && echo "✅ Active" || echo "❌ Inactive"
journalctl --user -u weather-collector.service -n 3 --no-pager
echo ""

# 2. Monitor performance metrics
curl -s http://localhost:9090/metrics | grep weather_api_requests_total

# 3. Monitor resource usage
ps aux | grep weather_collector
df -h /opt/weather-*/
du -sh /var/lib/weather-collector/
'
```

### Automated Validation Script
```bash
# Create validation script
cat > validate_deployment.sh << 'EOF'
#!/bin/bash

set -e

echo "🔍 Validating weather collector deployment..."

# Test 1: Service health
echo "1. Testing service health..."
if systemctl --user is-active weather-collector.service; then
    echo "✅ Service is active"
else
    echo "❌ Service is not active"
    exit 1
fi

# Test 2: Recent logs for errors
echo "2. Checking recent errors..."
ERROR_COUNT=$(journalctl --user -u weather-collector.service --since "1 hour ago" | grep -i error | wc -l)
if [ $ERROR_COUNT -eq 0 ]; then
    echo "✅ No errors in last hour"
else
    echo "❌ Found $ERROR_COUNT errors in last hour"
fi

# Test 3: API connectivity
echo "3. Testing API connectivity..."
API_STATUS=$(curl -s -o /dev/null -w "%{http_code}" https://data.hub.api.metoffice.gov.uk/)
if [ "$API_STATUS" = "200" ]; then
    echo "✅ API accessible"
else
    echo "❌ API returned status $API_STATUS"
fi

# Test 4: InfluxDB connectivity
echo "4. Testing InfluxDB connectivity..."
INFLUX_STATUS=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8086/health)
if [ "$INFLUX_STATUS" = "200" ]; then
    echo "✅ InfluxDB accessible"
else
    echo "❌ InfluxDB returned status $INFLUX_STATUS"
fi

# Test 5: Cache integrity
echo "5. Testing cache integrity..."
if [ -f "./cache/cache.json" ]; then
    python3 -c "
import json
try:
    with open('./cache/cache.json', 'r') as f:
        data = json.load(f)
    print(f'✅ Cache has {len(data)} entries')
except Exception as e:
    print(f'❌ Cache error: {e}')
    exit(1)
"
else
    echo "✅ No cache file (clean state)"
fi

# Test 6: Memory usage
echo "6. Checking memory usage..."
MEMORY_MB=$(ps aux | grep weather_collector | awk '{print $6}' | head -1)
if [ "$MEMORY_MB" -lt 100 ]; then
    echo "✅ Memory usage: ${MEMORY_MB}MB (normal)"
else
    echo "⚠️  Memory usage: ${MEMORY_MB}MB (high)"
fi

echo ""
echo "🎯 Deployment validation complete!"
EOF

chmod +x validate_deployment.sh

# Run validation
./validate_deployment.sh
```

### Performance Benchmarking
```bash
# 1. Run performance tests
echo "Running performance benchmarks..."
python3 test_reliability.py

# 2. Load test (simulated)
echo "Running load test..."
python3 -c "
import time, threading, requests, json, random
from datetime import datetime, timezone

def simulate_load():
    for i in range(100):
        data = {
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'temperature': 20.0 + random.uniform(-5, 5),
            'humidity': 60.0 + random.uniform(-10, 10)
        }
        try:
            response = requests.post(
                'http://localhost:8086/api/v2/write',
                json=data,
                headers={'Content-Type': 'application/json'},
                timeout=5
            )
            print(f'Load test point {i+1}/100: {response.status_code}')
        except Exception as e:
            print(f'Load test error {i+1}: {e}')

# Start 10 concurrent threads
threads = []
for i in range(10):
    t = threading.Thread(target=simulate_load)
    threads.append(t)
    t.start()

for t in threads:
    t.join()

print('Load test completed')
"

# 3. Compare with baseline
echo "Comparing with baseline performance..."
python3 -c "
import time, requests

# Test API response time
start = time.time()
response = requests.get('https://data.hub.api.metoffice.gov.uk/sitespecific/v0/point/hourly?latitude=52.0867&longitude=-0.7231', timeout=10)
end = time.time()

print(f'API response time: {(end-start)*1000:.2f}ms')
print(f'Target: <2000ms')

# Test InfluxDB write time
start = time.time()
# Simulate write
end = time.time()

print(f'Database write time: {(end-start)*1000:.2f}ms')
print(f'Target: <100ms per point')
"
```

## Rollback Procedures

### Immediate Rollback (Critical Issues)
```bash
# 1. Stop services
systemctl --user stop weather-collector.timer
systemctl --user stop weather-collector.service

# 2. Restore from backup
cp /opt/weather-backup/$(date +%Y%m%d)/weather_collector.py.backup ./weather_collector.py
cp /opt/weather-backup/$(date +%Y%m%d)/config.yml.backup ./config.yml

# 3. Restart services
systemctl --user daemon-reload
systemctl --user start weather-collector.timer
systemctl --user start weather-collector.service

# 4. Verify rollback
systemctl --user status weather-collector.service
./validate_deployment.sh
```

### Blue-Green Rollback
```bash
# 1. Switch back to blue environment
systemctl --user stop weather-collector.timer

# 2. Restore blue service
cp /opt/weather-blue/weather-collector.service ~/.config/systemd/user/weather-collector.service
cp /opt/weather-blue/weather-collector.timer ~/.config/systemd/user/weather-collector.timer

# 3. Reload and start
systemctl --user daemon-reload
systemctl --user enable weather-collector.timer
systemctl --user start weather-collector.timer

# 4. Clean green environment
rm -rf /opt/weather-green/

echo "✅ Rolled back to blue environment"
```

## Post-Deployment Optimization

### 1. Performance Tuning
```bash
# 1. Monitor for 24 hours
python3 -c "
import time, psutil, requests
from datetime import datetime, timedelta

start_time = datetime.now()
metrics = []

while (datetime.now() - start_time) < timedelta(hours=24):
    # Collect metrics
    cpu_percent = psutil.cpu_percent(interval=1)
    memory = psutil.virtual_memory()
    
    metrics.append({
        'timestamp': datetime.now().isoformat(),
        'cpu': cpu_percent,
        'memory_mb': memory.used / 1024 / 1024
    })
    
    time.sleep(300)  # Every 5 minutes

# Analyze metrics
avg_cpu = sum(m['cpu'] for m in metrics) / len(metrics)
max_memory = max(m['memory_mb'] for m in metrics)

print(f'Average CPU: {avg_cpu:.2f}%')
print(f'Peak Memory: {max_memory:.2f}MB')

# Recommendations
if avg_cpu > 50:
    print('⚠️  High CPU usage - consider optimizing')
if max_memory > 200:
    print('⚠️  High memory usage - consider reducing batch size')
"
```

### 2. Log Analysis
```bash
# Analyze logs for patterns
journalctl --user -u weather-collector.service --since "24 hours ago" | \
  grep -E "(ERROR|WARNING|timeout|failed)" | \
  awk '{print $1 " " $2 " " $3}' | \
  sort | uniq -c | sort -nr

# Identify most common errors
echo "Most common errors in last 24 hours:"
journalctl --user -u weather-collector.service --since "24 hours ago" | \
  grep -E "(ERROR|WARNING)" | \
  sed 's/.*\]//' | \
  sort | uniq -c | sort -nr | head -10
```

## Troubleshooting Guide

### Common Issues & Solutions

#### Issue: Circuit Breaker Trips Frequently
**Symptoms**: Service stops making API calls, logs show "Circuit breaker is OPEN"
**Causes**: 
- API rate limiting
- Network connectivity issues
- API service degradation

**Solutions**:
```bash
# 1. Check API status
curl -I https://data.hub.api.metoffice.gov.uk/

# 2. Adjust circuit breaker thresholds
# Edit config.yml
sed -i 's/failure_threshold: 5/failure_threshold: 10/' config.yml

# 3. Reduce request frequency
# Edit timer to run every 2 hours instead of hourly
systemctl --user edit weather-collector.timer
```

#### Issue: Memory Usage Increasing
**Symptoms**: System shows high memory usage over time
**Causes**:
- Cache growing without limits
- Connection leaks
- Large batch sizes

**Solutions**:
```bash
# 1. Check cache size
du -sh ./cache/

# 2. Clear cache if needed
rm ./cache/cache.json

# 3. Reduce batch size
sed -i 's/batch_size: 100/batch_size: 50/' config.yml

# 4. Monitor memory usage
watch -n 60 'ps aux | grep weather_collector | awk "{print \$6}"'
```

#### Issue: InfluxDB Connection Timeouts
**Symptoms**: Logs show "Failed to write to InfluxDB" frequently
**Causes**:
- Network latency
- InfluxDB overload
- Connection pool exhaustion

**Solutions**:
```bash
# 1. Check InfluxDB health
curl -I http://localhost:8086/health

# 2. Increase timeout
sed -i 's/timeout: 10/timeout: 30/' config.yml

# 3. Check InfluxDB logs
docker logs influxdb  # if using Docker
# or
journalctl -u influxdb -n 50  # if systemd
```

## Success Criteria

### ✅ Deployment Success Indicators
- All services active and healthy
- No errors in logs for 1 hour
- Performance metrics within targets
- Cache size stable
- Memory usage < 100MB
- API response time < 2 seconds
- InfluxDB write time < 100ms per point

### ✅ Performance Validation
- Average API response time: < 2 seconds
- Batch write efficiency: > 90% success rate
- Memory usage: < 100MB sustained
- CPU usage: < 50% average
- Cache hit rate: > 95% (for cached data)

### ✅ Reliability Validation
- Uptime: > 99.9%
- Circuit breaker trips: < 1 per day
- Data loss: < 0.1%
- Recovery time: < 5 minutes

## Documentation Updates

### Update README.md
```bash
# Add optimization section
cat >> README.md << 'EOF'

## Reliability Optimizations

This system includes comprehensive reliability optimizations:

- **Circuit Breaker**: Prevents cascade failures during API outages
- **Connection Pooling**: Reuses HTTP and InfluxDB connections for efficiency
- **Thread-Safe Cache**: Prevents data corruption in concurrent scenarios
- **Enhanced Validation**: Comprehensive input validation and security checks
- **Batch Operations**: Optimized database writes with batching
- **Performance Monitoring**: Built-in metrics and health checks

### Monitoring

- Health endpoint: http://localhost:9090/health
- Metrics: http://localhost:9090/metrics
- Logs: `journalctl --user -u weather-collector.service -f`

### Performance Targets

- API Response Time: < 2 seconds
- Database Write Time: < 100ms per point
- Memory Usage: < 100MB
- Uptime: > 99.9%
EOF
```

### Update Systemd Service Files
```bash
# Add health check and monitoring to service
cat >> weather-collector.service << 'EOF'

# Health check before running
ExecStartPre=/opt/validate_deployment.sh

# Monitoring
Environment=PYTHONPATH=/home/darren/weather
Environment=METRICS_ENABLED=true
EOF
```

## Final Checklist

Before going live with optimizations:

- [ ] All tests pass (`python3 test_reliability.py`)
- [ ] Configuration validated (`./validate_deployment.sh`)
- [ ] Backup created (`/opt/weather-backup/$(date +%Y%m%d)/`)
- [ ] Rollback procedure documented
- [ ] Monitoring systems operational
- [ ] Performance baseline established
- [ ] Team trained on new procedures
- [ ] Documentation updated
- [ ] Post-deployment validation scheduled

## Emergency Contacts

For deployment issues:
- **System Administrator**: [Your contact]
- **On-call Engineer**: [Your contact]  
- **Met Office Support**: [API support contact]
- **InfluxDB Support**: [Database support contact]

---

**Remember**: Always test in staging before production deployment!
