#!/usr/bin/env python3
"""
collect.py — SSH into a list of Arista devices and collect CLI output.

Usage:
    python3 collect.py                        # runs default command list
    python3 collect.py "show ip bgp detail"   # run a single command
    python3 collect.py -c commands.txt        # run commands from a file

Device list: devices.txt (one hostname/IP per line, # for comments)
Output:      output/<hostname>_<sanitized_command>.txt

VRF note:
    Default command is 'show ip bgp detail vrf all' which covers all VRFs on EOS.
    If your devices don't support 'vrf all', use:
        python3 collect.py "show ip bgp detail"
    or specify per-VRF commands in a commands.txt file.
"""

import argparse
import getpass
import os
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

try:
    from netmiko import ConnectHandler, NetmikoTimeoutException, NetmikoAuthenticationException
except ImportError:
    print("ERROR: netmiko not installed. Run: pip install netmiko")
    sys.exit(1)

OUTPUT_DIR = "output"

# Primary command — 'vrf all' gets default + all named VRFs in one shot on EOS.
# If a device doesn't support it, the script will warn you and save the error output.
DEFAULT_COMMANDS = [
    "show ip bgp detail vrf all",
]


def load_devices(path="devices.txt"):
    if not os.path.exists(path):
        print(f"ERROR: Device list '{path}' not found.")
        print("Create devices.txt with one hostname or IP per line.")
        sys.exit(1)
    devices = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                devices.append(line)
    if not devices:
        print("ERROR: No devices found in devices.txt")
        sys.exit(1)
    return devices


def sanitize(cmd):
    """Convert a command string to a safe filename component."""
    return re.sub(r"[^a-z0-9]+", "_", cmd.lower()).strip("_")


def collect_device(host, username, password, commands, timeout=30):
    """Connect to a single device and run all commands. Returns (host, results, error)."""
    results = {}
    try:
        conn = ConnectHandler(
            device_type="arista_eos",
            host=host,
            username=username,
            password=password,
            timeout=timeout,
            session_log=None,
        )
        for cmd in commands:
            output = conn.send_command(cmd, read_timeout=90)
            # Flag EOS % errors (e.g. vrf all not supported) so caller can warn
            if output.strip().startswith("%"):
                results[cmd] = output
                results[f"__error__{cmd}"] = output.strip()
            else:
                results[cmd] = output
        conn.disconnect()
        return host, results, None
    except NetmikoAuthenticationException:
        return host, {}, "Authentication failed"
    except NetmikoTimeoutException:
        return host, {}, "Connection timed out"
    except Exception as e:
        return host, {}, str(e)


def save_output(host, cmd, output, timestamp):
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    filename = f"{host}_{sanitize(cmd)}.txt"
    filepath = os.path.join(OUTPUT_DIR, filename)
    with open(filepath, "w") as f:
        f.write(f"# Host:      {host}\n")
        f.write(f"# Command:   {cmd}\n")
        f.write(f"# Collected: {timestamp}\n")
        f.write("#" + "-" * 60 + "\n\n")
        f.write(output)
    return filepath


def main():
    parser = argparse.ArgumentParser(description="Collect CLI output from Arista devices")
    parser.add_argument("command", nargs="?", help="Single command to run")
    parser.add_argument("-c", "--commands-file", help="File with one command per line")
    parser.add_argument("-d", "--devices", default="devices.txt", help="Device list file")
    parser.add_argument("-w", "--workers", type=int, default=10, help="Parallel SSH workers")
    parser.add_argument("-t", "--timeout", type=int, default=30, help="SSH timeout seconds")
    args = parser.parse_args()

    if args.command:
        commands = [args.command]
    elif args.commands_file:
        with open(args.commands_file) as f:
            commands = [l.strip() for l in f if l.strip() and not l.startswith("#")]
    else:
        commands = DEFAULT_COMMANDS

    devices = load_devices(args.devices)

    print(f"\nArista CLI Collector")
    print(f"{'='*40}")
    print(f"Devices:  {len(devices)}")
    print(f"Commands: {commands}")
    print(f"Output:   {OUTPUT_DIR}/\n")
    print("NOTE: Default uses 'show ip bgp detail vrf all'.")
    print("      If a device errors, re-run with: python3 collect.py 'show ip bgp detail'\n")

    username = input("Username: ").strip()
    password = getpass.getpass("Password: ")
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    success = 0
    failure = 0
    vrf_errors = []

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {
            pool.submit(collect_device, host, username, password, commands, args.timeout): host
            for host in devices
        }
        for future in as_completed(futures):
            host, results, error = future.result()
            if error:
                print(f"  [FAIL] {host}: {error}")
                failure += 1
            else:
                for cmd, output in results.items():
                    if cmd.startswith("__error__"):
                        orig_cmd = cmd.replace("__error__", "")
                        vrf_errors.append((host, orig_cmd, output))
                        continue
                    path = save_output(host, cmd, output, timestamp)
                    print(f"  [OK]   {host} → {path}")
                success += 1

    print(f"\nDone. {success} succeeded, {failure} failed.")

    if vrf_errors:
        print(f"\n{'='*40}")
        print("WARNING: These devices returned errors ('vrf all' may not be supported):")
        for host, cmd, err in vrf_errors:
            print(f"  {host}: {err[:100]}")
        print("\nFallback: python3 collect.py 'show ip bgp detail'")

    print(f"\nNext step: python3 parse_bgp.py")


if __name__ == "__main__":
    main()
