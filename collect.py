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
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

try:
    from netmiko import ConnectHandler, NetmikoTimeoutException, NetmikoAuthenticationException
except ImportError:
    print("ERROR: netmiko not installed. Run: pip install netmiko")
    sys.exit(1)

OUTPUT_DIR = "output"
PASSWORD_TRIES = 3
AUTH_FAILED = "Authentication failed"
SKIPPED = "Skipped: stopped after a login failure (to avoid locking the account)"

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


def collect_device(host, username, password, commands, timeout=30, stop=None):
    """Connect to a single device and run all commands. Returns (host, results, error).

    If ``stop`` (a threading.Event) is set before this device starts, it is skipped
    without trying to log in.
    """
    if stop is not None and stop.is_set():
        return host, {}, SKIPPED
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
        if stop is not None:
            stop.set()
        return host, {}, AUTH_FAILED
    except NetmikoTimeoutException:
        return host, {}, "Connection timed out"
    except Exception as e:
        return host, {}, str(e)


def verify_login(devices, username, commands, timeout, ask_password=None):
    """Log in to one device at a time until one works, so a wrong password is only
    tried once instead of on every device at the same time.

    Returns (password, first_result, unreachable) where first_result is the
    (host, results, None) of the device that worked, or (None, None, unreachable)
    if the password was refused PASSWORD_TRIES times or no device could be reached.
    """
    ask_password = ask_password or (lambda: getpass.getpass("Password: "))
    unreachable = []
    queue = list(devices)
    tries = 0
    password = ask_password()
    while queue:
        host = queue[0]
        print(f"  Checking login on {host} ...")
        host, results, error = collect_device(host, username, password, commands, timeout)
        if error is None:
            print(f"  [OK]   Login works on {host}. Collecting from the rest.\n")
            return password, (host, results, None), unreachable
        if error == AUTH_FAILED:
            tries += 1
            print(f"  [FAIL] {host}: login refused. No other device was tried.")
            if tries >= PASSWORD_TRIES:
                print(f"\nStopping after {tries} refused logins so the account doesn't get locked.")
                return None, None, unreachable
            print(f"         Try again ({PASSWORD_TRIES - tries} left).")
            password = ask_password()
            continue
        # Not a password problem (down, timeout, DNS): check on the next device instead.
        print(f"  [FAIL] {host}: {error}. Checking the login on the next device instead.")
        unreachable.append((host, error))
        queue.pop(0)
    print("\nNo device could be reached to check the login.")
    return None, None, unreachable


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
    try:
        _main()
    except (KeyboardInterrupt, EOFError):
        print("\nCancelled. No further devices were contacted.")
        sys.exit(130)


def _main():
    parser = argparse.ArgumentParser(description="Collect CLI output from Arista devices")
    parser.add_argument("command", nargs="?", help="Single command to run")
    parser.add_argument("-c", "--commands-file", help="File with one command per line")
    parser.add_argument("-d", "--devices", default="devices.txt", help="Device list file")
    parser.add_argument("-w", "--workers", type=int, default=10, help="Parallel SSH workers")
    parser.add_argument("-t", "--timeout", type=int, default=30, help="SSH timeout seconds")
    parser.add_argument("--keep-going", action="store_true",
                        help="keep logging in to the other devices after a login failure "
                             "(default: stop, to avoid locking the account)")
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
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    success = 0
    failure = 0
    skipped = []
    vrf_errors = []

    def handle(host, results, error):
        nonlocal success, failure
        if error == SKIPPED:
            skipped.append(host)
        elif error:
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

    # 1. Check the password on one device before touching the rest.
    password, first, unreachable = verify_login(devices, username, commands, args.timeout)
    for host, error in unreachable:
        print(f"  [FAIL] {host}: {error}")
        failure += 1
    if first is None:
        print("Nothing else was tried.")
        sys.exit(1)
    handle(*first)

    # 2. The rest in parallel. A login failure stops new logins unless --keep-going.
    checked = {first[0]} | {h for h, _ in unreachable}
    rest = [h for h in devices if h not in checked]
    stop = None if args.keep_going else threading.Event()
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {
            pool.submit(collect_device, host, username, password, commands, args.timeout, stop): host
            for host in rest
        }
        for future in as_completed(futures):
            handle(*future.result())

    print(f"\nDone. {success} succeeded, {failure} failed" + (f", {len(skipped)} skipped." if skipped else "."))
    if skipped:
        print("\nA login was refused, so these devices were not tried (to avoid locking the account):")
        for host in sorted(skipped):
            print(f"  {host}")
        print("Check the credentials for the failed device, then re-run "
              "(or use --keep-going to try every device anyway).")

    if vrf_errors:
        print(f"\n{'='*40}")
        print("WARNING: These devices returned errors ('vrf all' may not be supported):")
        for host, cmd, err in vrf_errors:
            print(f"  {host}: {err[:100]}")
        print("\nFallback: python3 collect.py 'show ip bgp detail'")

    print(f"\nNext step: python3 parse_bgp.py")


if __name__ == "__main__":
    main()
