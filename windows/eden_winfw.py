# Eden, Windows edition: turns the policy's (port, address) pairs into Windows Firewall rules. The rule SET is
# computed here in plain Python (no Windows calls, so it is unit-tested anywhere); the PowerShell that creates the
# rules is rendered from it. Nothing in this file is imported by the Linux edition.
#
# Why this shape (RELEASE_PLAN section 9.2, verified on Windows in W0): on Windows a Block rule beats any Allow rule,
# and Nord adds its own Allow rule for the peers it lists, so "allow list + default drop" cannot be written with
# allow rules alone. The set is therefore a complement of Blocks plus narrow Allows, all scoped to the Meshnet adapter:
#   - down (guard):  one Block, any protocol, any address.
#   - up: every Meshnet address that has no open port is blocked completely; an address with open ports is blocked on
#     every TCP port except its own, on all UDP and on ICMP, and gets an Allow for its TCP ports.
# A change is made by generations: the new set is created first and the old one removed after it, so the machine is
# never less protected during a change. Known limit: for an address that has open ports, IP protocols other than
# TCP, UDP and ICMP are not blocked by these rules (nothing listens on them on a normal machine).

import ipaddress

GROUP = "Eden"
# Meshnet addresses are 100.64.0.0/10 (RFC 6598); the tunnel only carries those (WireGuard drops any other source), and
# this exact "a-b" range syntax is the one verified on Windows (W0). Ranges starting at 0.0.0.0 were rejected (W2 run 1).
MESH_RANGE = (int(ipaddress.IPv4Address("100.64.0.0")), int(ipaddress.IPv4Address("100.127.255.255")))
IPV6_ALL = "::-ffff:ffff:ffff:ffff:ffff:ffff:ffff:ffff"   # the whole IPv6 space; "::/0" is refused by Windows (W2 run 2)


def port_ranges(open_ports):
    """TCP ports 1-65535 minus `open_ports`, as range strings for -LocalPort ("1-79", "81-65535")."""
    ports = sorted({int(p) for p in open_ports})
    if any(not 1 <= p <= 65535 for p in ports):
        raise ValueError("port out of range")
    out, start = [], 1
    for p in ports:
        if p > start:
            out.append(f"{start}-{p - 1}" if p - 1 > start else str(start))
        start = p + 1
    if start <= 65535:
        out.append(f"{start}-65535" if start < 65535 else "65535")
    return out


def address_ranges(exempt_ips):
    """The Meshnet range minus `exempt_ips`, as range strings for -RemoteAddress ("100.64.0.0-100.64.0.9")."""
    nums = sorted({int(ipaddress.IPv4Address(ip)) for ip in exempt_ips})
    if any(not MESH_RANGE[0] <= n <= MESH_RANGE[1] for n in nums):
        raise ValueError("address outside the Meshnet range 100.64.0.0/10")
    out, start = [], MESH_RANGE[0]
    for n in nums:
        if n > start:
            out.append(_span(start, n - 1))
        start = n + 1
    if start <= MESH_RANGE[1]:
        out.append(_span(start, MESH_RANGE[1]))
    return out


def _span(a, b):
    lo, hi = str(ipaddress.IPv4Address(a)), str(ipaddress.IPv4Address(b))
    return lo if a == b else f"{lo}-{hi}"


def guard_rules():
    """The state with Eden down or failed: nothing from the Meshnet reaches the machine."""
    return [{"name": "guard", "action": "Block", "protocol": "Any", "local_port": None, "remote": None}]


def up_rules(pairs, ipv6=True):
    """Rules for the open (port, ip) pairs. With no pair at all it blocks every Meshnet address (not the guard: same
    effect, but the result still reads as the "up" state). `ipv6` adds the Block of the whole IPv6 space."""
    per_ip = {}
    for port, ip in pairs:
        per_ip.setdefault(str(ipaddress.IPv4Address(ip)), set()).add(int(port))
    # Addresses with the same set of ports share their rules.
    by_ports = {}
    for ip, ports in per_ip.items():
        by_ports.setdefault(tuple(sorted(ports)), []).append(ip)
    rules = [{"name": "rest", "action": "Block", "protocol": "Any", "local_port": None,
              "remote": address_ranges(per_ip)}]
    if ipv6:
        rules.append({"name": "ipv6", "action": "Block", "protocol": "Any", "local_port": None, "remote": [IPV6_ALL]})
    for n, (ports, ips) in enumerate(sorted(by_ports.items()), 1):
        ips = sorted(ips, key=lambda x: int(ipaddress.IPv4Address(x)))
        tag = f"set{n}"
        # Blocks first, then the Allow: the Allow never exists without its Blocks.
        rules.append({"name": f"{tag} tcp-other", "action": "Block", "protocol": "TCP",
                      "local_port": port_ranges(ports), "remote": ips})
        rules.append({"name": f"{tag} udp", "action": "Block", "protocol": "UDP", "local_port": None, "remote": ips})
        rules.append({"name": f"{tag} icmp", "action": "Block", "protocol": "ICMPv4", "local_port": None, "remote": ips})
        rules.append({"name": f"{tag} allow", "action": "Allow", "protocol": "TCP",
                      "local_port": [str(p) for p in ports], "remote": ips})
    return rules


def _ps_list(values):
    return "@(" + ",".join("'" + v + "'" for v in values) + ")"


def render_rules(rules):
    """PowerShell array literal of the rules, in order (every Block before its Allow)."""
    lines = []
    for r in rules:
        parts = [f"Name='{r['name']}'", f"Action='{r['action']}'", f"Protocol='{r['protocol']}'"]
        if r["local_port"]:
            parts.append(f"LocalPort={_ps_list(r['local_port'])}")
        if r["remote"]:
            parts.append(f"RemoteAddress={_ps_list(r['remote'])}")
        lines.append("    @{ " + "; ".join(parts) + " }")
    return "@(\n" + ",\n".join(lines) + "\n)"


# PowerShell that applies a rule list as a new generation and then removes the older ones (never less protected
# in between). Static text: the same function serves the test script and, later, the elevated helper.
APPLY_FUNCTION = r"""
function Set-EdenRules {
    param([string]$Generation, [object[]]$Rules, [string]$Alias)
    $old = @(Get-NetFirewallRule -Group 'Eden' -ErrorAction SilentlyContinue)
    $created = @()
    try {
        foreach ($r in $Rules) {
            $p = @{ DisplayName = "Eden $Generation $($r.Name)"; Group = 'Eden'; Direction = 'Inbound'; Action = $r.Action; Protocol = $r.Protocol; InterfaceAlias = $Alias; Profile = 'Any' }
            if ($r.LocalPort) { $p.LocalPort = $r.LocalPort }
            if ($r.RemoteAddress) { $p.RemoteAddress = $r.RemoteAddress }
            $cur = $r.Name
            New-NetFirewallRule @p | Out-Null
            $created += $p.DisplayName
        }
    } catch {
        $why = "rule '$cur': " + $_.Exception.Message
        foreach ($n in $created) { Get-NetFirewallRule -DisplayName $n -ErrorAction SilentlyContinue | Remove-NetFirewallRule }
        throw $why
    }
    if ($old.Count -gt 0) { $old | Remove-NetFirewallRule }
}
function Remove-EdenRules { Get-NetFirewallRule -Group 'Eden' -ErrorAction SilentlyContinue | Remove-NetFirewallRule }
""".lstrip("\n")
