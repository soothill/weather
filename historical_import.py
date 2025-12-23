#!/usr/bin/env python3
"""
Historical Weather Data Importer
One-time import of all available historical weather data from Met Office DataHub.

IMPORTANT:
- This project uses the `observation-land/1/{geohash}` endpoint, which returns a list
  of observations covering a limited historical window (typically ~48 hours).
- This importer will fetch that list and write *every* observation into InfluxDB.

Copyright (c) 2025 Darren Soothill
Email: darren [at] soothill [dot] com
All rights reserved.
"""

import sys
import logging
from datetime import datetime
from typing import List, Dict, Any

# Import from main weather collector
from weather_collector import Config, MetOfficeClient, InfluxDBWriter


class HistoricalDataParser:
    """Parser for extracting ALL available observations from the observation-land API response."""

    def __init__(self, location: Dict[str, Any]):
        self.location = location

    @staticmethod
    def _parse_dt(dt: str) -> datetime:
        return datetime.fromisoformat(dt.replace("Z", "+00:00"))

    def parse_all_observations(self, raw_data: Any) -> List[Dict[str, Any]]:
        """Parse ALL entries from the raw observation list."""
        try:
            if not isinstance(raw_data, list) or not raw_data:
                logging.error(
                    "Historical import expected a list of observations from observation-land endpoint"
                )
                return []

            observations_with_dt = [
                o for o in raw_data if isinstance(o, dict) and o.get("datetime")
            ]
            if not observations_with_dt:
                logging.error("No observations with a 'datetime' field found")
                return []

            all_observations: List[Dict[str, Any]] = []
            for obs in observations_with_dt:
                ts = obs.get("datetime")
                if not ts:
                    continue

                # Normalize to Z-ulu format
                ts_norm = self._parse_dt(ts).isoformat().replace("+00:00", "Z")

                parsed_data = {
                    "timestamp": ts_norm,
                    "location_name": self.location.get("name", "Unknown"),
                    "latitude": self.location["latitude"],
                    "longitude": self.location["longitude"],
                    # Field mapping for observation-land endpoint
                    "temperature": obs.get("temperature"),
                    "humidity": obs.get("humidity"),
                    "msl_pressure": obs.get("mslp"),
                    "pressure_tendency": obs.get("pressure_tendency"),
                    "visibility": obs.get("visibility"),
                    "weather_code": obs.get("weather_code"),
                    "wind_direction": obs.get("wind_direction"),
                    "wind_gust": obs.get("wind_gust"),
                    "wind_speed": obs.get("wind_speed"),
                }

                # Remove None values
                parsed_data = {k: v for k, v in parsed_data.items() if v is not None}

                if parsed_data.get("timestamp"):
                    all_observations.append(parsed_data)

            # Sort by actual datetime (oldest first)
            all_observations.sort(key=lambda x: self._parse_dt(x["timestamp"]))

            if all_observations:
                first = all_observations[0]["timestamp"]
                last = all_observations[-1]["timestamp"]
                logging.info(f"Date range: {first} to {last}")
                logging.info(f"Total points parsed: {len(all_observations)}")

            return all_observations

        except Exception as e:
            logging.error(f"Error parsing historical data: {e}")
            return []


class HistoricalImporter:
    """Main orchestrator for historical data import."""

    def __init__(self, config_path: str = "config.yml"):
        self.config = Config(config_path)
        self._setup_logging()

        self.met_office = MetOfficeClient(self.config)
        self.influxdb = InfluxDBWriter(self.config)
        self.parser = HistoricalDataParser(self.config.get("met_office", "location"))

        # Get batch size from config or use default
        self.batch_size = self.config.get("historical_import", "batch_size") or 100

    def _setup_logging(self):
        """Configure logging"""
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s - %(levelname)s - %(message)s",
            handlers=[logging.StreamHandler(sys.stdout)],
        )

    def batch_write_to_influxdb(self, observations: List[Dict[str, Any]]) -> Dict[str, int]:
        """Write observations to InfluxDB in batches for efficiency using true batch writes."""
        total = len(observations)
        successful = 0
        failed = 0

        logging.info(
            f"Writing {total} observations to InfluxDB in batches of {self.batch_size}..."
        )

        for i in range(0, total, self.batch_size):
            batch = observations[i : i + self.batch_size]
            batch_num = (i // self.batch_size) + 1
            total_batches = (total + self.batch_size - 1) // self.batch_size

            logging.info(
                f"Processing batch {batch_num}/{total_batches} ({len(batch)} points)..."
            )

            # Use true batch write
            result = self.influxdb.write_batch(batch)
            successful += result['successful']
            failed += result['failed']

            logging.info(
                f"✓ Batch {batch_num}/{total_batches}: {result['successful']}/{len(batch)} points written"
            )

        return {"total": total, "successful": successful, "failed": failed}

    def import_historical_data(self) -> int:
        """Main import workflow"""
        print("=" * 60)
        print("Historical Weather Data Import")
        print("=" * 60)
        print()

        # Step 1: Fetch historical data from observation-land API
        print("→ Fetching all available historical data from Met Office API...")
        raw_data = self.met_office.fetch_weather_data()

        if raw_data is None:
            logging.error("Failed to fetch historical data from Met Office API")
            return 1

        # Step 2: Parse ALL observations from the response list
        print("→ Parsing historical observations...")
        observations = self.parser.parse_all_observations(raw_data)

        if not observations:
            logging.error("No observations found in API response")
            return 1

        print(f"✓ Retrieved {len(observations)} hourly observations")
        print(f"✓ Date range: {observations[0]['timestamp']} to {observations[-1]['timestamp']}")
        print()

        # Step 3: Batch write to InfluxDB
        print("→ Importing to InfluxDB...")
        stats = self.batch_write_to_influxdb(observations)

        print()
        print("=" * 60)
        print("Import Complete!")
        print("=" * 60)
        print(f"✓ Total observations:    {stats['total']}")
        print(f"✓ Successfully imported: {stats['successful']}")

        if stats["failed"] > 0:
            print(f"✗ Failed:               {stats['failed']}")
            logging.warning(f"{stats['failed']} observations failed to import")

        print()

        if stats["successful"] == stats["total"]:
            logging.info("All available historical data imported successfully!")
            return 0

        logging.error(f"Import completed with {stats['failed']} failures")
        return 1


def main():
    """Main entry point"""
    try:
        importer = HistoricalImporter()
        sys.exit(importer.import_historical_data())
    except KeyboardInterrupt:
        logging.info("\nImport interrupted by user")
        sys.exit(130)
    except Exception as e:
        logging.error(f"Unexpected error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
