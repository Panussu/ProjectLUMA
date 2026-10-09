#!/usr/bin/env python3
"""
ProjectLUMA - Backend Log Viewer
Allows viewing and real-time streaming (tail -f) of backend logs.
"""
import argparse
import os
import sys
import time
from pathlib import Path

# ANSI color codes for terminal formatting
COLORS = {
    "RESET": "\033[0m",
    "RED": "\033[91m",
    "YELLOW": "\033[93m",
    "GREEN": "\033[92m",
    "CYAN": "\033[96m",
    "MAGENTA": "\033[95m",
    "GRAY": "\033[90m",
    "WHITE": "\033[97m",
}


def colorize(line: str) -> str:
    line_upper = line.upper()
    if any(k in line_upper for k in ("ERROR", "CRITICAL", "TRACEBACK", "EXCEPTION")):
        return f"{COLORS['RED']}{line}{COLORS['RESET']}"
    if any(k in line_upper for k in ("WARNING", "WARN")):
        return f"{COLORS['YELLOW']}{line}{COLORS['RESET']}"
    if " 200 " in line or " 201 " in line or " 204 " in line:
        return f"{COLORS['GREEN']}{line}{COLORS['RESET']}"
    if any(code in line for code in (" 401 ", " 403 ", " 404 ", " 500 ")):
        return f"{COLORS['MAGENTA']}{line}{COLORS['RESET']}"
    if "[INFO]" in line or "INFO" in line:
        return f"{COLORS['GRAY']}{line}{COLORS['RESET']}"
    return line


def main():
    parser = argparse.ArgumentParser(description="View ProjectLUMA backend logs")
    parser.add_argument("-n", "--lines", type=int, default=50, help="Number of recent lines to display (default: 50)")
    parser.add_argument("--no-follow", action="store_true", help="Print recent lines and exit without streaming")
    parser.add_argument("-f", "--filter", type=str, default="", help="Filter log lines by substring")
    parser.add_argument("--errors", action="store_true", help="Show only errors and exceptions")
    parser.add_argument("--clear", action="store_true", help="Clear the log file")
    args = parser.parse_args()

    backend_dir = Path(__file__).resolve().parent
    log_dir = backend_dir / "logs"
    log_file = log_dir / "backend.log"

    log_dir.mkdir(parents=True, exist_ok=True)

    if args.clear:
        if log_file.exists():
            log_file.write_text("", encoding="utf-8")
            print(f"{COLORS['GREEN']}Log file cleared: {log_file}{COLORS['RESET']}")
        else:
            print("Log file does not exist.")
        return

    if not log_file.exists():
        log_file.touch()

    file_size_kb = round(log_file.stat().st_size / 1024, 2)
    print(f"{COLORS['CYAN']}=========================================================={COLORS['RESET']}")
    print(f"{COLORS['CYAN']}               ProjectLUMA - Backend Logs                 {COLORS['RESET']}")
    print(f"{COLORS['CYAN']}=========================================================={COLORS['RESET']}")
    print(f"Log File:  {log_file}")
    print(f"File Size: {file_size_kb} KB")
    if args.filter:
        print(f"Filter:    '{args.filter}'")
    if args.errors:
        print(f"Mode:      Errors only")
    if not args.no_follow:
        print(f"Stream:    Real-time (Press Ctrl+C to exit)")
    print("-" * 58)

    def line_matches(line: str) -> bool:
        if args.filter and args.filter.lower() not in line.lower():
            return False
        if args.errors and not any(k in line.upper() for k in ("ERROR", "CRITICAL", "TRACEBACK", "EXCEPTION")):
            return False
        return True

    # Read existing lines
    with log_file.open("r", encoding="utf-8", errors="replace") as f:
        existing = f.readlines()
        recent = existing[-args.lines :] if len(existing) > args.lines else existing
        for line in recent:
            stripped = line.rstrip("\r\n")
            if line_matches(stripped):
                print(colorize(stripped))

        if args.no_follow:
            return

        # Follow mode (tail -f)
        try:
            while True:
                line = f.readline()
                if line:
                    stripped = line.rstrip("\r\n")
                    if line_matches(stripped):
                        print(colorize(stripped))
                else:
                    time.sleep(0.3)
        except KeyboardInterrupt:
            print(f"\n{COLORS['CYAN']}Stopped viewing logs.{COLORS['RESET']}")


if __name__ == "__main__":
    main()
