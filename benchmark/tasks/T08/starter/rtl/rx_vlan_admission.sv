// Benchmark extension stub. Replace with the admission feature in task.md.
// No full-frame buffer belongs here; frame commit/rollback is in the RX FIFO.
`timescale 1ns/1ps
`default_nettype none
module rx_vlan_admission (
    input wire clk,                         // RX clock.
    input wire rst,                         // Active-high RX reset.
    input wire [7:0] s_data,                 // Decoded body, including padding.
    input wire s_valid,                     // Valid byte; there is no backpressure.
    input wire s_last,                      // Final decoded body byte.
    input wire s_bad,                       // Existing MAC/FCS failure marker.
    input wire cfg_enable,                 // Per-frame admission enable.
    input wire cfg_accept_untagged,         // Admit untagged packets.
    input wire cfg_accept_priority,         // Admit VID=0 independently of list.
    input wire [3:0] cfg_valid,              // Valid bits for the four VID entries.
    input wire [47:0] cfg_vids,              // Entry i occupies [12*i +: 12].
    output wire [7:0] m_data,               // Unmodified body byte.
    output wire m_valid,                    // Unmodified byte validity.
    output wire m_last,                     // Unmodified frame boundary.
    output wire [17:0] m_user,              // {tagged,TCI[15:0],bad}; terminal only.
    output wire vlan_drop                   // RX-domain policy rejection pulse.
);
    assign m_data = s_data;
    assign m_valid = s_valid;
    assign m_last = s_last;
    assign m_user = {17'b0, s_bad};
    assign vlan_drop = 1'b0;
endmodule
`default_nettype wire
