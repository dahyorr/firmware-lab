# Loopback IP Failures — Tracking Log

Tracks firmware that fail via the R-1 loopback guard in `firmae_runner.py`
(`_apply_ip_check`): FirmAE's own `result` file says `true`, but the `ip`
file it writes is `127.0.0.1` rather than a real routable address. Our
framework correctly reclassifies these as `emulation_failed` rather than
scanning the host VM by mistake — this file exists to spot patterns across
runs (same vendor family, same VPC, same architecture, etc.) rather than
treat each one as a one-off.

**Root cause (confirmed via scratch/2 boot logs, VPC-1, 2026-08-27):**
FirmAE's network setup lands the guest on QEMU's default user-mode/SLIRP
address (`10.0.2.15`), then checks for a web service by probing `127.0.0.1`
on the host side (via an implied port-forward). That check times out after
360s with no response, but FirmAE's own success criterion only requires
"network interface detected + ethernet present" — it doesn't verify the web
service actually came up. Our R-1 guard is the only thing standing between
this and scanning the wrong target.

## Log

| Date | VPC | Firmware | Vendor | Notes |
|---|---|---|---|---|
| 2026-08-27 | VPC-1 | DGN1000NA_V1.1.00.40.zip | netgear | Full boot log analysis done — see explanation above. `DGN1000` family already had a 0% historical success rate before this from-scratch run. |
| 2026-08-27 (pre-reset) | VPC-1 | FW_TV-IP110WN_1.2.2.65.zip | trendnet_ipcamera | Same signature, seen before the sasquatch fix + full reset wiped this run's data. |
| 2026-08-27 (pre-reset) | VPC-1 | FW_TV-IP121WN_1.2.2.zip | trendnet_ipcamera | Same signature. |

## How to add an entry

When this failure shows up again (grep a VPC's batch log for `Emulated IP is
loopback`), add a row above with date/VPC/firmware/vendor, and check
`scratch/<id>/makeNetwork.log` to confirm the same signature (or note if it
differs) before assuming it's the same root cause.
