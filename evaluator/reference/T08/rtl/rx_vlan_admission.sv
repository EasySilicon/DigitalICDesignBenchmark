// Per-frame VLAN policy. Bytes remain streaming; the existing frame FIFO
// commits good terminal beats and rolls back policy/MAC-bad terminal beats.
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
    // Saturate after the last inspected header byte: a long payload cannot
    // wrap around and reinterpret payload as a new header.
    reg [4:0] offset;
    // Zero is reserved for idle. A valid first byte sets one, a terminal
    // byte clears zero, and saturation prevents a payload wrap to idle.
    // This invariant removes a redundant frame-active flip-flop.
    wire in_frame = offset != 5'd0;
    reg enable_reg, untagged_reg, priority_reg;
    reg [3:0] valid_reg;
    reg [47:0] vids_reg;
    reg [7:0] type_hi;
    reg [15:0] tci_reg;
    reg tagged_reg, deny_reg;
    // Evaluate VID portions while their header octets arrive, not on the
    // terminal metadata/drop critical path. Configuration is already frozen.
    logic [3:0] vid_high_match_reg;
    logic vid_high_zero_reg, vid_high_reserved_reg, vid_allowed_reg;
    logic vlan_drop_reg;
    wire [3:0] vid_low_match;
    genvar slot;
    generate for (slot = 0; slot < 4; slot = slot + 1) begin : match_low
        assign vid_low_match[slot] = valid_reg[slot] && vid_high_match_reg[slot] &&
                                    s_data == vids_reg[12*slot +: 8];
    end endgenerate

    reg tagged_now, deny_now;

    // Decisions include the current byte. In particular, a terminal byte
    // at offset 13 or 17 completes its field before terminal user is formed.
    always @* begin
        tagged_now = tagged_reg;
        deny_now = deny_reg;

        if (!in_frame) begin
            tagged_now = 1'b0;
            deny_now = 1'b1; // incomplete header, if filtering is enabled
        end else if (offset == 5'd13) begin
            tagged_now = {type_hi, s_data} == 16'h8100;
            if ({type_hi, s_data} == 16'h8100 ||
                {type_hi, s_data} == 16'h88a8)
                deny_now = 1'b1;
            else
                deny_now = !untagged_reg;
        end else if (offset == 5'd17 && tagged_reg) begin
            if ({type_hi, s_data} == 16'h8100 ||
                {type_hi, s_data} == 16'h88a8)
                deny_now = 1'b1;
            else
                deny_now = !vid_allowed_reg;
        end
    end

    wire frame_enable = in_frame ? enable_reg : cfg_enable;
    wire policy_bad = frame_enable && deny_now;
    wire terminal = s_valid && s_last && !rst;
    wire terminal_tag = terminal && frame_enable && tagged_now &&
                        !policy_bad && !s_bad;

    assign m_data = s_data;
    assign m_valid = s_valid && !rst;
    assign m_last = s_last;
    // Never clear the raw MAC bad bit. Only bit zero controls FIFO rollback;
    // tag metadata follows the same terminal byte and the same frame commit.
    assign m_user = {terminal_tag, terminal_tag ? tci_reg : 16'b0,
                    s_bad | (terminal && policy_bad)};
    // Section 10.3 explicitly allows a fixed delay of up to two RX cycles.
    // A single registered pulse preserves MAC-error precedence and removes
    // the policy tree from the constrained top-level output path.
    assign vlan_drop = vlan_drop_reg && !rst;
    always_ff @(posedge clk) begin
        if (rst)
            vlan_drop_reg <= 1'b0;
        else
            vlan_drop_reg <= terminal && policy_bad && !s_bad;
    end

    always @(posedge clk) begin
        if (rst) begin
            offset <= 5'd0;
            enable_reg <= 1'b0;
            untagged_reg <= 1'b0;
            priority_reg <= 1'b0;
            valid_reg <= 4'd0;
            vids_reg <= 48'd0;
            type_hi <= 8'd0;
            tci_reg <= 16'd0;
            tagged_reg <= 1'b0;
            deny_reg <= 1'b1;
            vid_high_match_reg <= 4'b0;
            vid_high_zero_reg <= 1'b0;
            vid_high_reserved_reg <= 1'b0;
            vid_allowed_reg <= 1'b0;
        end else if (s_valid) begin
            if (!in_frame) begin
                // Snapshot all configuration on the first decoded byte,
                // independent of bubbles or subsequent live config changes.
                enable_reg <= cfg_enable;
                untagged_reg <= cfg_accept_untagged;
                priority_reg <= cfg_accept_priority;
                valid_reg <= cfg_valid;
                vids_reg <= cfg_vids;
                type_hi <= 8'd0;
                tci_reg <= 16'd0;
                vid_high_match_reg <= 4'b0;
                vid_high_zero_reg <= 1'b0;
                vid_high_reserved_reg <= 1'b0;
                vid_allowed_reg <= 1'b0;
                offset <= 5'd1;
            end else begin
                if (offset < 5'd18)
                    offset <= offset + 5'd1;
                if (offset == 5'd12 || offset == 5'd16)
                    type_hi <= s_data;
                if (offset == 5'd14) begin
                    tci_reg[15:8] <= s_data;
                    for (integer index = 0; index < 4; index = index + 1)
                        vid_high_match_reg[index] <= s_data[3:0] == vids_reg[12*index+8 +: 4];
                    vid_high_zero_reg <= s_data[3:0] == 4'h0;
                    vid_high_reserved_reg <= s_data[3:0] == 4'hf;
                end
                if (offset == 5'd15) begin
                    tci_reg[7:0] <= s_data;
                    if (vid_high_reserved_reg && s_data == 8'hff)
                        vid_allowed_reg <= 1'b0;
                    else if (vid_high_zero_reg && s_data == 8'h00)
                        vid_allowed_reg <= priority_reg;
                    else
                        vid_allowed_reg <= |vid_low_match;
                end
            end
            tagged_reg <= tagged_now;
            deny_reg <= deny_now;
            if (s_last)
                offset <= 5'd0;
        end
    end
endmodule
`default_nettype wire
