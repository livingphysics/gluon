#!/usr/bin/env python3
"""
Quickly extract timestamps and OD readings from bioreactor.log.

Usage:
  python extract_od_from_log.py [path/to/bioreactor.log] [output.csv]

Outputs CSV to stdout with columns: timestamp,<dynamic OD channel headers>.
OD channel headers are discovered from lines containing “OD measurement complete” and use the
channel names as they appear (e.g., channel 90, channel 135, channel Ref).
Values are taken from “avg voltage” fields on those lines. Non-OD fields are ignored.
"""

import csv
import re
import sys
from pathlib import Path


def parse_log(path: Path):
    """
    Yield (timestamp, {channel: value}) for each OD measurement line.
    
    Looks for lines like:
      "... OD measurement complete: ... channel 90 ... avg voltage: 0.1234V"
    """
    ts_pattern = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3})")
    # channel name captured, then avg voltage value
    od_pattern = re.compile(r"channel\s+([A-Za-z0-9_]+)[^A]*?avg voltage:\s*([-\d\.NaInf]+)", re.IGNORECASE)

    channels_seen = set()
    rows = []

    with path.open("r", errors="ignore") as f:
        for line in f:
            if "OD measurement complete" not in line:
                continue

            ts_match = ts_pattern.search(line)
            if not ts_match:
                continue
            ts = ts_match.group(1)

            od_matches = od_pattern.findall(line)
            if not od_matches:
                continue

            row = {"timestamp": ts}
            for ch_raw, val_raw in od_matches:
                ch = ch_raw.strip()
                header = f"channel {ch}"
                channels_seen.add(header)
                try:
                    val = float(val_raw)
                except ValueError:
                    try:
                        val = float("nan")
                    except Exception:
                        val = val_raw
                row[header] = val
            rows.append(row)

    return rows, sorted(channels_seen)


def main():
    log_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("src/bioreactor.log")
    out_path = Path(sys.argv[2]) if len(sys.argv) > 2 else None

    if not log_path.exists():
        sys.stderr.write(f"Log not found: {log_path}\n")
        sys.exit(1)

    rows, channels = parse_log(log_path)
    if not rows:
        sys.stderr.write("No OD readings found.\n")
        sys.exit(1)

    headers = ["timestamp"] + channels

    if out_path:
        with out_path.open("w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=headers)
            writer.writeheader()
            for row in rows:
                writer.writerow({h: row.get(h, "") for h in headers})
    else:
        writer = csv.DictWriter(sys.stdout, fieldnames=headers)
        writer.writeheader()
        for row in rows:
            writer.writerow({h: row.get(h, "") for h in headers})


if __name__ == "__main__":
    main()
