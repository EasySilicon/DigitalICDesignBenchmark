# T08 · 1GbE MAC repair and VLAN admission

[中文](README.md)

Repair the coupled TX/RX frame-transaction regression in the supplied MIT-licensed
brownfield RTL, and implement RX VLAN admission with a per-frame configuration
snapshot, atomic rejection and terminal metadata. The current time budget is
120 minutes, with no cumulative token hard stop.

The self-contained specification has over 4,000 lines, 39 ports, CRC/TCI numeric
vectors, 81 RX and 22 TX scenarios. It defines a GMII/C-tag subset, not full
IEEE certification, a PHY or a driver. Read [task.md](task.md) and
[acceptance.md](acceptance.md); `starter/rtl` is an intentionally broken starting
point, not the reference answer. Write your own verification and executable
`run.sh`; public smoke is not complete acceptance.

Specification `3.0-frame-transactions`, starter `3.0-coalesced-commit-regression`,
judge `3.1-boundary-crosses` and PPA policy `2.0-lambdapdk-tdp-1ghz` are frozen.
Scores are function /50 + PPA /50 + time /5. The evaluator automatically maps
eligible synchronous-read FIFO arrays to pinned lambdapdk `fakeram7_tdp_4096x32`
models, retaining both 4,096-entry capacities and all metadata. Candidates need
not instantiate/download a macro. All three asynchronous physical clocks use
1 GHz; functional clock requirements are unchanged.

WC standard cells with TT SRAM are mixed-corner research models, not silicon
signoff. Area/power include entire macros; DRC covers routing/pin access, not
macro interiors, and transistor-level LVS is not required. Qualified reference
seeds are 11/29/47. Host-only reference RTL, independent judges and freeze
receipts are excluded from candidate workspaces.
