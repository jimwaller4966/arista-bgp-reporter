# arista-bgp-reporter

Collect show ip bgp vrf all detail from Arista EOS devices via SSH and render
an interactive HTML report with filterable, sortable tables per VRF and neighbor.

## Requirements

    pip install netmiko

## Usage

### 1. Configure devices

    cp devices.txt.example devices.txt
    # Edit devices.txt - one hostname or IP per line

### 2. Collect

    python3 collect.py
    # Prompts for credentials, saves output/<host>_show_ip_bgp_detail_vrf_all.txt

The password is checked on one device before any other is contacted, so a typo
doesn't hit every device at once and lock the account:

- The first device is logged into alone. If the login is refused, nothing else is
  tried and you're asked again (3 tries, then it stops).
- If that device is down or times out, the check moves to the next device.
- Once the login works, the rest run in parallel. If any of them refuses the login,
  no new logins start and the remaining devices are listed as skipped.
  `--keep-going` turns that off and tries every device anyway.

### 3. Parse and render

    python3 parse_bgp.py
    # Generates bgp_report.html

Open bgp_report.html in any browser.

## Report features

- Live search across all fields
- Filter by Device, VRF, Remote AS, State, Address Family
- Sortable columns
- State badges (Established / Active / Idle / etc.)
- Stats bar: devices, VRFs, neighbors, established count, total prefixes

## Lab (cEOS / Containerlab)

A 6-node full-mesh cEOS lab with eBGP across default, PROD, and MGMT VRFs
is included under bgp-lab/ for testing.

    cd bgp-lab
    sudo containerlab deploy -t bgp-fullmesh.yaml

Requires Containerlab (https://containerlab.dev) and a local ceosimage:4.36.0.1F Docker image.

## Adding parsers

To add support for a new command:
1. Create parsers/<name>.py with parse(host, raw), COLUMNS, TITLE, COMMAND, COMMAND_SLUGS
2. Clone parse_bgp.py to parse_<name>.py pointing to the new parser
3. Add the command to DEFAULT_COMMANDS in collect.py or pass it with -c
