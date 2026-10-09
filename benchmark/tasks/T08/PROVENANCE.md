# Source provenance and primary protocol references

MIT fixture: [alexforencich/verilog-ethernet](https://github.com/alexforencich/verilog-ethernet)
commit `77320a9471d19c7dd383914bc049e02d9f4f1ffb`, including pinned lib/axis.
Eight imported modules: eth_mac_1g_fifo, eth_mac_1g, axis_gmii_tx, axis_gmii_rx,
lfsr, axis_async_fifo_adapter, axis_async_fifo, axis_adapter.
Original copyright/license headers and starter/LICENSE.upstream are retained.
This pinned benchmark fixture is not a recommendation to adopt deprecated IP.

Task-authored changes extend RX FIFO user width, insert the unimplemented VLAN
stub and define mac_1g_repair's fixed interface. Revision 3's repair ticket
contains a coupled frame-transaction regression; the old TX-tail defects are removed.
Neither its locations nor a golden patch are contestant input.
starter.sha256 freezes the buggy input, not a corrected reference.

The self-contained contract governs tests. Background primary sources:

- [IEEE 802.3](https://www.ieee802.org/3/)
- [IEEE frame format](https://www.ieee802.org/3/as/public/0607/802.3as_overview.pdf)
- [IEEE GMII overview](https://www.ieee802.org/3/cfi/1124_1/CFI_01_1124.pdf)
- [IEEE 802.1Q](https://www.ieee802.org/1/pages/802.1Q.html)
- [IETF RFC 7133 tag fields](https://datatracker.ietf.org/doc/html/rfc7133)

Acceptance uses independent software CRC, not the upstream RTL LFSR.
