// Frozen public interface for the experimental brownfield MAC task.
`timescale 1ns/1ps
`default_nettype none
module mac_1g_repair (
    input wire logic_clk, logic_rst,        // System clock/reset.
    input wire tx_clk, tx_rst,              // 125 MHz GMII TX clock/reset.
    input wire rx_clk, rx_rst,              // 125 MHz GMII RX clock/reset.
    input wire [7:0] tx_axis_tdata,          // Frame body, DA through payload.
    input wire tx_axis_tvalid, tx_axis_tlast, tx_axis_tuser,
    output wire tx_axis_tready,
    output wire [7:0] rx_axis_tdata,         // Frame body without preamble/FCS.
    output wire rx_axis_tvalid, rx_axis_tlast, rx_axis_tuser,
    input wire rx_axis_tready,
    output wire rx_axis_tagged,             // Meaningful on valid terminal beat.
    output wire [15:0] rx_axis_tci,          // Meaningful on valid terminal beat.
    input wire [7:0] gmii_rxd,
    input wire gmii_rx_dv, gmii_rx_er,
    output wire [7:0] gmii_txd,
    output wire gmii_tx_en, gmii_tx_er,
    input wire cfg_vlan_enable,             // Configuration synchronous to rx_clk.
    input wire cfg_accept_untagged, cfg_accept_priority,
    input wire [3:0] cfg_vlan_valid,
    input wire [47:0] cfg_vlan_vids,
    output wire rx_vlan_drop,               // RX-domain one-cycle event.
    output wire tx_error_underflow,
    output wire rx_error_bad_frame, rx_error_bad_fcs,
    output wire tx_fifo_overflow, tx_fifo_bad_frame, tx_fifo_good_frame,
    output wire rx_fifo_overflow, rx_fifo_bad_frame, rx_fifo_good_frame
);
    wire [17:0] rx_user;                    // Metadata shares the frame FIFO.
    assign rx_axis_tuser = rx_user[0];
    assign rx_axis_tci = rx_user[16:1];
    assign rx_axis_tagged = rx_user[17];
    eth_mac_1g_fifo #(
        .AXIS_DATA_WIDTH(8), .AXIS_KEEP_ENABLE(0), .AXIS_KEEP_WIDTH(1),
        .ENABLE_PADDING(1), .MIN_FRAME_LENGTH(64),
        .TX_FIFO_DEPTH(4096), .RX_FIFO_DEPTH(4096),
        .TX_FRAME_FIFO(1), .RX_FRAME_FIFO(1),
        .TX_DROP_OVERSIZE_FRAME(1), .RX_DROP_OVERSIZE_FRAME(1),
        .TX_DROP_BAD_FRAME(1), .RX_DROP_BAD_FRAME(1),
        .TX_DROP_WHEN_FULL(0), .RX_DROP_WHEN_FULL(1)
    ) mac (
        .logic_clk(logic_clk), .logic_rst(logic_rst),
        .tx_clk(tx_clk), .tx_rst(tx_rst), .rx_clk(rx_clk), .rx_rst(rx_rst),
        .tx_axis_tdata(tx_axis_tdata), .tx_axis_tkeep(1'b1),
        .tx_axis_tvalid(tx_axis_tvalid), .tx_axis_tready(tx_axis_tready),
        .tx_axis_tlast(tx_axis_tlast), .tx_axis_tuser(tx_axis_tuser),
        .rx_axis_tdata(rx_axis_tdata), .rx_axis_tkeep(),
        .rx_axis_tvalid(rx_axis_tvalid), .rx_axis_tready(rx_axis_tready),
        .rx_axis_tlast(rx_axis_tlast), .rx_axis_tuser(rx_user),
        .gmii_rxd(gmii_rxd), .gmii_rx_dv(gmii_rx_dv), .gmii_rx_er(gmii_rx_er),
        .gmii_txd(gmii_txd), .gmii_tx_en(gmii_tx_en), .gmii_tx_er(gmii_tx_er),
        .rx_clk_enable(1'b1), .tx_clk_enable(1'b1),
        .rx_mii_select(1'b0), .tx_mii_select(1'b0),
        .cfg_ifg(8'd12), .cfg_tx_enable(1'b1), .cfg_rx_enable(1'b1),
        .cfg_vlan_enable(cfg_vlan_enable), .cfg_accept_untagged(cfg_accept_untagged),
        .cfg_accept_priority(cfg_accept_priority), .cfg_vlan_valid(cfg_vlan_valid),
        .cfg_vlan_vids(cfg_vlan_vids), .rx_vlan_drop(rx_vlan_drop),
        .tx_error_underflow(tx_error_underflow),
        .rx_error_bad_frame(rx_error_bad_frame), .rx_error_bad_fcs(rx_error_bad_fcs),
        .tx_fifo_overflow(tx_fifo_overflow), .tx_fifo_bad_frame(tx_fifo_bad_frame),
        .tx_fifo_good_frame(tx_fifo_good_frame), .rx_fifo_overflow(rx_fifo_overflow),
        .rx_fifo_bad_frame(rx_fifo_bad_frame), .rx_fifo_good_frame(rx_fifo_good_frame)
    );
endmodule
`default_nettype wire
