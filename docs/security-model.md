# Security model and limits

Read this before relying on Eden.

## What Eden protects against

A device linked through Meshnet that you did not mean to give access to a service. With Eden, a service is closed to
every device unless you granted that device, and Eden's own admin page is not reachable from the network at all.

## What Eden does not do

- **It is not authentication for your services.** A device you grant a service reaches the whole service. If the service
  has no login of its own (a local AI server, say), anyone on that device can use it. Give such services their own key.
- **It filters what comes in, not what goes out.** Your computer can still connect to other devices' services.
- **It does not encrypt.** The Meshnet tunnel is the transport security. The remote login page is plain HTTP inside
  that tunnel.
- **It does not protect against a compromised account.** If someone controls your computer's user account, they control
  Eden. The helper limits what they can open: only ports in the allowed-ports file, which only root or an
  administrator can edit.

## The privileged part

The helper has a fixed list of commands and builds every rule itself from validated input. It never receives rule text
or a shell command. Ports must be listed in the allowed-ports file (a file that anyone but root or an administrator can
write to makes the helper refuse to work). Everything it does is logged: to the system journal on Linux, to
`%ProgramData%\Eden\helper.log` on Windows.

On Windows the helper runs elevated, so its files are copied to a folder only administrators can write to and it runs
with a Python that only administrators can change; the install script refuses a Python in a user-writable place.

## Devices of another Nord account

A person you invite to your Meshnet becomes an external device, which Eden treats as untrusted for good. Nord does not
tell Eden who invited whom. Accept an invitation from an outside person only on the computer that runs Eden and with
the four permission flags set to false, then give them services in Eden. An invitation is delivered to every device of
your Nord account: accepting it by mistake elsewhere links that person to that device too, which Eden cannot see. The
Nord account page, which lists external devices, is the audit.

## Known limits

- On Windows, IP protocols other than TCP, UDP and ICMP are not blocked for a device that has open ports (nothing
  listens on them on a normal machine).
- The secrets folder (password hash, one-time-code secret) relies on your user account's file permissions. On a volume
  without permissions (some NTFS or FAT mounts) any local account can read it.
- No lockout beyond the configured attempts per source; no TLS on the remote login.
- The forwarder adds no authentication and no rate limit.
- A notification that cannot be sent is logged and dropped.
- Log files grow while Eden runs; they are emptied at each start.
- The Windows edition is new and has had little testing.
