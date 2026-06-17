What We Know
A. About the problem
Why are we building this? What gap does it fill that FirmAE alone doesn't?

The threat model the framework targets (Mirai-style: defaults, known CVEs, exposed services)
Why automation matters (manual firmware analysis doesn't scale)
Why FirmAE alone isn't enough (raw outputs, no consolidation, no CVE matching, no credential testing, no structured reporting)
The project's contribution (integration and consolidation, not new emulation technique)

B. About FirmAE
What we've learned by actually using it.

It works for ~80% of firmware images (per the paper; we'll measure ourselves)
It caches results in PostgreSQL image table + scratch/<iid>/ directory
It hardcodes 192.168.0.0/24 for emulated firmware
It creates tap<iid>_0 interfaces with subnet routes attached — kernel preferences these over default routes, so even "public" inferred IPs route locally
It sometimes infers public IPs (saw: 2.65.87.199 for D-Link IP camera)
Its init.sh is lighter than expected; doesn't manipulate host main interface
Its install.sh breaks on Ubuntu 24.04 (PEP 668 cascade)
It produces useful structured outputs in scratch/<iid>/: result, ip, architecture, web, time_*, qemu.final.serial.log, etc.
Its check mode (-c) runs ~5-10 mins; run mode (-r) keeps firmware alive
Its analyser mode (-a) needs Chrome/chromedriver that we won't bother fixing
BusyBox errors during emulation (readlink: invalid option -- 'a') are cosmetic, non-fatal

C. About the lab environment
What we built and why.

Proxmox host, opnsense gateway at 192.168.0.3 bridging 192.168.0.0/24 ↔ 10.10.0.0/24
VM firmdh: Ubuntu 22.04.4 LTS, 16GB RAM, dual NIC (enp6s18 management 10.10.1.101, enp6s19 lab 10.10.80.101)
22.04 not 24.04 (24.04 breaks FirmAE install)
Dual NIC didn't fix the SSH issue alone — the route pinning did
192.168.0.11/32 via 10.10.1.1 persistent route survives FirmAE network changes
Snapshots: base-installed → firmae-installed → firmae-working → first-emulation-success → dual-nic

D. About what works
Concrete successes that prove the approach.

DIR-868L (armel revB) emulated successfully, full pipeline ran, real findings produced
dnsmasq 2.45 on port 53/63481 detected — first real CVE-relevant finding
v1 framework: end-to-end run on one firmware producing structured JSON
Cache detection (PostgreSQL + scratch verification) reduces re-runs to ~2 min from ~10 min
Batch runner with vendor-aware brand naming works
Scan profiles as data dict (fast/comprehensive/stealth) — flexible without code bloat

E. About what didn't work or surprised us
The mistakes worth recording so we don't repeat them.

Three wrong diagnoses of the SSH death problem before getting it right
Hardcoded ports in initial probe code — would have broken cross-vendor scanning
Missing IP validation — surfaced the Swedish-IP scare (which turned out to be safe but only because of FirmAE's tap routing)
Initial proposal said "primary data" for firmware — actually secondary
Initial methodology name "applied experimentation" — Design Science Research is the proper term
DCS-930L 1.09_B2 timed out at 1800s — possible genuine FirmAE failure, possible transient

F. About the safety model
What the framework guarantees and how.

RFC1918 / loopback IP check before any probing (defence in depth on top of FirmAE's tap routing)
No exploitation, no weaponisation
No probing of any IP the framework hasn't validated
Determinism: same input produces same finding set
No silent failures — every firmware produces a report

G. About the data we care about
What goes into reports and why.

Per-image: firmware identity (hash + path + name), architecture, inferred IP, emulation success, services with banners, processing time, cache flag
Per-batch: outcomes by status, per-vendor breakdown, success rates, mean fresh-run duration
Future additions: CVE matches per service, credential test results per endpoint

H. About the dissertation's needs
What the framework's outputs must support.

Emulation success rate (per vendor, per architecture)
Vulnerability detection accuracy (precision/recall on labelled subset)
Mean processing time (fresh runs only, broken down)
Comparison to FirmAE's published baseline
Honest reporting of limitations (failed emulations, parser misses, timeout cases)

I. What we don't yet know
The open questions.

True emulation success rate on the full dataset (only have 2 images measured)
Whether the timeout cases are genuine FirmAE limits or transient
Whether NVD's API will return useful results for the kinds of service strings nmap produces
Whether default credential testing will produce reliable positives/negatives
Whether IP cameras systematically behave differently from routers
How the framework will scale to 30-50 images in one batch


