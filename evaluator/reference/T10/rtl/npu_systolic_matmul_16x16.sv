// Independent T10 reference under construction. The stream/wavefront and
// exact arithmetic paths still require full hidden and physical qualification.
module npu_systolic_matmul_16x16 (
    input  logic          clk,
    input  logic          rst_n,
    input  logic          in_valid,
    input  logic          in_start,
    input  logic [15:0]   in_block_id,
    input  logic [3:0]    mode,
    input  logic [255:0]  a_scale,
    input  logic [255:0]  b_scale,
    input  logic [1023:0] a_data,
    input  logic [1023:0] b_data,
    output logic          in_ready,
    output logic [3:0]    out_valid,
    output logic [63:0]   out_block_id,
    output logic [15:0]   out_row,
    output logic [4095:0] out_data,
    input  logic          out_ready
);
    localparam int SLOT_COUNT = 16;
    localparam int TOKEN_BITS = 28;
    localparam int CTRL_BITS = 12;
    localparam int CTRL_VALID_BIT = 11;
    localparam int CTRL_FIRST_BIT = 10;
    logic active;
    logic [4:0] beat_q;
    logic [3:0] mode_q, active_slot, write_slot, read_slot;
    logic write_wrap, read_wrap, slot_full_state, slot_full_io;
    logic [3:0] output_row;
    logic [15:0] slot_id [0:SLOT_COUNT-1];
    logic [3:0] slot_mode [0:SLOT_COUNT-1];
    logic complete [0:SLOT_COUNT-1];
    logic [1023:0] row_read_data [0:15];
    logic [3:0] row_read_slot [0:15];
    logic row_consumed_pipe1 [0:15];
    logic row_consumed_pipe2 [0:15];
    logic [3:0] source_valid;
    logic [63:0] source_block_id;
    logic [15:0] source_row;
    logic source_ready;
    logic gather_stage_ready;
    logic output_stage_ready;
    logic final_stage_ready;
    logic [3:0] gather_valid;
    logic [63:0] gather_block_id;
    logic [15:0] gather_row;
    logic [607:0] gather_group_data [0:3][0:3];
    logic [3:0] output_stage_valid;
    logic [63:0] output_stage_block_id;
    logic [15:0] output_stage_row;
    logic [2431:0] output_stage_compact_data;
    logic [1:0] output_queue_count;
    logic output_queue_read_ptr, output_queue_write_ptr;
    logic [3:0] output_queue_valid_0, output_queue_valid_1;
    logic [63:0] output_queue_block_id_0, output_queue_block_id_1;
    logic [15:0] output_queue_row_0, output_queue_row_1;
    logic [3:0] prefetch_valid;
    logic [63:0] prefetch_block_id;
    logic [15:0] prefetch_row;
    logic [3:0] prefetch_row_select [0:15];
    logic [607:0] row_capture_data [0:15];

    logic input_fire, input_first, input_last, output_fire, output_last;
    logic final_push, final_pop;
    logic [3:0] input_mode, input_slot;
    logic high_scale_group;
    logic [2:0] rows_per_cycle;
    logic [4:0] next_output_row;
    logic [63:0] a_edge_data [0:15];
    logic [63:0] b_edge_data [0:15];
    logic [15:0] a_edge_scale [0:15];
    logic [15:0] b_edge_scale [0:15];
    logic [1023:0] ingress_a_data, ingress_b_data;
    logic [255:0] ingress_a_scale, ingress_b_scale;
    logic ingress_fire, ingress_start, ingress_open;
    logic [3:0] ingress_mode;
    logic [3:0] ingress_beats_left;
    logic [15:0] ingress_block_id;
    logic [15:0] a_scale_hold [0:15];
    logic [15:0] b_scale_hold [0:15];
    (* keep = 1 *) logic [10:0] a_ctrl_payload [0:15];
    (* keep = 1 *) logic [10:0] b_ctrl_payload [0:15];
    (* keep = 1 *) logic a_ctrl_valid [0:15];
    (* keep = 1 *) logic b_ctrl_valid [0:15];
    logic [CTRL_BITS-1:0] a_ctrl_spine [0:15];
    logic [CTRL_BITS-1:0] b_ctrl_spine [0:15];
    logic [63:0] a_skew_data [0:15][0:14];
    logic [63:0] b_skew_data [0:15][0:14];
    logic [15:0] a_skew_scale [0:15][0:14];
    logic [15:0] b_skew_scale [0:15][0:14];
    logic [15:0] a_enter_scale [0:15], b_enter_scale [0:15];
    logic [63:0] a_enter_data [0:15], b_enter_data [0:15];
    logic [TOKEN_BITS-1:0] a_enter_token [0:15], b_enter_token [0:15];
    logic [63:0] a_tile_forward [0:15][0:3];
    logic [63:0] b_tile_forward [0:3][0:15];
    logic [TOKEN_BITS-1:0] at_tile_forward [0:15][0:3];
    logic [TOKEN_BITS-1:0] bt_tile_forward [0:3][0:15];
    logic [15:0] pe_boundary_done;
    logic [3:0] pe_boundary_slot [0:15];
    logic [15:0] pe_boundary_done_s0, pe_boundary_done_s1, pe_boundary_done_s2;
    logic [3:0] pe_boundary_slot_s0 [0:15];
    logic [3:0] pe_boundary_slot_s1 [0:15];
    logic [3:0] pe_boundary_slot_s2 [0:15];

    function automatic logic [3:0] next_slot(input logic [3:0] slot);
        next_slot = slot == 4'(SLOT_COUNT-1) ? 4'd0 : slot + 4'd1;
    endfunction

    // ingress_open tracks the external transaction boundary independently of
    // the one-stage processing pipeline.  slot_full_io is deliberately two
    // registered stages behind the allocation pointers: the shortest block is
    // four beats, so it asserts before that block can finish while keeping the
    // chip-level ready path to one local OR gate.
    assign in_ready = ingress_open || !slot_full_io;
    assign input_fire = ingress_fire;
    assign input_first = input_fire && ingress_start;
    assign input_mode = ingress_start ? ingress_mode : mode_q;
    assign input_slot = ingress_start ? write_slot : active_slot;
    // A first beat is never the last beat and always uses the low MX scale.
    // Decode the ongoing block from registered state so in_start does not
    // traverse the mode/width comparator before the control spine register.
    always_comb begin
        case (mode_q)
            1, 2, 3: begin
                input_last = input_fire && !ingress_start && (beat_q == 5'd15);
                high_scale_group = !ingress_start && beat_q[3];
            end
            6, 9: begin
                input_last = input_fire && !ingress_start && (beat_q == 5'd3);
                high_scale_group = !ingress_start && beat_q[1];
            end
            default: begin
                input_last = input_fire && !ingress_start && (beat_q == 5'd7);
                high_scale_group = !ingress_start && beat_q[2];
            end
        endcase
    end

    // Capture the complete external transaction at the chip boundary.  The
    // following edge launches matched registered data and control into the
    // row/column wavefront while another external beat can be accepted.
    always_ff @(posedge clk) begin
        ingress_a_data <= a_data;
        ingress_b_data <= b_data;
        ingress_a_scale <= a_scale;
        ingress_b_scale <= b_scale;
        ingress_start <= in_start;
        ingress_mode <= mode;
        ingress_block_id <= in_block_id;
        a_ctrl_payload[0] <= {input_first, input_last, input_mode,
                             input_slot, high_scale_group};
        b_ctrl_payload[0] <= ~{input_first, input_last, input_mode,
                              input_slot, high_scale_group};
    end
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            ingress_fire <= 1'b0;
            ingress_open <= 1'b0;
            ingress_beats_left <= '0;
            slot_full_state <= 1'b0;
            slot_full_io <= 1'b0;
        end else begin
            ingress_fire <= in_valid && in_ready;
            slot_full_state <= (write_slot == read_slot) &&
                               (write_wrap != read_wrap);
            slot_full_io <= slot_full_state;
            if (in_valid && in_ready) begin
                if (in_start) begin
                    ingress_open <= 1'b1;
                    case (mode)
                        1, 2, 3: ingress_beats_left <= 4'd15;
                        6, 9:    ingress_beats_left <= 4'd3;
                        default: ingress_beats_left <= 4'd7;
                    endcase
                end else if (ingress_open) begin
                    if (ingress_beats_left == 4'd1) begin
                        ingress_open <= 1'b0;
                        ingress_beats_left <= '0;
                    end else begin
                        ingress_beats_left <= ingress_beats_left - 4'd1;
                    end
                end
            end
        end
    end
    // Register the far-edge PE completion token twice before it updates the
    // shared block-complete table. The two stages also let physical placement
    // spread this chip-wide connection across multiple clock periods.
    for (genvar r=0; r<16; r++) begin : completion_pipeline
        always_ff @(posedge clk) begin
            pe_boundary_slot_s0[r] <= pe_boundary_slot[r];
            pe_boundary_slot_s1[r] <= pe_boundary_slot_s0[r];
            pe_boundary_slot_s2[r] <= pe_boundary_slot_s1[r];
        end
        always_ff @(posedge clk or negedge rst_n) begin
            if (!rst_n) begin
                pe_boundary_done_s0[r] <= 1'b0;
                pe_boundary_done_s1[r] <= 1'b0;
                pe_boundary_done_s2[r] <= 1'b0;
            end else begin
                pe_boundary_done_s0[r] <= pe_boundary_done[r];
                pe_boundary_done_s1[r] <= pe_boundary_done_s0[r];
                pe_boundary_done_s2[r] <= pe_boundary_done_s1[r];
            end
        end
    end
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            a_ctrl_valid[0] <= 1'b0;
            b_ctrl_valid[0] <= 1'b1;
        end else begin
            a_ctrl_valid[0] <= ingress_fire;
            b_ctrl_valid[0] <= ~ingress_fire;
        end
    end
    for (genvar d=1; d<16; d++) begin : control_spine
        always_ff @(posedge clk) begin
            a_ctrl_payload[d] <= a_ctrl_payload[d-1];
            b_ctrl_payload[d] <= b_ctrl_payload[d-1];
        end
        always_ff @(posedge clk or negedge rst_n) begin
            if (!rst_n) begin
                a_ctrl_valid[d] <= 1'b0;
                b_ctrl_valid[d] <= 1'b1;
            end else begin
                a_ctrl_valid[d] <= a_ctrl_valid[d-1];
                b_ctrl_valid[d] <= b_ctrl_valid[d-1];
            end
        end
    end
    for (genvar d=0; d<16; d++) begin : control_pack
        assign a_ctrl_spine[d] = {a_ctrl_valid[d], a_ctrl_payload[d]};
        assign b_ctrl_spine[d] = {~b_ctrl_valid[d], ~b_ctrl_payload[d]};
    end

    // A row and B column each carry one 64-bit vector per accepted input
    // beat. The valid bit makes bubbles transparent to the running wavefront.
    for (genvar r=0; r<16; r++) begin : row_boundary
        // Scale follows the row payload; first-beat scale is held locally.
        always_ff @(posedge clk)
            a_edge_data[r] <= ingress_a_data[r*64 +: 64];
        always_ff @(posedge clk)
            a_edge_scale[r] <= ingress_a_scale[r*16 +: 16];
        always_ff @(posedge clk)
            if (a_ctrl_spine[r][CTRL_VALID_BIT] &&
                a_ctrl_spine[r][CTRL_FIRST_BIT])
                a_scale_hold[r] <= a_enter_scale[r];
        if (r == 0) begin : no_skew
            assign a_enter_data[r] = a_edge_data[r];
            assign a_enter_scale[r] = a_edge_scale[r];
        end else begin : skew
            for (genvar d=0; d<r; d++) begin : stage
                always_ff @(posedge clk)
                    a_skew_data[r][d] <= d == 0 ? a_edge_data[r] :
                                          a_skew_data[r][d-1];
                always_ff @(posedge clk)
                    a_skew_scale[r][d] <= d == 0 ? a_edge_scale[r] :
                                             a_skew_scale[r][d-1];
            end
            assign a_enter_data[r] = a_skew_data[r][r-1];
            assign a_enter_scale[r] = a_skew_scale[r][r-1];
        end
        assign a_enter_token[r] = {a_ctrl_spine[r],
                                   a_ctrl_spine[r][CTRL_FIRST_BIT] ?
                                   a_enter_scale[r] : a_scale_hold[r]};
    end
    for (genvar c=0; c<16; c++) begin : column_boundary
        // Match the A boundary stage to preserve the diagonal wavefront.
        always_ff @(posedge clk)
            b_edge_data[c] <= ingress_b_data[c*64 +: 64];
        always_ff @(posedge clk)
            b_edge_scale[c] <= ingress_b_scale[c*16 +: 16];
        always_ff @(posedge clk)
            if (b_ctrl_spine[c][CTRL_VALID_BIT] &&
                b_ctrl_spine[c][CTRL_FIRST_BIT])
                b_scale_hold[c] <= b_enter_scale[c];
        if (c == 0) begin : no_skew
            assign b_enter_data[c] = b_edge_data[c];
            assign b_enter_scale[c] = b_edge_scale[c];
        end else begin : skew
            for (genvar d=0; d<c; d++) begin : stage
                always_ff @(posedge clk)
                    b_skew_data[c][d] <= d == 0 ? b_edge_data[c] :
                                          b_skew_data[c][d-1];
                always_ff @(posedge clk)
                    b_skew_scale[c][d] <= d == 0 ? b_edge_scale[c] :
                                             b_skew_scale[c][d-1];
            end
            assign b_enter_data[c] = b_skew_data[c][c-1];
            assign b_enter_scale[c] = b_skew_scale[c][c-1];
        end
        assign b_enter_token[c] = {b_ctrl_spine[c],
                                   b_ctrl_spine[c][CTRL_FIRST_BIT] ?
                                   b_enter_scale[c] : b_scale_hold[c]};
    end

    // Sixteen physical tiles preserve the PE-to-PE wavefront and absorb the
    // four local result banks. Only tile boundaries cross the top hierarchy.
    for (genvar tr=0; tr<4; tr++) begin : tile_row
        for (genvar tc=0; tc<4; tc++) begin : tile_col
            wire [255:0] tile_a_input, tile_b_input;
            wire [111:0] tile_at_input, tile_bt_input;
            wire [15:0] tile_read_slot;
            wire [255:0] tile_a_output, tile_b_output;
            wire [111:0] tile_at_output, tile_bt_output;
            wire [1023:0] tile_read_data;
            wire [3:0] tile_boundary_done;
            wire [15:0] tile_boundary_slot;
            for (genvar i=0; i<4; i++) begin : tile_edge
                localparam int R = tr*4+i;
                localparam int C = tc*4+i;
                assign tile_a_input[i*64 +: 64] =
                    tc == 0 ? a_enter_data[R] : a_tile_forward[R][tc-1];
                assign tile_at_input[i*TOKEN_BITS +: TOKEN_BITS] =
                    tc == 0 ? a_enter_token[R] : at_tile_forward[R][tc-1];
                assign tile_b_input[i*64 +: 64] =
                    tr == 0 ? b_enter_data[C] : b_tile_forward[tr-1][C];
                assign tile_bt_input[i*TOKEN_BITS +: TOKEN_BITS] =
                    tr == 0 ? b_enter_token[C] : bt_tile_forward[tr-1][C];
                assign tile_read_slot[i*4 +: 4] = row_read_slot[R];
                assign a_tile_forward[R][tc] = tile_a_output[i*64 +: 64];
                assign at_tile_forward[R][tc] =
                    tile_at_output[i*TOKEN_BITS +: TOKEN_BITS];
                assign b_tile_forward[tr][C] = tile_b_output[i*64 +: 64];
                assign bt_tile_forward[tr][C] =
                    tile_bt_output[i*TOKEN_BITS +: TOKEN_BITS];
                assign row_read_data[R][tc*256 +: 256] =
                    tile_read_data[i*256 +: 256];
                if (tc == 3) begin : far_edge
                    assign pe_boundary_done[R] = tile_boundary_done[i];
                    assign pe_boundary_slot[R] =
                        tile_boundary_slot[i*4 +: 4];
                end
            end
            t10_reference_tile_4x4 tile (
                .clk, .rst_n,
                .a_in_data(tile_a_input), .a_in_token(tile_at_input),
                .b_in_data(tile_b_input), .b_in_token(tile_bt_input),
                .a_out_data(tile_a_output), .a_out_token(tile_at_output),
                .b_out_data(tile_b_output), .b_out_token(tile_bt_output),
                .read_slot(tile_read_slot), .read_data(tile_read_data),
                .boundary_done(tile_boundary_done),
                .boundary_slot(tile_boundary_slot)
            );
        end
    end
    for (genvar r=0; r<16; r++) begin : result_row
        logic row_consumed_now;
        always_comb begin
            row_consumed_now = 1'b0;
            for (int s=0; s<4; s++)
                if (source_valid[s] && source_row[s*4 +: 4] == 4'(r))
                    row_consumed_now = 1'b1;
        end
        // Each row is read once per block. The earliest revisit is four
        // cycles later, leaving room for two registered consume pulses,
        // a local slot update, and the bank's registered read address.
        always_ff @(posedge clk or negedge rst_n) begin
            if (!rst_n) begin
                row_consumed_pipe1[r] <= 1'b0;
                row_consumed_pipe2[r] <= 1'b0;
                row_read_slot[r] <= '0;
            end else begin
                row_consumed_pipe1[r] <= output_fire && row_consumed_now;
                row_consumed_pipe2[r] <= row_consumed_pipe1[r];
                if (row_consumed_pipe2[r])
                    row_read_slot[r] <= next_slot(row_read_slot[r]);
            end
        end
    end

    always_comb begin
        case (slot_mode[read_slot])
            1, 2, 3: rows_per_cycle = 3'd1;
            6, 9: rows_per_cycle = 3'd4;
            default: rows_per_cycle = 3'd2;
        endcase
        source_valid = '0;
        source_block_id = '0;
        source_row = '0;
        for (int s=0; s<4; s++) begin
            if (complete[read_slot] && s<int'(rows_per_cycle) &&
                int'(output_row)+s<16) begin
                source_valid[s] = 1'b1;
                source_block_id[s*16 +: 16] = slot_id[read_slot];
                source_row[s*4 +: 4] = 4'(int'(output_row)+s);
            end
        end
    end

    // Each tile now owns the distributed result capture registers at its
    // read-data boundary. Elastic local four-row groups feed the final
    // four-group OR without another chip-level capture stage.
    // A two-entry circular output queue cuts external out_ready off from both
    // the gather pipeline and the wide data-bank write enables.  Backpressure
    // changes only the two-bit count and the read pointer; a push writes one
    // fixed bank selected by the write pointer.  The conservative full flag
    // deliberately does not borrow same-cycle pop credit.  In steady state
    // count remains one and one push plus one pop still completes every beat.
    assign final_stage_ready = output_queue_count != 2;
    assign output_stage_ready = !(|output_stage_valid) || final_stage_ready;
    assign gather_stage_ready = !(|gather_valid) || output_stage_ready;
    assign source_ready = !(|prefetch_valid) || gather_stage_ready;
    assign output_fire = (|source_valid) && source_ready;
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) prefetch_valid <= '0;
        else if (source_ready) prefetch_valid <= source_valid;
    end
    always_ff @(posedge clk) begin
        if (output_fire) begin
            prefetch_block_id <= source_block_id;
            prefetch_row <= source_row;
        end
    end
    // The tile output register already retains the 38 useful bits. Wiring
    // those bits into the gather network preserves the previous pipeline
    // latency while keeping the register physically inside each tile.
    for (genvar r=0; r<16; r++) begin : captured_row
        for (genvar c=0; c<16; c++) begin : captured_cell
            assign row_capture_data[r][c*38 +: 38] =
                row_read_data[r][c*64 +: 38];
        end
    end
    for (genvar r=0; r<16; r++) begin : local_row_select
        for (genvar s=0; s<4; s++) begin : slot
            always_ff @(posedge clk)
                if (source_ready)
                    prefetch_row_select[r][s] <=
                        source_valid[s] && source_row[s*4 +: 4] == 4'(r);
        end
    end
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) gather_valid <= '0;
        else if (gather_stage_ready) gather_valid <= prefetch_valid;
    end
    always_ff @(posedge clk) begin
        if (gather_stage_ready && (|prefetch_valid)) begin
            gather_block_id <= prefetch_block_id;
            gather_row <= prefetch_row;
        end
    end
    // Preserve local selections while stalled.  Each 38-bit result lane owns
    // its skid selector and data register.  A single chip-wide skid_valid
    // would otherwise select all 9,728 gather bits and create a physically
    // unbufferable control path across the complete 16x16 top level.
    for (genvar s=0; s<4; s++) begin : gather_slot
        for (genvar g=0; g<4; g++) begin : gather_group
            for (genvar c=0; c<16; c++) begin : gather_cell
                t10_reference_gather_lane gather_lane (
                    .clk,
                    .rst_n,
                    .gather_stage_ready,
                    .prefetch_any_valid(prefetch_valid[s]),
                    .row_select({prefetch_row_select[g*4+3][s],
                                 prefetch_row_select[g*4+2][s],
                                 prefetch_row_select[g*4+1][s],
                                 prefetch_row_select[g*4+0][s]}),
                    .source_data_0(row_capture_data[g*4+0][c*38 +: 38]),
                    .source_data_1(row_capture_data[g*4+1][c*38 +: 38]),
                    .source_data_2(row_capture_data[g*4+2][c*38 +: 38]),
                    .source_data_3(row_capture_data[g*4+3][c*38 +: 38]),
                    .gather_data(gather_group_data[s][g][c*38 +: 38])
                );
            end
        end
    end
    // The second stage combines only four registered local groups per slot.
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) output_stage_valid <= '0;
        else if (output_stage_ready) output_stage_valid <= gather_valid;
    end
    always_ff @(posedge clk) begin
        if (output_stage_ready && (|gather_valid)) begin
            output_stage_block_id <= gather_block_id;
            output_stage_row <= gather_row;
        end
    end
    // Duplicate the valid state beside each 38-bit output lane.  The logical
    // stage still exposes one four-bit valid vector, while each lane derives
    // its own hold enable locally instead of distributing one enable across
    // all 2,432 data bits.
    for (genvar s=0; s<4; s++) begin : compact_slot
        for (genvar c=0; c<16; c++) begin : compact_cell
            t10_reference_output_stage_lane output_stage_lane (
                .clk,
                .rst_n,
                .final_stage_ready,
                .gather_valid(gather_valid[s]),
                .group_data_0(gather_group_data[s][0][c*38 +: 38]),
                .group_data_1(gather_group_data[s][1][c*38 +: 38]),
                .group_data_2(gather_group_data[s][2][c*38 +: 38]),
                .group_data_3(gather_group_data[s][3][c*38 +: 38]),
                .compact_data(output_stage_compact_data[s*608 + c*38 +: 38])
            );
        end
    end
    // Only 38 result bits carry information inside the queue.  Reconstruct
    // the 64-bit external lanes at the final port, saving 1,664 state bits in
    // each of the output-stage and two circular queue entries.
    assign out_valid = output_queue_count == 0 ? '0 :
                       (output_queue_read_ptr ? output_queue_valid_1 :
                                                output_queue_valid_0);
    assign out_block_id = output_queue_read_ptr ? output_queue_block_id_1 :
                                                  output_queue_block_id_0;
    assign out_row = output_queue_read_ptr ? output_queue_row_1 :
                                             output_queue_row_0;
    for (genvar s=0; s<4; s++) begin : output_expand_slot
        for (genvar c=0; c<16; c++) begin : output_expand_cell
            wire [37:0] output_lane_data;
            t10_reference_output_queue_lane output_lane (
                .clk,
                .rst_n,
                .write_enable(final_push),
                .write_select(output_queue_write_ptr),
                .write_data(output_stage_compact_data[s*608 + c*38 +: 38]),
                .read_advance(final_pop),
                .read_data(output_lane_data)
            );
            assign out_data[s*1024 + c*64 +: 64] =
                {{26{output_lane_data[37]}}, output_lane_data};
        end
    end
    assign final_push = (|output_stage_valid) && final_stage_ready;
    assign final_pop = (|out_valid) && out_ready;
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            output_queue_count <= '0;
            output_queue_read_ptr <= 1'b0;
            output_queue_write_ptr <= 1'b0;
            output_queue_valid_0 <= '0;
            output_queue_valid_1 <= '0;
        end else begin
            case ({final_pop, final_push})
                2'b01: output_queue_count <= output_queue_count + 2'd1;
                2'b10: output_queue_count <= output_queue_count - 2'd1;
                default: output_queue_count <= output_queue_count;
            endcase
            if (final_push) begin
                if (output_queue_write_ptr)
                    output_queue_valid_1 <= output_stage_valid;
                else
                    output_queue_valid_0 <= output_stage_valid;
                output_queue_write_ptr <= ~output_queue_write_ptr;
            end
            if (final_pop)
                output_queue_read_ptr <= ~output_queue_read_ptr;
        end
    end
    always_ff @(posedge clk) begin
        if (final_push) begin
            if (output_queue_write_ptr) begin
                output_queue_block_id_1 <= output_stage_block_id;
                output_queue_row_1 <= output_stage_row;
            end else begin
                output_queue_block_id_0 <= output_stage_block_id;
                output_queue_row_0 <= output_stage_row;
            end
        end
    end
    assign next_output_row = {1'b0, output_row} + {2'b0, rows_per_cycle};
    assign output_last = output_fire && next_output_row >= 5'd16;
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            active <= 1'b0;
            beat_q <= '0;
            mode_q <= '0;
            active_slot <= '0;
            write_slot <= '0;
            read_slot <= '0;
            write_wrap <= 1'b0;
            read_wrap <= 1'b0;
            output_row <= '0;
            for (int slot=0; slot<SLOT_COUNT; slot++) begin
                complete[slot] <= 1'b0;
                slot_id[slot] <= '0;
                slot_mode[slot] <= '0;
            end
        end else begin
            if (input_first) begin
                active <= 1'b1;
                beat_q <= 5'd1;
                mode_q <= ingress_mode;
                active_slot <= write_slot;
                slot_id[write_slot] <= ingress_block_id;
                slot_mode[write_slot] <= ingress_mode;
                complete[write_slot] <= 1'b0;
                if (write_slot == 4'd15)
                    write_wrap <= ~write_wrap;
                write_slot <= next_slot(write_slot);
            end else if (input_fire) begin
                if (input_last) begin
                    active <= 1'b0;
                    beat_q <= '0;
                end else beat_q <= beat_q + 5'd1;
            end
            // Start a block's w-cycle readout when the row that is w rows
            // from the end is ready. All later row groups then become ready
            // one cycle at a time, without waiting for the entire block.
            for (int r=0; r<16; r++) begin
                if (pe_boundary_done_s2[r] &&
                    ((r == 0 && (slot_mode[pe_boundary_slot_s2[r]] == 4'd1 ||
                                 slot_mode[pe_boundary_slot_s2[r]] == 4'd2 ||
                                 slot_mode[pe_boundary_slot_s2[r]] == 4'd3)) ||
                     (r == 12 && (slot_mode[pe_boundary_slot_s2[r]] == 4'd6 ||
                                  slot_mode[pe_boundary_slot_s2[r]] == 4'd9)) ||
                     (r == 8 && !(slot_mode[pe_boundary_slot_s2[r]] == 4'd1 ||
                                  slot_mode[pe_boundary_slot_s2[r]] == 4'd2 ||
                                  slot_mode[pe_boundary_slot_s2[r]] == 4'd3 ||
                                  slot_mode[pe_boundary_slot_s2[r]] == 4'd6 ||
                                  slot_mode[pe_boundary_slot_s2[r]] == 4'd9))))
                    complete[pe_boundary_slot_s2[r]] <= 1'b1;
            end
            if (output_last) begin
                complete[read_slot] <= 1'b0;
                if (read_slot == 4'd15)
                    read_wrap <= ~read_wrap;
                read_slot <= next_slot(read_slot);
                output_row <= '0;
            end else if (output_fire)
                output_row <= next_output_row[3:0];
        end
    end
endmodule

// Local 38-bit output stage.  valid_q mirrors its slot's architectural valid
// bit, but sits beside the data flops so the elastic hold mux stays local.
(* keep_hierarchy = "yes" *) module t10_reference_output_stage_lane (
    input  logic        clk,
    input  logic        rst_n,
    input  logic        final_stage_ready,
    input  logic        gather_valid,
    input  logic [37:0] group_data_0,
    input  logic [37:0] group_data_1,
    input  logic [37:0] group_data_2,
    input  logic [37:0] group_data_3,
    output logic [37:0] compact_data
);
    logic valid_q;
    wire lane_ready = !valid_q || final_stage_ready;

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n)
            valid_q <= 1'b0;
        else if (lane_ready)
            valid_q <= gather_valid;
    end
    always_ff @(posedge clk) begin
        if (lane_ready && gather_valid)
            compact_data <= group_data_0 | group_data_1 |
                            group_data_2 | group_data_3;
    end
endmodule

// Local elastic gather lane.  Replicating the one-bit skid state is a small
// area cost that confines every hold-data mux to one 38-bit result lane.
(* keep_hierarchy = "yes" *) module t10_reference_gather_lane (
    input  logic        clk,
    input  logic        rst_n,
    input  logic        gather_stage_ready,
    input  logic        prefetch_any_valid,
    input  logic [3:0]  row_select,
    input  logic [37:0] source_data_0,
    input  logic [37:0] source_data_1,
    input  logic [37:0] source_data_2,
    input  logic [37:0] source_data_3,
    output logic [37:0] gather_data
);
    logic skid_valid;
    logic [37:0] skid_data;
    logic [37:0] selected_source;

    always_comb begin
        selected_source = (source_data_0 & {38{row_select[0]}}) |
                          (source_data_1 & {38{row_select[1]}}) |
                          (source_data_2 & {38{row_select[2]}}) |
                          (source_data_3 & {38{row_select[3]}});
    end

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n)
            skid_valid <= 1'b0;
        else if (gather_stage_ready)
            skid_valid <= 1'b0;
        else if (prefetch_any_valid && !skid_valid)
            skid_valid <= 1'b1;
    end
    always_ff @(posedge clk) begin
        if (!gather_stage_ready && prefetch_any_valid && !skid_valid)
            skid_data <= selected_source;
        if (gather_stage_ready && prefetch_any_valid)
            gather_data <= skid_valid ? skid_data : selected_source;
    end
endmodule

// One result lane owns both queue banks and its read selector.  Replicating
// this small selector per 38-bit lane keeps the external ready signal away
// from the 2,432-bit data path and prevents synthesis from inferring one
// monolithic 4,864-bit memory at the full-chip level.
(* keep_hierarchy = "yes" *) module t10_reference_output_queue_lane (
    input  logic        clk,
    input  logic        rst_n,
    input  logic        write_enable,
    input  logic        write_select,
    input  logic [37:0] write_data,
    input  logic        read_advance,
    output logic [37:0] read_data
);
    logic [37:0] data_bank_0, data_bank_1;
    logic read_select;

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n)
            read_select <= 1'b0;
        else if (read_advance)
            read_select <= ~read_select;
    end
    always_ff @(posedge clk) begin
        if (write_enable) begin
            if (write_select)
                data_bank_1 <= write_data;
            else
                data_bank_0 <= write_data;
        end
    end
    assign read_data = read_select ? data_bank_1 : data_bank_0;
endmodule

// A physical 4x4 compute tile. The interior forward links stay inside this
// boundary; the result-quarter banks sit beside their four local PE rows.
module t10_reference_tile_4x4 (
    input  logic          clk,
    input  logic          rst_n,
    input  logic [255:0]  a_in_data,
    input  logic [111:0]  a_in_token,
    input  logic [255:0]  b_in_data,
    input  logic [111:0]  b_in_token,
    output logic [255:0]  a_out_data,
    output logic [111:0]  a_out_token,
    output logic [255:0]  b_out_data,
    output logic [111:0]  b_out_token,
    input  logic [15:0]   read_slot,
    output logic [1023:0] read_data,
    output logic [3:0]    boundary_done,
    output logic [15:0]   boundary_slot
);
    localparam int TOKEN_BITS = 28;
    logic [63:0] a_forward [0:3][0:3];
    logic [63:0] b_forward [0:3][0:3];
    logic [TOKEN_BITS-1:0] at_forward [0:3][0:3];
    logic [TOKEN_BITS-1:0] bt_forward [0:3][0:3];
    logic [63:0] pe_sum [0:3][0:3];
    logic pe_done [0:3][0:3];
    logic [3:0] pe_slot [0:3][0:3];

    for (genvar r=0; r<4; r++) begin : pe_row
        assign a_out_data[r*64 +: 64] = a_forward[r][3];
        assign a_out_token[r*TOKEN_BITS +: TOKEN_BITS] = at_forward[r][3];
        assign boundary_done[r] = pe_done[r][3];
        assign boundary_slot[r*4 +: 4] = pe_slot[r][3];
        for (genvar c=0; c<4; c++) begin : pe_col
            wire [63:0] a_input, b_input;
            wire [TOKEN_BITS-1:0] at_input, bt_input;
            assign a_input = c == 0 ? a_in_data[r*64 +: 64] :
                                      a_forward[r][c-1];
            assign at_input = c == 0 ? a_in_token[r*TOKEN_BITS +: TOKEN_BITS] :
                                       at_forward[r][c-1];
            assign b_input = r == 0 ? b_in_data[c*64 +: 64] :
                                      b_forward[r-1][c];
            assign bt_input = r == 0 ? b_in_token[c*TOKEN_BITS +: TOKEN_BITS] :
                                       bt_forward[r-1][c];
            t10_reference_pe pe (
                .clk, .rst_n,
                .a_in(a_input), .b_in(b_input),
                .at_in(at_input), .bt_in(bt_input),
                .a_out(a_forward[r][c]), .b_out(b_forward[r][c]),
                .at_out(at_forward[r][c]), .bt_out(bt_forward[r][c]),
                .result(pe_sum[r][c]), .result_valid(pe_done[r][c]),
                .result_slot(pe_slot[r][c])
            );
        end
    end
    for (genvar c=0; c<4; c++) begin : bottom_edge
        assign b_out_data[c*64 +: 64] = b_forward[3][c];
        assign b_out_token[c*TOKEN_BITS +: TOKEN_BITS] = bt_forward[3][c];
    end
    for (genvar r=0; r<4; r++) begin : result_row
        wire [151:0] compact_write_data;
        wire [15:0] compact_write_group;
        wire [7:0] compact_write_low;
        // A local registered result hop in every column separates PE macro
        // output timing from the bank input. Reset only the narrow valid path;
        // data and slot values are ignored until their one-hot group is valid.
        // Earlier columns take proportionally more hops to align the wavefront.
        for (genvar c=0; c<4; c++) begin : result_cell
            // The bank has an internal input hop in columns 0..2; column 3
            // writes directly. These stages retain column alignment and add
            // two cycles to each result relative to the preceding reference.
            localparam int STAGES = c == 3 ? 2 : 4 - c;
            logic [37:0] data_pipe [0:STAGES];
            logic [3:0] slot_pipe [0:STAGES];
            logic valid_pipe [0:STAGES];
            logic [3:0] write_group_q;
            assign data_pipe[0] = pe_sum[r][c][37:0];
            assign slot_pipe[0] = pe_slot[r][c];
            assign valid_pipe[0] = pe_done[r][c];
            for (genvar stage=1; stage<=STAGES; stage++) begin : hop
                always_ff @(posedge clk) begin
                    data_pipe[stage] <= data_pipe[stage-1];
                    slot_pipe[stage] <= slot_pipe[stage-1];
                end
                always_ff @(posedge clk or negedge rst_n) begin
                    if (!rst_n)
                        valid_pipe[stage] <= 1'b0;
                    else
                        valid_pipe[stage] <= valid_pipe[stage-1];
                end
                if (stage == STAGES) begin : final_write_decode
                    // Decode into the final hop register so the bank receives
                    // local one-hot control instead of a late valid/slot cone.
                    always_ff @(posedge clk or negedge rst_n) begin
                        if (!rst_n)
                            write_group_q <= '0;
                        else if (valid_pipe[stage-1])
                            write_group_q <= 4'b0001 <<
                                             slot_pipe[stage-1][3:2];
                        else
                            write_group_q <= '0;
                    end
                end
            end
            assign compact_write_data[c*38 +: 38] = data_pipe[STAGES];
            assign compact_write_group[c*4 +: 4] = write_group_q;
            assign compact_write_low[c*2 +: 2] = slot_pipe[STAGES][1:0];
        end
        t10_reference_result_quarter bank (
            .clk, .rst_n,
            .read_slot(read_slot[r*4 +: 4]),
            .write_group(compact_write_group),
            .write_low(compact_write_low),
            .write_data(compact_write_data),
            .read_data(read_data[r*256 +: 256])
        );
    end
endmodule

// Select the live block slot within each row before the four-row output mux.
// This gives the twelve-deep result store one read mux per cell instead of
// a separate four-row read mux for every block slot.
(* keep_hierarchy = "yes" *) module t10_reference_result_quarter (
    input  logic clk,
    input  logic rst_n,
    input  logic [3:0] read_slot,
    input  logic [15:0] write_group,
    input  logic [7:0] write_low,
    input  logic [151:0] write_data,
    output logic [255:0] read_data
);
    /* verilator hier_block */
    for (genvar c=0; c<4; c++) begin : cell_bank
        // A hard hierarchy boundary prevents synthesis from merging the four
        // equivalent read-address registers back into one tile-wide net.
        t10_reference_result_cell_bank bank (
            .clk,
            .rst_n,
            .read_slot,
            .write_group(write_group[c*4 +: 4]),
            .write_low(write_low[c*2 +: 2]),
            .write_data(write_data[c*38 +: 38]),
            .read_data(read_data[c*64 +: 64])
        );
    end
endmodule

// Keep every cell's sixteen-entry result store, address register, and output
// register physically local.  This module boundary is part of the physical
// architecture: without it, synthesis legally merges the equivalent address
// registers and recreates a tile-wide high-fanout timing path.
(* keep_hierarchy = "yes" *) module t10_reference_result_cell_bank (
    input  logic        clk,
    input  logic        rst_n,
    input  logic [3:0]  read_slot,
    input  logic [3:0]  write_group,
    input  logic [1:0]  write_low,
    input  logic [37:0] write_data,
    output logic [63:0] read_data
);
    // INT16's 64-term dot product fits signed 38 bits; the FP result occupies
    // only the low 32 bits.  Sign extension reconstructs exact INT outputs.
    logic [37:0] cell_data [0:15];
    logic [3:0] read_slot_q;
    logic [37:0] read_data_q;
    logic [37:0] stored_write_data;
    logic [3:0] stored_write_group;
    logic [1:0] stored_write_low;

    always_ff @(posedge clk) begin
        read_slot_q <= read_slot;
        stored_write_data <= write_data;
        stored_write_low <= write_low;
        read_data_q <= cell_data[read_slot_q];
    end
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n)
            stored_write_group <= '0;
        else
            stored_write_group <= write_group;
    end
    for (genvar slot=0; slot<16; slot++) begin : slot_bank
        always_ff @(posedge clk)
            if (stored_write_group[slot/4] &&
                stored_write_low == 2'(slot%4))
                cell_data[slot] <= stored_write_data;
    end
    assign read_data = {{26{read_data_q[37]}}, read_data_q};
endmodule

// One shared mapping of the finite floating-point term generator is used
// by all sixteen lanes of every PE. Keeping this boundary also prevents
// standard-cell mapping from treating the complete PE as one huge cone.
(* keep_hierarchy = "yes" *) module t10_reference_fp_lane #(
    parameter int SUPPORT_CLASS = 0
) (
    input  logic clk,
    input  logic [15:0] a_raw, b_raw,
    input  logic [3:0] mode,
    input  logic lane_active,
    input  logic [7:0] a_scale, b_scale,
    output logic [579:0] term_word,
    output logic negative, nan_value, plus_inf, minus_inf
);
    /* verilator hier_block */
    localparam int EXACT_BITS = 580;
    localparam int EXACT_LSB = -286;
    typedef struct packed {
        logic sign;
        logic nan_value;
        logic infinity;
        logic [10:0] mantissa;
        logic signed [10:0] exponent;
    } decoded_t;

    function automatic decoded_t decode_float(input logic [15:0] raw,
                                                input logic [3:0] format,
                                                input logic [7:0] scale);
        decoded_t value;
        begin
            value = '0;
            case (format)
                4'd2: if (SUPPORT_CLASS == 0) begin // binary16
                    value.sign = raw[15];
                    value.mantissa = raw[14:10] == 0 ? 11'(raw[9:0]) :
                                     {1'b1,raw[9:0]};
                    value.exponent = raw[14:10] == 0 ? -11'sd24 :
                                     $signed({6'b0,raw[14:10]}) - 11'sd25;
                    value.nan_value = raw[14:10] == 5'h1f && raw[9:0] != 0;
                    value.infinity = raw[14:10] == 5'h1f && raw[9:0] == 0;
                end
                4'd3: if (SUPPORT_CLASS == 0) begin // bfloat16
                    value.sign = raw[15];
                    value.mantissa = raw[14:7] == 0 ? 11'(raw[6:0]) :
                                     11'({3'b001,raw[6:0]});
                    value.exponent = raw[14:7] == 0 ? -11'sd133 :
                                     $signed({3'b0,raw[14:7]}) - 11'sd134;
                    value.nan_value = raw[14:7] == 8'hff && raw[6:0] != 0;
                    value.infinity = raw[14:7] == 8'hff && raw[6:0] == 0;
                end
                4'd4, 4'd7: if (SUPPORT_CLASS <= 1) begin // OFP8 E4M3
                    value.sign = raw[7];
                    value.mantissa = raw[6:3] == 0 ? 11'(raw[2:0]) :
                                     11'({7'b0000001,raw[2:0]});
                    value.exponent = raw[6:3] == 0 ? -11'sd9 :
                                     $signed({7'b0,raw[6:3]}) - 11'sd10;
                    value.nan_value = raw[6:3] == 4'hf && raw[2:0] == 3'h7;
                end
                4'd5, 4'd8: if (SUPPORT_CLASS <= 1) begin // OFP8 E5M2
                    value.sign = raw[7];
                    value.mantissa = raw[6:2] == 0 ? 11'(raw[1:0]) :
                                     11'({8'b00000001,raw[1:0]});
                    value.exponent = raw[6:2] == 0 ? -11'sd16 :
                                     $signed({6'b0,raw[6:2]}) - 11'sd17;
                    value.nan_value = raw[6:2] == 5'h1f && raw[1:0] != 0;
                    value.infinity = raw[6:2] == 5'h1f && raw[1:0] == 0;
                end
                default: begin // E2M1 for FP4 and MXFP4
                    value.sign = raw[3];
                    value.mantissa = raw[2:1] == 0 ? 11'(raw[0]) :
                                     11'({9'b000000001,raw[0]});
                    value.exponent = raw[2:1] == 0 ? -11'sd1 :
                                     $signed({9'b0,raw[2:1]}) - 11'sd2;
                end
            endcase
            if (format == 4'd7 || format == 4'd8 || format == 4'd9) begin
                if (scale == 8'hff) value.nan_value = 1'b1;
                else value.exponent = value.exponent +
                    ($signed({3'b0,scale}) - 11'sd127);
            end
            decode_float = value;
        end
    endfunction

    // Decode only the mantissa before the product stage. Scale and special
    // value handling stay on the existing parallel metadata path.
    function automatic logic [10:0] decode_mantissa_fast(
        input logic [15:0] raw, input logic [3:0] format);
        case (format)
            4'd2: decode_mantissa_fast = {raw[14:10] != 5'd0, raw[9:0]};
            4'd3: decode_mantissa_fast =
                {3'b0, raw[14:7] != 8'd0, raw[6:0]};
            4'd4, 4'd7: decode_mantissa_fast =
                {7'b0, raw[6:3] != 4'd0, raw[2:0]};
            4'd5, 4'd8: decode_mantissa_fast =
                {8'b0, raw[6:2] != 5'd0, raw[1:0]};
            default: decode_mantissa_fast =
                {9'b0, raw[2:1] != 2'd0, raw[0]};
        endcase
    endfunction

    // Register the cross-macro interface before format decode. This gives
    // both the mode fanout and the decode path a full local clock cycle.
    logic [15:0] a_input_q, b_input_q;
    logic [3:0] mode_input_q;
    logic [7:0] a_scale_input_q, b_scale_input_q;
    logic lane_input_active_q;
    logic [10:0] a_mantissa_input_q, b_mantissa_input_q;
    always_ff @(posedge clk) begin
        a_input_q <= a_raw;
        b_input_q <= b_raw;
        mode_input_q <= mode;
        a_scale_input_q <= a_scale;
        b_scale_input_q <= b_scale;
        lane_input_active_q <= lane_active;
        if (SUPPORT_CLASS == 0) begin
            a_mantissa_input_q <= decode_mantissa_fast(a_raw,mode);
            b_mantissa_input_q <= decode_mantissa_fast(b_raw,mode);
        end
    end
    decoded_t left_value, right_value;
    decoded_t left_decoded, right_decoded;
    logic [11:0] product_ll_q;
    logic [10:0] product_lh_q, product_hl_q;
    logic [9:0] product_hh_q;
    logic lane_active_q;
    always_comb begin
        left_decoded = decode_float(a_input_q,mode_input_q,a_scale_input_q);
        right_decoded = decode_float(b_input_q,mode_input_q,b_scale_input_q);
    end
    always_ff @(posedge clk) begin
        left_value <= left_decoded;
        right_value <= right_decoded;
        if (SUPPORT_CLASS == 0) begin
            product_ll_q <= a_mantissa_input_q[5:0] *
                            b_mantissa_input_q[5:0];
            product_lh_q <= a_mantissa_input_q[5:0] *
                            b_mantissa_input_q[10:6];
            product_hl_q <= a_mantissa_input_q[10:6] *
                            b_mantissa_input_q[5:0];
            product_hh_q <= a_mantissa_input_q[10:6] *
                            b_mantissa_input_q[10:6];
        end
        lane_active_q <= lane_input_active_q;
    end
    logic [21:0] term_mantissa, term_mantissa_q;
    wire [21:0] product_part0 = 22'(product_ll_q);
    wire [21:0] product_part1 = 22'(product_lh_q) << 6;
    wire [21:0] product_part2 = 22'(product_hl_q) << 6;
    wire [21:0] product_part3 = 22'(product_hh_q) << 12;
    wire [21:0] product_sum0 = product_part0 ^ product_part1 ^ product_part2;
    wire [21:0] product_carry0 =
        ((product_part0 & product_part1) | (product_part0 & product_part2) |
         (product_part1 & product_part2)) << 1;
    wire [21:0] product_sum1 = product_sum0 ^ product_carry0 ^ product_part3;
    wire [21:0] product_carry1 =
        ((product_sum0 & product_carry0) | (product_sum0 & product_part3) |
         (product_carry0 & product_part3)) << 1;
    logic [EXACT_BITS-1:0] term_magnitude;
    logic signed [11:0] term_shift, term_shift_q;
    logic product_negative, product_negative_q;
    logic finite_value, finite_q;
    logic nan_next, plus_inf_next, minus_inf_next;
    logic negative_pre, nan_pre, plus_inf_pre, minus_inf_pre;
    always_comb begin
        product_negative = left_value.sign ^ right_value.sign;
        term_mantissa = SUPPORT_CLASS == 0 ?
                        product_sum1 + product_carry1 :
                        left_value.mantissa * right_value.mantissa;
        term_shift = 12'(left_value.exponent) +
                     12'(right_value.exponent) - 12'(EXACT_LSB);
        nan_next = 1'b0;
        plus_inf_next = 1'b0;
        minus_inf_next = 1'b0;
        finite_value = 1'b0;
        if (lane_active_q) begin
            if (left_value.nan_value || right_value.nan_value ||
                ((left_value.infinity || right_value.infinity) &&
                 (left_value.mantissa==0 || right_value.mantissa==0)))
                nan_next = 1'b1;
            else if (left_value.infinity || right_value.infinity) begin
                if (product_negative) minus_inf_next = 1'b1;
                else plus_inf_next = 1'b1;
            end else finite_value = 1'b1;
        end
    end
    always_ff @(posedge clk) begin
        term_mantissa_q <= term_mantissa;
        term_shift_q <= term_shift;
        product_negative_q <= product_negative;
        finite_q <= finite_value;
        negative_pre <= finite_value && product_negative;
        nan_pre <= nan_next;
        plus_inf_pre <= plus_inf_next;
        minus_inf_pre <= minus_inf_next;
    end
    always_comb begin
        term_magnitude = {{(EXACT_BITS-22){1'b0}},term_mantissa_q};
        if (term_shift_q>=0 && term_shift_q<12'(EXACT_BITS))
            term_magnitude = term_magnitude << term_shift_q;
        else term_magnitude = '0;
    end
    always_ff @(posedge clk) begin
        term_word <= finite_q ?
            (product_negative_q ? ~term_magnitude : term_magnitude) : '0;
        negative <= negative_pre;
        nan_value <= nan_pre;
        plus_inf <= plus_inf_pre;
        minus_inf <= minus_inf_pre;
    end
endmodule

// Keep four floating lanes and their first carry-save reduction inside one
// physical child. This halves the number of 580-bit result nets crossing the
// PE floorplan and leaves the beat-to-feedback latency unchanged.
(* keep_hierarchy = "yes" *) module t10_reference_fp_quad #(
    parameter int SUPPORT_CLASS = 0
) (
    input logic clk,
    input logic [63:0] a_raw, b_raw,
    input logic [3:0] mode,
    input logic [3:0] lane_active,
    input logic [7:0] a_scale, b_scale,
    output logic [579:0] sum_word, carry_word,
    output logic [2:0] negative_count,
    output logic nan_value, plus_inf, minus_inf
);
    localparam int EXACT_BITS = 580;
    if (SUPPORT_CLASS == 2) begin : fp4_only
        t10_reference_fp4_quad fp4_quad (.*);
    end else begin : general
    logic [EXACT_BITS-1:0] term_word [0:3];
    logic [3:0] negative, nan_lane, plus_inf_lane, minus_inf_lane;
    logic [EXACT_BITS-1:0] sum0, carry0, sum1, carry1;
    for (genvar lane=0; lane<4; lane++) begin : lanes
        t10_reference_fp_lane #(.SUPPORT_CLASS(SUPPORT_CLASS)) fp_lane (
            .clk,
            .a_raw(a_raw[lane*16 +: 16]),
            .b_raw(b_raw[lane*16 +: 16]),
            .mode,
            .lane_active(lane_active[lane]),
            .a_scale, .b_scale,
            .term_word(term_word[lane]),
            .negative(negative[lane]),
            .nan_value(nan_lane[lane]),
            .plus_inf(plus_inf_lane[lane]),
            .minus_inf(minus_inf_lane[lane])
        );
    end
    assign sum0 = term_word[0] ^ term_word[1] ^ term_word[2];
    assign carry0 = ((term_word[0] & term_word[1]) |
                     (term_word[0] & term_word[2]) |
                     (term_word[1] & term_word[2])) << 1;
    assign sum1 = sum0 ^ carry0 ^ term_word[3];
    assign carry1 = ((sum0 & carry0) | (sum0 & term_word[3]) |
                     (carry0 & term_word[3])) << 1;
    always_ff @(posedge clk) begin
        sum_word <= sum1;
        carry_word <= carry1;
        negative_count <= 3'($countones(negative));
        nan_value <= |nan_lane;
        plus_inf <= |plus_inf_lane;
        minus_inf <= |minus_inf_lane;
    end
    end
endmodule

// The last two quads only see FP4/MXFP4 lanes. Their four products share
// the same pair of MX scales, so add them at a small fixed exponent first
// and shift the signed sum into the exact accumulator position once.
module t10_reference_fp4_quad (
    input  logic clk,
    input  logic [63:0] a_raw, b_raw,
    input  logic [3:0] mode, lane_active,
    input  logic [7:0] a_scale, b_scale,
    output logic [579:0] sum_word, carry_word,
    output logic [2:0] negative_count,
    output logic nan_value, plus_inf, minus_inf
);
    localparam int EXACT_BITS = 580;
    logic [3:0] a_nibble_q1 [0:3], b_nibble_q1 [0:3];
    logic [3:0] mode_q1, active_q1, active_q2, active_q3;
    logic [7:0] a_scale_q1, b_scale_q1;
    logic [3:0] a_sign_q2, b_sign_q2;
    logic [1:0] a_mantissa_q2 [0:3], b_mantissa_q2 [0:3];
    logic signed [2:0] a_exponent_q2 [0:3], b_exponent_q2 [0:3];
    logic scale_nan_q2, scale_nan_q3, scale_nan_q4;
    logic [9:0] wide_shift_q2, wide_shift_q3, wide_shift_q4;
    logic [7:0] local_magnitude_q3 [0:3];
    logic [3:0] negative_q3;
    logic signed [10:0] local_total, local_total_q4;
    logic signed [10:0] local_term [0:3];
    logic signed [10:0] local_pair0, local_pair1;
    wire signed [EXACT_BITS-1:0] wide_total =
        {{(EXACT_BITS-11){local_total_q4[10]}}, local_total_q4};

    always_ff @(posedge clk) begin
        for (int lane=0; lane<4; lane++) begin
            a_nibble_q1[lane] <= a_raw[lane*16 +: 4];
            b_nibble_q1[lane] <= b_raw[lane*16 +: 4];
        end
        mode_q1 <= mode;
        active_q1 <= lane_active;
        a_scale_q1 <= a_scale;
        b_scale_q1 <= b_scale;
    end
    always_ff @(posedge clk) begin
        for (int lane=0; lane<4; lane++) begin
            a_sign_q2[lane] <= a_nibble_q1[lane][3];
            b_sign_q2[lane] <= b_nibble_q1[lane][3];
            a_mantissa_q2[lane] <= a_nibble_q1[lane][2:1] == 2'd0 ?
                                   {1'b0, a_nibble_q1[lane][0]} :
                                   {1'b1, a_nibble_q1[lane][0]};
            b_mantissa_q2[lane] <= b_nibble_q1[lane][2:1] == 2'd0 ?
                                   {1'b0, b_nibble_q1[lane][0]} :
                                   {1'b1, b_nibble_q1[lane][0]};
            a_exponent_q2[lane] <= a_nibble_q1[lane][2:1] == 2'd0 ?
                                   -3'sd1 :
                                   $signed({1'b0,a_nibble_q1[lane][2:1]}) - 3'sd2;
            b_exponent_q2[lane] <= b_nibble_q1[lane][2:1] == 2'd0 ?
                                   -3'sd1 :
                                   $signed({1'b0,b_nibble_q1[lane][2:1]}) - 3'sd2;
        end
        active_q2 <= active_q1;
        scale_nan_q2 <= mode_q1 == 4'd9 &&
                        (a_scale_q1 == 8'hff || b_scale_q1 == 8'hff);
        // E2M1 products have exponent sum -2..2. The local products are
        // shifted by exponent_sum+2; this offset is removed here.
        wide_shift_q2 <= mode_q1 == 4'd9 ?
                         10'd30 + 10'(a_scale_q1) + 10'(b_scale_q1) :
                         10'd284;
    end
    always_ff @(posedge clk) begin
        for (int lane=0; lane<4; lane++) begin
            local_magnitude_q3[lane] <=
                8'(a_mantissa_q2[lane] * b_mantissa_q2[lane]) <<
                3'($signed(a_exponent_q2[lane]) +
                   $signed(b_exponent_q2[lane]) + 4'sd2);
            negative_q3[lane] <= a_sign_q2[lane] ^ b_sign_q2[lane];
        end
        active_q3 <= active_q2;
        scale_nan_q3 <= scale_nan_q2;
        wide_shift_q3 <= wide_shift_q2;
    end
    always_comb begin
        for (int lane=0; lane<4; lane++) begin
            logic [7:0] magnitude;
            magnitude = local_magnitude_q3[lane];
            local_term[lane] = !active_q3[lane] ? '0 :
                               negative_q3[lane] ?
                               -$signed({3'b0, magnitude}) :
                               $signed({3'b0, magnitude});
        end
        local_pair0 = local_term[0] + local_term[1];
        local_pair1 = local_term[2] + local_term[3];
        local_total = local_pair0 + local_pair1;
    end
    always_ff @(posedge clk) begin
        local_total_q4 <= local_total;
        wide_shift_q4 <= wide_shift_q3;
        scale_nan_q4 <= scale_nan_q3 && (|active_q3);
    end
    always_ff @(posedge clk) begin
        sum_word <= scale_nan_q4 ? '0 : (wide_total <<< wide_shift_q4);
        carry_word <= '0;
        negative_count <= '0;
        nan_value <= scale_nan_q4;
        plus_inf <= 1'b0;
        minus_inf <= 1'b0;
    end
endmodule

(* keep_hierarchy = "yes" *) module t10_reference_int_group (
    input logic clk,
    input logic [15:0] a_work, b_work,
    input logic mode_int8,
    input logic integer_raw_input_valid, integer_raw_valid, integer_partial_valid,
    output wire [31:0] p8_pair,
    output wire [31:0] p16_out
);
    // Capture operands at the hard-macro boundary. This removes the
    // multiplier partial-product logic from the parent PE setup path.
    logic [15:0] a_operand_q, b_operand_q;
    logic mode_int8_operand_q;
    logic integer_raw_input_valid_q, integer_raw_valid_q;
    logic integer_partial_valid_q;
    always_ff @(posedge clk) begin
        a_operand_q <= a_work;
        b_operand_q <= b_work;
        mode_int8_operand_q <= mode_int8;
        integer_raw_input_valid_q <= integer_raw_input_valid;
        integer_raw_valid_q <= integer_raw_valid;
        integer_partial_valid_q <= integer_partial_valid;
    end
    logic [7:0] product8_p00_reg [0:1];
    logic signed [7:0] product8_p01_reg [0:1];
    logic signed [7:0] product8_p10_reg [0:1];
    logic signed [7:0] product8_p11_reg [0:1];
    logic signed [15:0] product8_delay [0:1];
    logic signed [15:0] product8_delay2 [0:1];
    logic [15:0] product_ll_pre_delay [0:0];
    logic signed [16:0] product_lh_reg [0:0];
    logic signed [16:0] product_hl_reg [0:0];
    logic signed [15:0] product_hh_pre_delay [0:0];
    logic [7:0] product_ll_p00_reg [0:0];
    logic [7:0] product_ll_p01_reg [0:0];
    logic [7:0] product_ll_p10_reg [0:0];
    logic [7:0] product_ll_p11_reg [0:0];
    logic [7:0] product_hh_p00_reg [0:0];
    logic signed [7:0] product_hh_p01_reg [0:0];
    logic signed [7:0] product_hh_p10_reg [0:0];
    logic signed [7:0] product_hh_p11_reg [0:0];
    logic [7:0] product_lh_00_reg [0:0];
    logic signed [7:0] product_lh_signed_mid_reg [0:0];
    logic [7:0] product_lh_unsigned_mid_reg [0:0];
    logic signed [7:0] product_lh_11_reg [0:0];
    logic [7:0] product_hl_00_reg [0:0];
    logic signed [7:0] product_hl_signed_mid_reg [0:0];
    logic [7:0] product_hl_unsigned_mid_reg [0:0];
    logic signed [7:0] product_hl_11_reg [0:0];
    logic [15:0] product_low_delay [0:0];
    logic signed [18:0] product_cross_delay [0:0];
    logic signed [15:0] product_high_delay [0:0];
    function automatic logic signed [16:0] recombine_4x4(
        input logic [7:0] p00,
        input logic signed [7:0] p_signed_mid,
        input logic [7:0] p_unsigned_mid,
        input logic signed [7:0] p11);
        logic [16:0] t0, t1, t2, t3, s0, c0, s1, c1;
        begin
            t0 = {9'b0,p00};
            t1 = {{9{p_signed_mid[7]}},p_signed_mid} << 4;
            t2 = {9'b0,p_unsigned_mid} << 4;
            t3 = {{9{p11[7]}},p11} << 8;
            s0 = t0 ^ t1 ^ t2;
            c0 = ((t0 & t1) | (t0 & t2) | (t1 & t2)) << 1;
            s1 = s0 ^ c0 ^ t3;
            c1 = ((s0 & c0) | (s0 & t3) | (c0 & t3)) << 1;
            recombine_4x4 = $signed(s1 + c1);
        end
    endfunction
    function automatic logic signed [15:0] recombine_signed8(
        input logic [7:0] p00,
        input logic signed [7:0] p01,
        input logic signed [7:0] p10,
        input logic signed [7:0] p11);
        logic [15:0] t0, t1, t2, t3, s0, c0, s1, c1;
        begin
            t0 = {8'b0,p00};
            t1 = {{8{p01[7]}},p01} << 4;
            t2 = {{8{p10[7]}},p10} << 4;
            t3 = {{8{p11[7]}},p11} << 8;
            s0 = t0 ^ t1 ^ t2;
            c0 = ((t0 & t1) | (t0 & t2) | (t1 & t2)) << 1;
            s1 = s0 ^ c0 ^ t3;
            c1 = ((s0 & c0) | (s0 & t3) | (c0 & t3)) << 1;
            recombine_signed8 = $signed(s1 + c1);
        end
    endfunction
    function automatic logic [15:0] recombine_unsigned8(
        input logic [7:0] p00,
        input logic [7:0] p01,
        input logic [7:0] p10,
        input logic [7:0] p11);
        logic [15:0] t0, t1, t2, t3, s0, c0, s1, c1;
        begin
            t0 = {8'b0,p00};
            t1 = {8'b0,p01} << 4;
            t2 = {8'b0,p10} << 4;
            t3 = {8'b0,p11} << 8;
            s0 = t0 ^ t1 ^ t2;
            c0 = ((t0 & t1) | (t0 & t2) | (t1 & t2)) << 1;
            s1 = s0 ^ c0 ^ t3;
            c1 = ((s0 & c0) | (s0 & t3) | (c0 & t3)) << 1;
            recombine_unsigned8 = s1 + c1;
        end
    endfunction
    for (genvar ilane=0; ilane<2; ilane++) begin : integer_lane
        wire [3:0] a8_lo = a_operand_q[ilane*8 +: 4];
        wire signed [3:0] a8_hi = a_operand_q[ilane*8+4 +: 4];
        wire [3:0] b8_lo = b_operand_q[ilane*8 +: 4];
        wire signed [3:0] b8_hi = b_operand_q[ilane*8+4 +: 4];
        always_ff @(posedge clk) if (integer_raw_input_valid_q &&
                                     mode_int8_operand_q) begin
            product8_p00_reg[ilane] <= a8_lo * b8_lo;
            product8_p01_reg[ilane] <= $signed({1'b0,a8_lo}) * b8_hi;
            product8_p10_reg[ilane] <= a8_hi * $signed({1'b0,b8_lo});
            product8_p11_reg[ilane] <= a8_hi * b8_hi;
        end
        if (ilane == 0) begin : int16_lane
            wire [3:0] a_lo_nibble0 = a_operand_q[ilane*16 +: 4];
            wire [3:0] a_lo_nibble1 = a_operand_q[ilane*16+4 +: 4];
            wire [3:0] b_lo_nibble0 = b_operand_q[ilane*16 +: 4];
            wire [3:0] b_lo_nibble1 = b_operand_q[ilane*16+4 +: 4];
            wire [3:0] a_hi_nibble0 = a_operand_q[ilane*16+8 +: 4];
            wire signed [3:0] a_hi_nibble1 = a_operand_q[ilane*16+12 +: 4];
            wire [3:0] b_hi_nibble0 = b_operand_q[ilane*16+8 +: 4];
            wire signed [3:0] b_hi_nibble1 = b_operand_q[ilane*16+12 +: 4];
            always_ff @(posedge clk)
                if (integer_raw_input_valid_q) begin
                    product_lh_00_reg[ilane] <=
                        a_lo_nibble0 * b_hi_nibble0;
                    product_lh_signed_mid_reg[ilane] <=
                        $signed({1'b0,a_lo_nibble0}) * b_hi_nibble1;
                    product_lh_unsigned_mid_reg[ilane] <=
                        a_lo_nibble1 * b_hi_nibble0;
                    product_lh_11_reg[ilane] <=
                        $signed({1'b0,a_lo_nibble1}) * b_hi_nibble1;
                    product_hl_00_reg[ilane] <=
                        a_hi_nibble0 * b_lo_nibble0;
                    product_hl_signed_mid_reg[ilane] <=
                        a_hi_nibble1 * $signed({1'b0,b_lo_nibble0});
                    product_hl_unsigned_mid_reg[ilane] <=
                        a_hi_nibble0 * b_lo_nibble1;
                    product_hl_11_reg[ilane] <=
                        a_hi_nibble1 * $signed({1'b0,b_lo_nibble1});
                end
            wire signed [16:0] lh_recombined =
                recombine_4x4(product_lh_00_reg[ilane],
                              product_lh_signed_mid_reg[ilane],
                              product_lh_unsigned_mid_reg[ilane],
                              product_lh_11_reg[ilane]);
            wire signed [16:0] hl_recombined =
                recombine_4x4(product_hl_00_reg[ilane],
                              product_hl_signed_mid_reg[ilane],
                              product_hl_unsigned_mid_reg[ilane],
                              product_hl_11_reg[ilane]);
            always_ff @(posedge clk) if (integer_raw_input_valid_q) begin
                product_ll_p00_reg[ilane] <= a_lo_nibble0 * b_lo_nibble0;
                product_ll_p01_reg[ilane] <= a_lo_nibble0 * b_lo_nibble1;
                product_ll_p10_reg[ilane] <= a_lo_nibble1 * b_lo_nibble0;
                product_ll_p11_reg[ilane] <= a_lo_nibble1 * b_lo_nibble1;
                product_hh_p00_reg[ilane] <= a_hi_nibble0 * b_hi_nibble0;
                product_hh_p01_reg[ilane] <=
                    $signed({1'b0,a_hi_nibble0}) * b_hi_nibble1;
                product_hh_p10_reg[ilane] <=
                    a_hi_nibble1 * $signed({1'b0,b_hi_nibble0});
                product_hh_p11_reg[ilane] <= a_hi_nibble1 * b_hi_nibble1;
            end
            always_ff @(posedge clk) if (integer_raw_valid_q) begin
                product_lh_reg[ilane] <= lh_recombined;
                product_hl_reg[ilane] <= hl_recombined;
                product_ll_pre_delay[ilane] <= recombine_unsigned8(
                    product_ll_p00_reg[ilane],product_ll_p01_reg[ilane],
                    product_ll_p10_reg[ilane],product_ll_p11_reg[ilane]);
                product_hh_pre_delay[ilane] <= recombine_signed8(
                    product_hh_p00_reg[ilane],product_hh_p01_reg[ilane],
                    product_hh_p10_reg[ilane],product_hh_p11_reg[ilane]);
            end
            wire signed [18:0] cross_sum =
                $signed({{2{product_lh_reg[ilane][16]}},product_lh_reg[ilane]}) +
                $signed({{2{product_hl_reg[ilane][16]}},product_hl_reg[ilane]});
            always_ff @(posedge clk) if (integer_partial_valid_q) begin
                product_low_delay[ilane] <= product_ll_pre_delay[ilane];
                product_cross_delay[ilane] <= cross_sum;
                product_high_delay[ilane] <= product_hh_pre_delay[ilane];
            end
            wire [31:0] low_word = {16'b0,product_low_delay[ilane]};
            wire [31:0] middle_word =
                {{13{product_cross_delay[ilane][18]}},product_cross_delay[ilane]} << 8;
            wire [31:0] high_word =
                {{16{product_high_delay[ilane][15]}},product_high_delay[ilane]} << 16;
            wire [31:0] csa_sum = low_word ^ middle_word ^ high_word;
            wire [31:0] csa_carry =
                ((low_word & middle_word) | (low_word & high_word) |
                 (middle_word & high_word)) << 1;
            wire signed [31:0] product16 = $signed(csa_sum + csa_carry);
            assign p8_pair[ilane*16 +: 16] = product8_delay2[ilane];
            assign p16_out = product16;
        end else begin : int8_only
            assign p8_pair[ilane*16 +: 16] = product8_delay2[ilane];
        end
    end
    always_ff @(posedge clk) begin
        if (integer_raw_valid_q)
            for (int i=0; i<2; i++) product8_delay[i] <=
                recombine_signed8(product8_p00_reg[i],product8_p01_reg[i],
                                  product8_p10_reg[i],product8_p11_reg[i]);
        if (integer_partial_valid_q)
            for (int i=0; i<2; i++) product8_delay2[i] <= product8_delay[i];
    end
endmodule

module t10_reference_postprocess (
    input logic clk, rst_n,
    input logic post2_valid,
    input logic [579:0] post2_exact,
    input logic [63:0] post2_integer,
    input logic post2_is_integer,
    input logic post2_nan, post2_plus_inf, post2_minus_inf,
    input logic [3:0] post2_slot,
    output logic [63:0] result,
    output logic result_valid,
    output logic [3:0] result_slot
);
    /* verilator hier_block */
    localparam int EXACT_BITS = 580;
    logic post2_in_valid;
    logic [579:0] post2_in_exact;
    logic [63:0] post2_in_integer;
    logic post2_in_is_integer;
    logic post2_in_nan, post2_in_plus_inf, post2_in_minus_inf;
    logic [3:0] post2_in_slot;
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            post2_in_valid <= 1'b0;
        end else begin
            post2_in_valid <= post2_valid;
            if (post2_valid) begin
                post2_in_exact <= post2_exact;
                post2_in_integer <= post2_integer;
                post2_in_is_integer <= post2_is_integer;
                post2_in_nan <= post2_nan;
                post2_in_plus_inf <= post2_plus_inf;
                post2_in_minus_inf <= post2_minus_inf;
                post2_in_slot <= post2_slot;
            end
        end
    end
    localparam int EXACT_LSB = -286;
    localparam logic [EXACT_BITS-1:0] MAX_FINITE_F32 =
        ({{(EXACT_BITS-24){1'b0}}, 24'hff_ffff} << 390);
    function automatic logic [9:0] leading_one(
        input logic [EXACT_BITS-1:0] magnitude);
        logic [1023:0] padded;
        logic [127:1] found;
        logic [9:0] position [1:127];
        begin
            padded = '0;
            padded[EXACT_BITS-1:0] = magnitude;
            for (int group=0; group<64; group++) begin
                found[64+group] = 1'b0;
                position[64+group] = '0;
                for (int local_bit=0; local_bit<16; local_bit++) begin
                    if (padded[group*16+local_bit]) begin
                        found[64+group] = 1'b1;
                        position[64+group] = 10'(group*16+local_bit);
                    end
                end
            end
            for (int node=63; node>=1; node--) begin
                found[node] = found[node*2] | found[node*2+1];
                position[node] = found[node*2+1] ?
                                 position[node*2+1] : position[node*2];
            end
            leading_one = found[1] ? position[1] : 10'h3ff;
        end
    endfunction

    function automatic logic [31:0] encode_f32(
        input logic [EXACT_BITS-1:0] magnitude,
        input logic [9:0] leading,
        input logic [9:0] shift_amount,
        input logic overflow,
        input logic negative,
        input logic seen_nan, seen_plus_inf, seen_minus_inf);
        logic [23:0] significand;
        logic [22:0] subnormal;
        integer exponent;
        begin
            encode_f32 = '0;
            if (seen_nan || (seen_plus_inf && seen_minus_inf))
                encode_f32 = 32'h7fc0_0000;
            else if (seen_plus_inf || seen_minus_inf)
                encode_f32 = {seen_minus_inf,8'hff,23'b0};
            else begin
                if (leading != 10'h3ff) begin
                    exponent = int'(leading) + EXACT_LSB;
                    if (overflow)
                        encode_f32 = {negative,8'hff,23'b0};
                    else if (exponent>=-126) begin
                        significand = 24'(magnitude >> shift_amount);
                        encode_f32 = {negative,8'(exponent+127),significand[22:0]};
                    end else begin
                        subnormal = 23'(magnitude >> 137);
                        encode_f32 = {negative,8'd0,subnormal};
                    end
                end
            end
        end
    endfunction

    logic post3_valid, post4_valid, post5_valid;
    logic [63:0] post3_integer, post4_integer, post5_integer;
    logic [EXACT_BITS-1:0] post3_abs_word, post4_magnitude, post5_magnitude;
    logic post5_overflow;
    (* fsm_encoding = "none" *) logic [9:0] post5_leading;
    (* fsm_encoding = "none" *) logic [9:0] post5_shift;
    logic post3_negative, post4_negative, post5_negative;
    logic post3_is_integer, post4_is_integer, post5_is_integer;
    logic post3_nan, post3_plus_inf, post3_minus_inf;
    logic post4_nan, post4_plus_inf, post4_minus_inf;
    logic post5_nan, post5_plus_inf, post5_minus_inf;
    logic [3:0] post3_slot, post4_slot, post5_slot;
    localparam int ABS_CHUNKS = (EXACT_BITS+31)/32;
    wire [ABS_CHUNKS-1:0] abs_zero_prefix [0:5];
    wire [ABS_CHUNKS-1:0] post2_abs_carry_comb;
    wire [EXACT_BITS-1:0] abs_completed;
    wire [ABS_CHUNKS-1:0] post2_abs_zero_comb;
    logic [ABS_CHUNKS-1:0] post3_abs_carry;
    for (genvar chunk=0; chunk<ABS_CHUNKS; chunk++) begin : abs_chunk
        localparam int LO = chunk*32;
        localparam int WIDTH = (EXACT_BITS-LO < 32) ? EXACT_BITS-LO : 32;
        wire carry_in;
        assign post2_abs_zero_comb[chunk] = ~|post2_in_exact[LO +: WIDTH];
        assign abs_zero_prefix[0][chunk] = post2_abs_zero_comb[chunk];
        for (genvar level=0; level<5; level++) begin : prefix_level
            if (chunk >= (1 << level))
                assign abs_zero_prefix[level+1][chunk] =
                    abs_zero_prefix[level][chunk] &
                    abs_zero_prefix[level][chunk-(1 << level)];
            else
                assign abs_zero_prefix[level+1][chunk] =
                    abs_zero_prefix[level][chunk];
        end
        if (chunk == 0) assign carry_in = 1'b1;
        else assign carry_in = abs_zero_prefix[5][chunk-1];
        assign post2_abs_carry_comb[chunk] = carry_in;
        assign abs_completed[LO +: WIDTH] =
            post3_abs_word[LO +: WIDTH] +
            WIDTH'(post3_negative && post3_abs_carry[chunk]);
    end
    // Result payload and slot are consumed only while result_valid is high.
    // Their wide registers do not need an asynchronous reset.
    always_ff @(posedge clk) begin
        if (post5_valid) begin
            result <= post5_is_integer ? post5_integer :
                {32'b0,encode_f32(post5_magnitude,post5_leading,post5_shift,
                                  post5_overflow,
                                  post5_negative,post5_nan,
                                  post5_plus_inf,post5_minus_inf)};
            result_slot <= post5_slot;
        end
    end
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            result_valid <= 1'b0;
            post3_valid <= 1'b0;
            post4_valid <= 1'b0;
            post5_valid <= 1'b0;
        end else begin
            result_valid <= post5_valid;
            post5_valid <= post4_valid;
            if (post4_valid) begin
                post5_leading <= leading_one(post4_magnitude);
                post5_shift <= leading_one(post4_magnitude) - 10'd23;
                post5_magnitude <= post4_magnitude;
                post5_overflow <= post4_magnitude > MAX_FINITE_F32;
                post5_negative <= post4_negative;
                post5_integer <= post4_integer;
                post5_is_integer <= post4_is_integer;
                post5_nan <= post4_nan;
                post5_plus_inf <= post4_plus_inf;
                post5_minus_inf <= post4_minus_inf;
                post5_slot <= post4_slot;
            end
            post4_valid <= post3_valid;
            if (post3_valid) begin
                post4_magnitude <= abs_completed;
                post4_negative <= post3_negative;
                post4_integer <= post3_integer;
                post4_is_integer <= post3_is_integer;
                post4_nan <= post3_nan;
                post4_plus_inf <= post3_plus_inf;
                post4_minus_inf <= post3_minus_inf;
                post4_slot <= post3_slot;
            end
            post3_valid <= post2_in_valid;
            if (post2_in_valid) begin
                post3_negative <= post2_in_exact[EXACT_BITS-1];
                post3_abs_word <= post2_in_exact[EXACT_BITS-1] ?
                                  ~$unsigned(post2_in_exact) : $unsigned(post2_in_exact);
                post3_abs_carry <= post2_abs_carry_comb;
                post3_integer <= post2_in_integer;
                post3_is_integer <= post2_in_is_integer;
                post3_nan <= post2_in_nan;
                post3_plus_inf <= post2_in_plus_inf;
                post3_minus_inf <= post2_in_minus_inf;
                post3_slot <= post2_in_slot;
            end
        end
    end
endmodule

(* keep_hierarchy = "yes" *) module t10_reference_pe (
    input  logic clk, rst_n,
    input  logic [63:0] a_in, b_in,
    input  logic [27:0] at_in, bt_in,
    output logic [63:0] a_out, b_out,
    output logic [27:0] at_out, bt_out,
    output logic [63:0] result,
    output logic result_valid,
    output logic [3:0] result_slot
);
    /* verilator hier_block */
    localparam int EXACT_BITS = 580;
    logic [63:0] a_work, b_work;
    logic [27:0] at_work, bt_work;
    logic [26:0] at_work_payload, bt_work_payload;
    logic at_work_valid, bt_work_valid;
    logic float_mode16_q, float_mode4_q;
    assign at_work = {at_work_valid, at_work_payload};
    assign bt_work = {bt_work_valid, bt_work_payload};
    always_ff @(posedge clk) begin
        a_work <= a_in;
        b_work <= b_in;
    end
    // Token payload is ignored whenever its valid bit is clear. Reset only
    // the valid bit to avoid resettable flops on the wide wavefront buses.
    always_ff @(posedge clk) begin
        at_work_payload <= at_in[26:0];
        bt_work_payload <= bt_in[26:0];
        float_mode16_q <= at_in[24:21] == 4'd2 || at_in[24:21] == 4'd3;
        float_mode4_q <= at_in[24:21] == 4'd6 || at_in[24:21] == 4'd9;
    end
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            at_work_valid <= 1'b0;
            bt_work_valid <= 1'b0;
        end else begin
            at_work_valid <= at_in[27];
            bt_work_valid <= bt_in[27];
        end
    end

    function automatic logic [2*EXACT_BITS-1:0] csa3(
        input logic [EXACT_BITS-1:0] x, y, z);
        logic [EXACT_BITS-1:0] sum_word, carry_word;
        begin
            sum_word = x ^ y ^ z;
            carry_word = ((x & y) | (x & z) | (y & z)) << 1;
            csa3 = {carry_word,sum_word};
        end
    endfunction

    // 64 signed INT16 products fit in 38 signed bits, including the
    // +2^36 corner from (-32768)*(-32768) repeated 64 times.
    logic signed [37:0] integer_accum;
    logic signed [37:0] integer_next;
    logic integer_pre_valid, integer_pre_first, integer_pre_last;
    logic [3:0] integer_pre_slot;
    logic integer_level2_valid, integer_level2_first, integer_level2_last;
    logic [3:0] integer_level2_slot;
    logic integer_mul_valid, integer_mul_first, integer_mul_last;
    logic [3:0] integer_mul_slot;
    logic integer_pending_valid, integer_pending_first, integer_pending_last;
    logic integer_done_valid;
    logic [3:0] integer_done_slot;
    logic [3:0] integer_pending_slot;
    logic signed [34:0] integer_pending_sum;
    logic [EXACT_BITS-1:0] csa_sum_accum, csa_carry_accum;
    logic [EXACT_BITS-1:0] csa_sum_next, csa_carry_next;
    logic float_lane_valid, float_lane_first, float_lane_last;
    logic [3:0] float_lane_slot;
    logic float_input_valid, float_input_first, float_input_last;
    logic [3:0] float_input_slot;
    logic float_product_valid, float_product_first, float_product_last;
    logic [3:0] float_product_slot;
    logic float_term_valid, float_term_first, float_term_last;
    logic [3:0] float_term_slot;
    logic float_exact1_valid, float_exact1_first, float_exact1_last;
    logic [3:0] float_exact1_slot;
    logic float_exact2_valid, float_exact2_first, float_exact2_last;
    logic [3:0] float_exact2_slot;
    logic float_reduce_valid, float_reduce_first, float_reduce_last;
    logic [3:0] float_reduce_slot;
    logic float_macro_pipe_valid, float_macro_pipe_first, float_macro_pipe_last;
    logic [3:0] float_macro_pipe_slot;
    logic float_macro_sample_valid, float_macro_sample_first;
    logic float_macro_sample_last;
    logic [3:0] float_macro_sample_slot;
    logic float_reduce_pipe_valid, float_reduce_pipe_first, float_reduce_pipe_last;
    logic [3:0] float_reduce_pipe_slot;
    logic float_reduce_pipe2_valid, float_reduce_pipe2_first, float_reduce_pipe2_last;
    logic [3:0] float_reduce_pipe2_slot;
    logic float_pending_valid, float_pending_first, float_pending_last;
    logic [3:0] float_pending_slot;
    logic float_pending_nan, float_pending_plus_inf, float_pending_minus_inf;
    logic [EXACT_BITS-1:0] float_pending_words [0:1];
    logic [EXACT_BITS-1:0] quad_sum [0:3];
    logic [EXACT_BITS-1:0] quad_carry [0:3];
    logic [2:0] quad_negative_count [0:3];
    logic [3:0] quad_nan, quad_plus_inf, quad_minus_inf;
    logic [EXACT_BITS-1:0] quad_sum_macro_q [0:3];
    logic [3:0] quad_nan_macro_q, quad_plus_inf_macro_q;
    logic [3:0] quad_minus_inf_macro_q;
    wire [15:0] a_lane_raw [0:15], b_lane_raw [0:15];
    wire lane_active [0:15];
    logic [EXACT_BITS-1:0] level0 [0:8];
    logic [EXACT_BITS-1:0] level1 [0:5];
    logic [EXACT_BITS-1:0] level1_q [0:5];
    logic [3:0] quad_nan_q, quad_plus_inf_q, quad_minus_inf_q;
    logic [EXACT_BITS-1:0] level2 [0:3];
    logic [EXACT_BITS-1:0] level2_q [0:3];
    logic [3:0] quad_nan_q2, quad_plus_inf_q2, quad_minus_inf_q2;
    logic [EXACT_BITS-1:0] level3 [0:2];
    logic [EXACT_BITS-1:0] level4 [0:1];
    logic [EXACT_BITS-1:0] pending_level0 [0:3];
    logic [EXACT_BITS-1:0] pending_level1 [0:2];
    logic [3:0] negative_pair0, negative_pair1;
    logic [3:0] negative_pair0_macro_q, negative_pair1_macro_q;
    logic [3:0] negative_pair0_q, negative_pair1_q;
    logic [4:0] negative_count;
    logic post1_valid, post1a_valid, post1b_valid, post2_valid;
    logic [EXACT_BITS-1:0] post1_sum, post1_carry;
    t10_reference_cpa_postprocess cpa_postprocess (
        .clk, .valid_data_in(post1_valid),
        .valid_in(1'b1), .sum_in(post1_sum),
        .carry_word_in(post1_carry),
        .rst_n, .post2_valid, .post2_integer,
        .post2_is_integer,
        .post2_nan, .post2_plus_inf, .post2_minus_inf,
        .post2_slot,
        .result, .result_valid, .result_slot
    );
    logic [63:0] post1_integer, post1a_integer, post1b_integer, post2_integer;
    logic post1_is_integer, post1a_is_integer, post1b_is_integer, post2_is_integer;
    logic post1_nan, post1_plus_inf, post1_minus_inf;
    logic post1a_nan, post1a_plus_inf, post1a_minus_inf;
    logic post1b_nan, post1b_plus_inf, post1b_minus_inf;
    logic post2_nan, post2_plus_inf, post2_minus_inf;
    logic [3:0] post1_slot, post1a_slot, post1b_slot, post2_slot;
    logic nan_accum, plus_inf_accum, minus_inf_accum;
    logic nan_next, plus_inf_next, minus_inf_next;
    logic signed [34:0] integer_product [0:7];
    logic signed [34:0] integer_product_reg [0:7];
    logic integer_raw_input_valid, integer_raw_valid;
    logic integer_mode_int8_q;
    logic integer_raw_first, integer_raw_last;
    logic [3:0] integer_raw_slot, integer_raw_mode;
    logic integer_partial_valid, integer_partial_first, integer_partial_last;
    logic [3:0] integer_partial_slot, integer_partial_mode;
    logic integer_retime_valid, integer_retime_first, integer_retime_last;
    logic [3:0] integer_retime_slot, integer_retime_mode;
    logic integer_cross_valid, integer_cross_first, integer_cross_last;
    logic [3:0] integer_cross_slot, integer_cross_mode;
    logic signed [34:0] integer_level1 [0:3];
    logic signed [34:0] integer_pre_sum [0:3];
    logic signed [34:0] integer_level2 [0:1];
    logic signed [34:0] integer_level2_q [0:1];
    logic signed [34:0] integer_lane_sum;
    // Decode the integer mode at the ingress register boundary. The macro
    // inputs and these controls then arrive from registers on the same beat.
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n)
            integer_raw_input_valid <= 1'b0;
        else
            integer_raw_input_valid <= at_in[27] && bt_in[27] &&
                                       at_in[24:21] <= 4'd1;
    end
    always_ff @(posedge clk)
        integer_mode_int8_q <= at_in[24:21] == 4'd0;
    wire [31:0] int8_group_product [0:3];
    wire signed [31:0] int16_group_product [0:3];
    for (genvar group=0; group<4; group++) begin : int_group
        t10_reference_int_group product_group (
            .clk,
            .a_work(a_work[group*16 +: 16]),
            .b_work(b_work[group*16 +: 16]),
            .mode_int8(integer_mode_int8_q),
            .integer_raw_input_valid,
            .integer_raw_valid,
            .integer_partial_valid,
            .p8_pair(int8_group_product[group]),
            .p16_out(int16_group_product[group])
        );
    end
    for (genvar ilane=0; ilane<8; ilane++) begin : int_product_select
        wire signed [15:0] p8 =
            $signed(int8_group_product[ilane/2][(ilane%2)*16 +: 16]);
        if (ilane < 4) begin : int16_lane
            assign integer_product[ilane] = integer_cross_mode == 4'd0 ?
                {{19{p8[15]}},p8} :
                {{3{int16_group_product[ilane][31]}},int16_group_product[ilane]};
        end else begin : int8_only
            assign integer_product[ilane] = integer_cross_mode == 4'd0 ?
                {{19{p8[15]}},p8} : 35'sd0;
        end
    end
    for (genvar pair=0; pair<4; pair++)
        assign integer_level1[pair] = integer_product_reg[2*pair] +
                                       integer_product_reg[2*pair+1];
    for (genvar pair=0; pair<2; pair++)
        assign integer_level2[pair] = integer_pre_sum[2*pair] +
                                       integer_pre_sum[2*pair+1];
    assign integer_lane_sum = integer_level2_q[0] + integer_level2_q[1];
    logic [7:0] a_scale_work, b_scale_work;
    always_ff @(posedge clk) begin
        a_scale_work <= at_in[16] ? at_in[15:8] : at_in[7:0];
        b_scale_work <= bt_in[16] ? bt_in[15:8] : bt_in[7:0];
    end
    // The PE ingress registers already hold operands and metadata for this
    // beat. Select lanes locally during the next cycle, before each quad's
    // first register. This keeps the quad sampling edge unchanged and removes
    // the wide format mux from the inter-PE token input setup path.
    for (genvar lane=0; lane<16; lane++) begin : float_lane_input
        assign lane_active[lane] = at_work[24:21]>=4'd2 &&
            (float_mode16_q ? lane<4 :
             (float_mode4_q ? 1'b1 : lane<8));
        assign a_lane_raw[lane] =
            float_mode16_q ?
            a_work[(lane%4)*16 +: 16] :
            (float_mode4_q ?
             {12'b0,a_work[lane*4 +: 4]} :
             {8'b0,a_work[(lane%8)*8 +: 8]});
        assign b_lane_raw[lane] =
            float_mode16_q ?
            b_work[(lane%4)*16 +: 16] :
            (float_mode4_q ?
             {12'b0,b_work[lane*4 +: 4]} :
             {8'b0,b_work[(lane%8)*8 +: 8]});
    end
    for (genvar group=0; group<4; group++) begin : float_quad
        wire [63:0] quad_a_raw, quad_b_raw;
        wire [3:0] quad_active;
        for (genvar lane=0; lane<4; lane++) begin : connect_lane
            assign quad_a_raw[lane*16 +: 16] = a_lane_raw[group*4+lane];
            assign quad_b_raw[lane*16 +: 16] = b_lane_raw[group*4+lane];
            assign quad_active[lane] = lane_active[group*4+lane];
        end
        if (group == 0) begin : class0
            t10_reference_fp_quad_class0_exact fp_quad (
                .clk, .a_raw(quad_a_raw), .b_raw(quad_b_raw),
                .mode(at_work[24:21]), .lane_active(quad_active),
                .a_scale(a_scale_work), .b_scale(b_scale_work),
                .exact_word(quad_sum[group]),
                .negative_count(quad_negative_count[group]),
                .nan_value(quad_nan[group]), .plus_inf(quad_plus_inf[group]),
                .minus_inf(quad_minus_inf[group])
            );
        end else if (group == 1) begin : class1
            t10_reference_fp_quad_class1_exact fp_quad (
                .clk, .a_raw(quad_a_raw), .b_raw(quad_b_raw),
                .mode(at_work[24:21]), .lane_active(quad_active),
                .a_scale(a_scale_work), .b_scale(b_scale_work),
                .exact_word(quad_sum[group]),
                .negative_count(quad_negative_count[group]),
                .nan_value(quad_nan[group]), .plus_inf(quad_plus_inf[group]),
                .minus_inf(quad_minus_inf[group])
            );
        end else begin : class2
            t10_reference_fp_quad_class2_exact fp_quad (
                .clk, .a_raw(quad_a_raw), .b_raw(quad_b_raw),
                .mode(at_work[24:21]), .lane_active(quad_active),
                .a_scale(a_scale_work), .b_scale(b_scale_work),
                .exact_word(quad_sum[group]),
                .negative_count(quad_negative_count[group]),
                .nan_value(quad_nan[group]), .plus_inf(quad_plus_inf[group]),
                .minus_inf(quad_minus_inf[group])
            );
        end
        assign quad_carry[group] = '0;
    end
    always_comb begin
        integer_next = (integer_pending_first ? 38'sd0 : integer_accum) +
                       {{3{integer_pending_sum[34]}},integer_pending_sum};
        negative_pair0 = 4'(quad_negative_count[0]) +
                         4'(quad_negative_count[1]);
        negative_pair1 = 4'(quad_negative_count[2]) +
                         4'(quad_negative_count[3]);
        negative_count = 5'(negative_pair0_q) + 5'(negative_pair1_q);
        nan_next = (float_pending_first ? 1'b0 : nan_accum) |
                   float_pending_nan;
        plus_inf_next = (float_pending_first ? 1'b0 : plus_inf_accum) |
                        float_pending_plus_inf;
        minus_inf_next = (float_pending_first ? 1'b0 : minus_inf_accum) |
                         float_pending_minus_inf;
    end
    always_comb begin
        for (int group=0; group<4; group++) begin
            level0[2*group] = quad_sum_macro_q[group];
            level0[2*group+1] = quad_carry[group];
        end
        // The sign-correction count is registered beside the first reduction
        // stage, then injected into the second stage. This cuts the macro
        // output -> count adders -> CSA -> level1 register timing path.
        level0[8] = '0;
        for (int i=0; i<3; i++)
            {level1[2*i+1],level1[2*i]} =
                csa3(level0[3*i],level0[3*i+1],level0[3*i+2]);
        {level2[1],level2[0]} =
            csa3(level1_q[0],level1_q[1],level1_q[2]);
        {level2[3],level2[2]} =
            csa3(level1_q[3],level1_q[4],
                 {{(EXACT_BITS-5){1'b0}},negative_count});
        {level3[1],level3[0]} = csa3(level2_q[0],level2_q[1],level2_q[2]);
        level3[2] = level2_q[3];
        {level4[1],level4[0]} = csa3(level3[0],level3[1],level3[2]);
        pending_level0[0] = float_pending_words[0];
        pending_level0[1] = float_pending_words[1];
        // The final beat clears feedback after its result is captured.
        pending_level0[2] = csa_sum_accum;
        pending_level0[3] = csa_carry_accum;
        {pending_level1[1],pending_level1[0]} =
            csa3(pending_level0[0],pending_level0[1],pending_level0[2]);
        pending_level1[2] = pending_level0[3];
        {csa_carry_next,csa_sum_next} =
            csa3(pending_level1[0],pending_level1[1],pending_level1[2]);
    end
    always_ff @(posedge clk) begin
        if (float_macro_pipe_valid) begin
            // Sample the routed hard-macro outputs before the first CSA.
            // This adds one registered reduction stage while preserving the
            // one-beat-per-cycle throughput of the valid pipeline.
            for (int i=0; i<4; i++) quad_sum_macro_q[i] <= quad_sum[i];
            negative_pair0_macro_q <= negative_pair0;
            negative_pair1_macro_q <= negative_pair1;
            quad_nan_macro_q <= quad_nan;
            quad_plus_inf_macro_q <= quad_plus_inf;
            quad_minus_inf_macro_q <= quad_minus_inf;
        end
        if (integer_cross_valid)
            for (int i=0; i<8; i++) integer_product_reg[i] <= integer_product[i];
        if (integer_mul_valid)
            for (int i=0; i<4; i++) integer_pre_sum[i] <= integer_level1[i];
        if (integer_pre_valid)
            for (int i=0; i<2; i++) integer_level2_q[i] <= integer_level2[i];
        if (float_macro_sample_valid) begin
            for (int i=0; i<6; i++) level1_q[i] <= level1[i];
            // Split the four-quad sign-count reduction across the same two
            // stages as level1 -> level2 without changing beat latency.
            negative_pair0_q <= negative_pair0_macro_q;
            negative_pair1_q <= negative_pair1_macro_q;
            quad_nan_q <= quad_nan_macro_q;
            quad_plus_inf_q <= quad_plus_inf_macro_q;
            quad_minus_inf_q <= quad_minus_inf_macro_q;
        end
        // level2_q is a true pipeline boundary.  Sampling it every cycle
        // avoids turning float_reduce_pipe_valid into a 1392-bit, routed
        // write-enable cone; validity still controls which sampled beat can
        // update architectural state downstream.
        for (int i=0; i<4; i++) level2_q[i] <= level2[i];
        if (float_reduce_pipe_valid) begin
            quad_nan_q2 <= quad_nan_q;
            quad_plus_inf_q2 <= quad_plus_inf_q;
            quad_minus_inf_q2 <= quad_minus_inf_q;
        end
        if (float_reduce_pipe2_valid)
            for (int i=0; i<2; i++) float_pending_words[i] <= level4[i];
    end
    logic [26:0] at_out_payload, bt_out_payload;
    logic at_out_valid, bt_out_valid;
    logic at_out_valid_n, bt_out_valid_n;
    assign at_out_valid = ~at_out_valid_n;
    assign bt_out_valid = ~bt_out_valid_n;
    assign at_out = {at_out_valid, at_out_payload};
    assign bt_out = {bt_out_valid, bt_out_payload};
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            at_out_payload <= '0;
            bt_out_payload <= '0;
        end else begin
            at_out_payload <= at_in[26:0];
            bt_out_payload <= bt_in[26:0];
        end
    end
    // Separate both token output-valid registers from their internal
    // control copies and drive each boundary directly from the FF QN pin.
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            at_out_valid_n <= 1'b1;
            bt_out_valid_n <= 1'b1;
        end else begin
            at_out_valid_n <= ~at_in[27];
            bt_out_valid_n <= ~bt_in[27];
        end
    end
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            integer_accum <= '0;
            integer_pre_valid <= 1'b0;
            integer_level2_valid <= 1'b0;
            integer_level2_first <= 1'b0;
            integer_level2_last <= 1'b0;
            integer_level2_slot <= '0;
            integer_pre_first <= 1'b0;
            integer_pre_last <= 1'b0;
            integer_pre_slot <= '0;
            integer_mul_valid <= 1'b0;
            integer_raw_valid <= 1'b0;
            integer_partial_valid <= 1'b0;
            integer_partial_first <= 1'b0;
            integer_partial_last <= 1'b0;
            integer_partial_slot <= '0;
            integer_partial_mode <= '0;
            integer_raw_first <= 1'b0;
            integer_raw_last <= 1'b0;
            integer_raw_slot <= '0;
            integer_raw_mode <= '0;
            integer_retime_valid <= 1'b0;
            integer_retime_first <= 1'b0;
            integer_retime_last <= 1'b0;
            integer_retime_slot <= '0;
            integer_retime_mode <= '0;
            integer_cross_valid <= 1'b0;
            integer_cross_first <= 1'b0;
            integer_cross_last <= 1'b0;
            integer_cross_slot <= '0;
            integer_cross_mode <= '0;
            integer_mul_first <= 1'b0;
            integer_mul_last <= 1'b0;
            integer_mul_slot <= '0;
            integer_pending_valid <= 1'b0;
            integer_done_valid <= 1'b0;
            integer_done_slot <= '0;
            integer_pending_first <= 1'b0;
            integer_pending_last <= 1'b0;
            integer_pending_slot <= '0;
            integer_pending_sum <= '0;
            float_exact1_valid <= 1'b0;
            float_exact2_valid <= 1'b0;
            float_exact1_first <= 1'b0;
            float_exact1_last <= 1'b0;
            float_exact1_slot <= '0;
            float_exact2_first <= 1'b0;
            float_exact2_last <= 1'b0;
            float_exact2_slot <= '0;
            float_reduce_valid <= 1'b0;
            float_macro_pipe_valid <= 1'b0;
            float_macro_pipe_first <= 1'b0;
            float_macro_pipe_last <= 1'b0;
            float_macro_pipe_slot <= '0;
            float_macro_sample_valid <= 1'b0;
            float_macro_sample_first <= 1'b0;
            float_macro_sample_last <= 1'b0;
            float_macro_sample_slot <= '0;
            float_reduce_pipe_valid <= 1'b0;
            float_reduce_pipe_first <= 1'b0;
            float_reduce_pipe_last <= 1'b0;
            float_reduce_pipe_slot <= '0;
            float_reduce_pipe2_valid <= 1'b0;
            float_reduce_pipe2_first <= 1'b0;
            float_reduce_pipe2_last <= 1'b0;
            float_reduce_pipe2_slot <= '0;
            float_lane_valid <= 1'b0;
            float_lane_first <= 1'b0;
            float_lane_last <= 1'b0;
            float_lane_slot <= '0;
            float_input_valid <= 1'b0;
            float_input_first <= 1'b0;
            float_input_last <= 1'b0;
            float_input_slot <= '0;
            float_product_valid <= 1'b0;
            float_term_valid <= 1'b0;
            float_product_first <= 1'b0;
            float_product_last <= 1'b0;
            float_product_slot <= '0;
            float_reduce_first <= 1'b0;
            float_reduce_last <= 1'b0;
            float_reduce_slot <= '0;
            float_pending_valid <= 1'b0;
            float_pending_first <= 1'b0;
            float_pending_last <= 1'b0;
            float_pending_slot <= '0;
            float_pending_nan <= 1'b0;
            float_pending_plus_inf <= 1'b0;
            float_pending_minus_inf <= 1'b0;
            csa_sum_accum <= '0;
            csa_carry_accum <= '0;
            nan_accum <= 1'b0;
            plus_inf_accum <= 1'b0;
            minus_inf_accum <= 1'b0;
            post1_valid <= 1'b0;
            post1a_valid <= 1'b0;
            post1b_valid <= 1'b0;
            post2_valid <= 1'b0;
        end else begin
            post2_valid <= post1b_valid;
            integer_done_valid <= 1'b0;
            if (post1b_valid) begin
                post2_integer <= post1b_integer;
                post2_is_integer <= post1b_is_integer;
                post2_nan <= post1b_nan;
                post2_plus_inf <= post1b_plus_inf;
                post2_minus_inf <= post1b_minus_inf;
                post2_slot <= post1b_slot;
            end
            post1b_valid <= post1a_valid;
            if (post1a_valid) begin
                post1b_integer <= post1a_integer;
                post1b_is_integer <= post1a_is_integer;
                post1b_nan <= post1a_nan;
                post1b_plus_inf <= post1a_plus_inf;
                post1b_minus_inf <= post1a_minus_inf;
                post1b_slot <= post1a_slot;
            end
            post1a_valid <= post1_valid;
            if (post1_valid) begin
                post1a_integer <= post1_integer;
                post1a_is_integer <= post1_is_integer;
                post1a_nan <= post1_nan;
                post1a_plus_inf <= post1_plus_inf;
                post1a_minus_inf <= post1_minus_inf;
                post1a_slot <= post1_slot;
            end
            post1_valid <= 1'b0;
            integer_raw_valid <= integer_raw_input_valid;
            integer_partial_valid <= integer_raw_valid;
            integer_retime_valid <= integer_partial_valid;
            integer_cross_valid <= integer_retime_valid;
            integer_mul_valid <= integer_cross_valid;
            integer_pre_valid <= integer_mul_valid;
            float_lane_valid <= at_work[27] && bt_work[27] &&
                                at_work[24:21] > 4'd1;
            if (at_work[27] && bt_work[27] && at_work[24:21] > 4'd1) begin
                float_lane_first <= at_work[26];
                float_lane_last <= at_work[25];
                float_lane_slot <= at_work[20:17];
            end
            float_input_valid <= float_lane_valid;
            if (float_lane_valid) begin
                float_input_first <= float_lane_first;
                float_input_last <= float_lane_last;
                float_input_slot <= float_lane_slot;
            end
            float_product_valid <= float_input_valid;
            if (float_input_valid) begin
                float_product_first <= float_input_first;
                float_product_last <= float_input_last;
                float_product_slot <= float_input_slot;
            end
            float_term_valid <= float_product_valid;
            if (float_product_valid) begin
                float_term_first <= float_product_first;
                float_term_last <= float_product_last;
                float_term_slot <= float_product_slot;
            end
            float_exact1_valid <= float_term_valid;
            if (float_term_valid) begin
                float_exact1_first <= float_term_first;
                float_exact1_last <= float_term_last;
                float_exact1_slot <= float_term_slot;
            end
            float_exact2_valid <= float_exact1_valid;
            if (float_exact1_valid) begin
                float_exact2_first <= float_exact1_first;
                float_exact2_last <= float_exact1_last;
                float_exact2_slot <= float_exact1_slot;
            end
            float_reduce_valid <= float_exact2_valid;
            if (float_exact2_valid) begin
                float_reduce_first <= float_exact2_first;
                float_reduce_last <= float_exact2_last;
                float_reduce_slot <= float_exact2_slot;
            end
            float_macro_pipe_valid <= float_reduce_valid;
            if (float_reduce_valid) begin
                float_macro_pipe_first <= float_reduce_first;
                float_macro_pipe_last <= float_reduce_last;
                float_macro_pipe_slot <= float_reduce_slot;
            end
            float_macro_sample_valid <= float_macro_pipe_valid;
            if (float_macro_pipe_valid) begin
                float_macro_sample_first <= float_macro_pipe_first;
                float_macro_sample_last <= float_macro_pipe_last;
                float_macro_sample_slot <= float_macro_pipe_slot;
            end
            float_reduce_pipe_valid <= float_macro_sample_valid;
            if (float_macro_sample_valid) begin
                float_reduce_pipe_first <= float_macro_sample_first;
                float_reduce_pipe_last <= float_macro_sample_last;
                float_reduce_pipe_slot <= float_macro_sample_slot;
            end
            float_reduce_pipe2_valid <= float_reduce_pipe_valid;
            if (float_reduce_pipe_valid) begin
                float_reduce_pipe2_first <= float_reduce_pipe_first;
                float_reduce_pipe2_last <= float_reduce_pipe_last;
                float_reduce_pipe2_slot <= float_reduce_pipe_slot;
            end
            float_pending_valid <= float_reduce_pipe2_valid;
            if (float_reduce_pipe2_valid) begin
                float_pending_first <= float_reduce_pipe2_first;
                float_pending_last <= float_reduce_pipe2_last;
                float_pending_slot <= float_reduce_pipe2_slot;
                float_pending_nan <= |quad_nan_q2;
                float_pending_plus_inf <= |quad_plus_inf_q2;
                float_pending_minus_inf <= |quad_minus_inf_q2;
            end
            if (integer_raw_input_valid) begin
                integer_raw_first <= at_work[26];
                integer_raw_last <= at_work[25];
                integer_raw_slot <= at_work[20:17];
                integer_raw_mode <= at_work[24:21];
            end
            if (integer_raw_valid) begin
                integer_partial_first <= integer_raw_first;
                integer_partial_last <= integer_raw_last;
                integer_partial_slot <= integer_raw_slot;
                integer_partial_mode <= integer_raw_mode;
            end
            if (integer_partial_valid) begin
                integer_retime_first <= integer_partial_first;
                integer_retime_last <= integer_partial_last;
                integer_retime_slot <= integer_partial_slot;
                integer_retime_mode <= integer_partial_mode;
            end
            if (integer_retime_valid) begin
                integer_cross_first <= integer_retime_first;
                integer_cross_last <= integer_retime_last;
                integer_cross_slot <= integer_retime_slot;
                integer_cross_mode <= integer_retime_mode;
            end
            if (integer_cross_valid) begin
                integer_mul_first <= integer_cross_first;
                integer_mul_last <= integer_cross_last;
                integer_mul_slot <= integer_cross_slot;
            end
            if (integer_mul_valid) begin
                integer_pre_first <= integer_mul_first;
                integer_pre_last <= integer_mul_last;
                integer_pre_slot <= integer_mul_slot;
            end
            integer_level2_valid <= integer_pre_valid;
            if (integer_pre_valid) begin
                integer_level2_first <= integer_pre_first;
                integer_level2_last <= integer_pre_last;
                integer_level2_slot <= integer_pre_slot;
            end
            integer_pending_valid <= integer_level2_valid;
            if (integer_level2_valid) begin
                integer_pending_first <= integer_level2_first;
                integer_pending_last <= integer_level2_last;
                integer_pending_slot <= integer_level2_slot;
                integer_pending_sum <= integer_lane_sum;
            end
            if (integer_pending_valid) begin
                integer_accum <= integer_next;
                if (integer_pending_last) begin
                    integer_done_valid <= 1'b1;
                    integer_done_slot <= integer_pending_slot;
                end
            end
            if (integer_done_valid) begin
                post1_sum <= '0;
                post1_carry <= '0;
                post1_integer <= {{26{integer_accum[37]}},integer_accum};
                post1_is_integer <= 1'b1;
                post1_nan <= 1'b0;
                post1_plus_inf <= 1'b0;
                post1_minus_inf <= 1'b0;
                post1_slot <= integer_done_slot;
                post1_valid <= 1'b1;
            end
            if (float_pending_valid) begin
                csa_sum_accum <= float_pending_last ? '0 : csa_sum_next;
                csa_carry_accum <= float_pending_last ? '0 : csa_carry_next;
                nan_accum <= nan_next;
                plus_inf_accum <= plus_inf_next;
                minus_inf_accum <= minus_inf_next;
                // Capture every beat without putting last on the wide D path.
                post1_sum <= csa_sum_next;
                post1_carry <= csa_carry_next;
                if (float_pending_last) begin
                    post1_integer <= '0;
                    post1_is_integer <= 1'b0;
                    post1_nan <= nan_next;
                    post1_plus_inf <= plus_inf_next;
                    post1_minus_inf <= minus_inf_next;
                    post1_slot <= float_pending_slot;
                    post1_valid <= 1'b1;
                end
            end
        end
    end
    // Store the complemented forwarding data so the resettable ASAP7 FF's
    // QN pin can directly drive the output boundary without an inverter.
    logic [63:0] a_out_n, b_out_n;
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            a_out_n <= '1;
            b_out_n <= '1;
        end else begin
            a_out_n <= ~a_in;
            b_out_n <= ~b_in;
        end
    end
    assign a_out = ~a_out_n;
    assign b_out = ~b_out_n;
endmodule

(* keep_hierarchy = "yes" *) module t10_reference_mode_reg (
    input logic clk, rst_n,
    input logic [3:0] mode_in,
    output logic [3:0] mode_out
);
    // The surrounding valid pipeline is reset; the mode payload is ignored
    // while invalid and can use ordinary data flops.
    always_ff @(posedge clk) mode_out <= mode_in;
endmodule


// Isolate the 580-bit carry-propagate pipeline as a physical child macro.
// Its interface and register boundary match the original PE pipeline.
module t10_reference_cpa (
    input logic clk,
    input logic valid_data_in,
    input logic valid_in,
    input logic [579:0] sum_in, carry_word_in,
    output logic [579:0] cpa_result
);
    /* verilator hier_block */
    localparam int EXACT_BITS = 580;
    localparam int CPA_CHUNK_BITS = 20;
    localparam int CPA_CHUNKS = (EXACT_BITS+CPA_CHUNK_BITS-1)/CPA_CHUNK_BITS;
    localparam int CPA_LEVELS = $clog2(CPA_CHUNKS);
    wire [EXACT_BITS-1:0] cpa_base_comb, cpa_plus_comb;
    wire [EXACT_BITS-1:0] cpa_result_comb;
    wire [CPA_CHUNKS-1:0] cpa_generate_comb, cpa_propagate_comb;
    wire [CPA_CHUNKS-1:0] cpa_pre_generate_comb, cpa_pre_propagate_comb;
    logic [EXACT_BITS-1:0] cpa_base_reg, cpa_plus_reg;
    logic [EXACT_BITS-1:0] sum_reg, carry_reg;
    logic [CPA_CHUNKS-1:0] cpa_generate_reg, cpa_propagate_reg;
    wire [CPA_CHUNKS-1:0] cpa_group_generate [0:CPA_LEVELS-1];
    wire [CPA_CHUNKS-1:0] cpa_group_propagate [0:CPA_LEVELS-1];
    for (genvar chunk=0; chunk<CPA_CHUNKS; chunk++) begin : cpa_chunk
        localparam int LO = chunk*CPA_CHUNK_BITS;
        localparam int WIDTH = (EXACT_BITS-LO < CPA_CHUNK_BITS) ?
                               EXACT_BITS-LO : CPA_CHUNK_BITS;
        wire [WIDTH:0] sum_without_carry;
        wire [WIDTH-1:0] sum_with_carry;
        wire carry_in;
        assign sum_without_carry = {1'b0,sum_reg[LO +: WIDTH]} +
                                   {1'b0,carry_reg[LO +: WIDTH]};
        assign sum_with_carry = sum_without_carry[WIDTH-1:0] + WIDTH'(1);
        assign cpa_base_comb[LO +: WIDTH] = sum_without_carry[WIDTH-1:0];
        assign cpa_plus_comb[LO +: WIDTH] = sum_with_carry;
        assign cpa_generate_comb[chunk] = sum_without_carry[WIDTH];
        assign cpa_propagate_comb[chunk] =
            &(sum_reg[LO +: WIDTH] ^ carry_reg[LO +: WIDTH]);
        // Register the first prefix level with each chunk sum. The next
        // stage then handles only offsets 2, 4, 8, ... before its CPA mux.
        if (chunk >= 1) begin : first_prefix
            assign cpa_pre_generate_comb[chunk] = cpa_generate_comb[chunk] |
                (cpa_propagate_comb[chunk] & cpa_generate_comb[chunk-1]);
            assign cpa_pre_propagate_comb[chunk] = cpa_propagate_comb[chunk] &
                cpa_propagate_comb[chunk-1];
        end else begin : first_prefix_root
            assign cpa_pre_generate_comb[chunk] = cpa_generate_comb[chunk];
            assign cpa_pre_propagate_comb[chunk] = cpa_propagate_comb[chunk];
        end
        assign cpa_group_generate[0][chunk] = cpa_generate_reg[chunk];
        assign cpa_group_propagate[0][chunk] = cpa_propagate_reg[chunk];
        for (genvar level=1; level<CPA_LEVELS; level++) begin : prefix_level
            if (chunk >= (1 << level)) begin : combine
                assign cpa_group_generate[level][chunk] =
                    cpa_group_generate[level-1][chunk] |
                    (cpa_group_propagate[level-1][chunk] &
                     cpa_group_generate[level-1][chunk-(1 << level)]);
                assign cpa_group_propagate[level][chunk] =
                    cpa_group_propagate[level-1][chunk] &
                    cpa_group_propagate[level-1][chunk-(1 << level)];
            end else begin : copy
                assign cpa_group_generate[level][chunk] =
                    cpa_group_generate[level-1][chunk];
                assign cpa_group_propagate[level][chunk] =
                    cpa_group_propagate[level-1][chunk];
            end
        end
        if (chunk == 0) assign carry_in = 1'b0;
        else assign carry_in = cpa_group_generate[CPA_LEVELS-1][chunk-1];
        assign cpa_result_comb[LO +: WIDTH] = carry_in ?
            cpa_plus_reg[LO +: WIDTH] : cpa_base_reg[LO +: WIDTH];
    end
    always_ff @(posedge clk) begin
        cpa_result <= cpa_result_comb;
        if (valid_data_in) begin
            sum_reg <= sum_in;
            carry_reg <= carry_word_in;
        end
        if (valid_in) begin
            cpa_base_reg <= cpa_base_comb;
            cpa_plus_reg <= cpa_plus_comb;
            cpa_generate_reg <= cpa_pre_generate_comb;
            cpa_propagate_reg <= cpa_pre_propagate_comb;
        end
    end
endmodule

// Keep the 580-bit CPA-to-postprocess result entirely inside one routed macro.
(* keep_hierarchy = "yes" *) module t10_reference_cpa_postprocess (
    input logic clk, rst_n,
    input logic valid_data_in, valid_in,
    input logic [579:0] sum_in, carry_word_in,
    input logic post2_valid,
    input logic [63:0] post2_integer,
    input logic post2_is_integer,
    input logic post2_nan, post2_plus_inf, post2_minus_inf,
    input logic [3:0] post2_slot,
    output logic [63:0] result,
    output logic result_valid,
    output logic [3:0] result_slot
);
    /* verilator hier_block */
    wire [579:0] cpa_result;
    t10_reference_cpa cpa (
        .clk, .valid_data_in, .valid_in, .sum_in, .carry_word_in,
        .cpa_result
    );
    t10_reference_postprocess postprocess (
        .clk, .rst_n, .post2_valid, .post2_exact(cpa_result),
        .post2_integer, .post2_is_integer,
        .post2_nan, .post2_plus_inf, .post2_minus_inf,
        .post2_slot, .result, .result_valid, .result_slot
    );
endmodule


// Three macro stages turn each quad's carry-save pair into one exact word.
// A former PE register stage is removed to preserve end-to-end latency.
module t10_reference_fp_quad_exact #(
    parameter int SUPPORT_CLASS = 0
) (
    input  logic clk,
    input  logic [63:0] a_raw, b_raw,
    input  logic [3:0] mode, lane_active,
    input  logic [7:0] a_scale, b_scale,
    output logic [579:0] exact_word,
    output logic [2:0] negative_count,
    output logic nan_value, plus_inf, minus_inf
);
    localparam int BLOCK_BITS = 20;
    localparam int BLOCKS = 29;
    logic [579:0] csa_sum, csa_carry;
    logic [2:0] raw_negative_count, negative_count_q, negative_count_mid_q;
    logic raw_nan, raw_plus_inf, raw_minus_inf;
    logic nan_q, plus_inf_q, minus_inf_q;
    logic nan_mid_q, plus_inf_mid_q, minus_inf_mid_q;
    logic [BLOCK_BITS-1:0] sum0_q [0:BLOCKS-1];
    logic [BLOCK_BITS-1:0] sum1_q [0:BLOCKS-1];
    logic [BLOCK_BITS-1:0] sum0_mid_q [0:BLOCKS-1];
    logic [BLOCK_BITS-1:0] sum1_mid_q [0:BLOCKS-1];
    logic [BLOCKS-1:0] generate_q, propagate_q;
    logic [BLOCKS-1:0] prefix_g [0:3];
    logic [BLOCKS-1:0] prefix_p [0:3];
    logic [BLOCKS-1:0] mid_g_q, mid_p_q;
    logic [BLOCKS-1:0] final_g [0:2];
    logic [BLOCKS-1:0] final_p [0:2];
    t10_reference_fp_quad #(.SUPPORT_CLASS(SUPPORT_CLASS)) original_quad (
        .clk, .a_raw, .b_raw, .mode, .lane_active, .a_scale, .b_scale,
        .sum_word(csa_sum), .carry_word(csa_carry),
        .negative_count(raw_negative_count), .nan_value(raw_nan),
        .plus_inf(raw_plus_inf), .minus_inf(raw_minus_inf)
    );
    for (genvar block=0; block<BLOCKS; block++) begin : add_block
        wire [BLOCK_BITS:0] base_sum =
            {1'b0,csa_sum[block*BLOCK_BITS +: BLOCK_BITS]} +
            {1'b0,csa_carry[block*BLOCK_BITS +: BLOCK_BITS]};
        always_ff @(posedge clk) begin
            sum0_q[block] <= base_sum[BLOCK_BITS-1:0];
            sum1_q[block] <= base_sum[BLOCK_BITS-1:0] + BLOCK_BITS'(1);
            generate_q[block] <= base_sum[BLOCK_BITS];
            propagate_q[block] <=
                &(csa_sum[block*BLOCK_BITS +: BLOCK_BITS] ^
                  csa_carry[block*BLOCK_BITS +: BLOCK_BITS]);
        end
    end
    assign prefix_g[0] = generate_q;
    assign prefix_p[0] = propagate_q;
    for (genvar level=0; level<3; level++) begin : prefix_level
        for (genvar block=0; block<BLOCKS; block++) begin : prefix_block
            if (block >= (1 << level)) begin : combine
                assign prefix_g[level+1][block] =
                    prefix_g[level][block] |
                    (prefix_p[level][block] &
                     prefix_g[level][block-(1 << level)]);
                assign prefix_p[level+1][block] =
                    prefix_p[level][block] &
                    prefix_p[level][block-(1 << level)];
            end else begin : passthrough
                assign prefix_g[level+1][block] = prefix_g[level][block];
                assign prefix_p[level+1][block] = prefix_p[level][block];
            end
        end
    end
    always_ff @(posedge clk) begin
        mid_g_q <= prefix_g[3];
        mid_p_q <= prefix_p[3];
        negative_count_q <= raw_negative_count;
        nan_q <= raw_nan;
        plus_inf_q <= raw_plus_inf;
        minus_inf_q <= raw_minus_inf;
        negative_count_mid_q <= negative_count_q;
        nan_mid_q <= nan_q;
        plus_inf_mid_q <= plus_inf_q;
        minus_inf_mid_q <= minus_inf_q;
        negative_count <= negative_count_mid_q;
        nan_value <= nan_mid_q;
        plus_inf <= plus_inf_mid_q;
        minus_inf <= minus_inf_mid_q;
    end
    for (genvar block=0; block<BLOCKS; block++) begin : mid_block
        always_ff @(posedge clk) begin
            sum0_mid_q[block] <= sum0_q[block];
            sum1_mid_q[block] <= sum1_q[block];
        end
    end
    assign final_g[0] = mid_g_q;
    assign final_p[0] = mid_p_q;
    for (genvar level=0; level<2; level++) begin : final_prefix_level
        for (genvar block=0; block<BLOCKS; block++) begin : final_prefix_block
            if (block >= (1 << (level+3))) begin : combine
                assign final_g[level+1][block] =
                    final_g[level][block] |
                    (final_p[level][block] &
                     final_g[level][block-(1 << (level+3))]);
                assign final_p[level+1][block] =
                    final_p[level][block] &
                    final_p[level][block-(1 << (level+3))];
            end else begin : passthrough
                assign final_g[level+1][block] = final_g[level][block];
                assign final_p[level+1][block] = final_p[level][block];
            end
        end
    end
    for (genvar block=0; block<BLOCKS; block++) begin : output_block
        if (block == 0) begin : first
            always_ff @(posedge clk)
                exact_word[block*BLOCK_BITS +: BLOCK_BITS] <= sum0_mid_q[block];
        end else begin : rest
            always_ff @(posedge clk)
                exact_word[block*BLOCK_BITS +: BLOCK_BITS] <=
                    final_g[2][block-1] ? sum1_mid_q[block] : sum0_mid_q[block];
        end
    end
endmodule

(* keep_hierarchy = "yes" *) module t10_reference_fp_quad_class0 (
    input logic clk,
    input logic [63:0] a_raw, b_raw,
    input logic [3:0] mode,
    input logic [3:0] lane_active,
    input logic [7:0] a_scale, b_scale,
    output logic [579:0] sum_word, carry_word,
    output logic [2:0] negative_count,
    output logic nan_value, plus_inf, minus_inf
);
    t10_reference_fp_quad #(.SUPPORT_CLASS(0)) impl (.*);
endmodule

(* keep_hierarchy = "yes" *) module t10_reference_fp_quad_class1 (
    input logic clk,
    input logic [63:0] a_raw, b_raw,
    input logic [3:0] mode,
    input logic [3:0] lane_active,
    input logic [7:0] a_scale, b_scale,
    output logic [579:0] sum_word, carry_word,
    output logic [2:0] negative_count,
    output logic nan_value, plus_inf, minus_inf
);
    t10_reference_fp_quad #(.SUPPORT_CLASS(1)) impl (.*);
endmodule

(* keep_hierarchy = "yes" *) module t10_reference_fp_quad_class2 (
    input logic clk,
    input logic [63:0] a_raw, b_raw,
    input logic [3:0] mode,
    input logic [3:0] lane_active,
    input logic [7:0] a_scale, b_scale,
    output logic [579:0] sum_word, carry_word,
    output logic [2:0] negative_count,
    output logic nan_value, plus_inf, minus_inf
);
    t10_reference_fp_quad #(.SUPPORT_CLASS(2)) impl (.*);
endmodule

(* keep_hierarchy = "yes" *) module t10_reference_fp_quad_class0_exact (
    input logic clk,
    input logic [63:0] a_raw, b_raw,
    input logic [3:0] mode, lane_active,
    input logic [7:0] a_scale, b_scale,
    output logic [579:0] exact_word,
    output logic [2:0] negative_count,
    output logic nan_value, plus_inf, minus_inf
);
    t10_reference_fp_quad_exact #(.SUPPORT_CLASS(0)) impl (.*);
endmodule

(* keep_hierarchy = "yes" *) module t10_reference_fp_quad_class1_exact (
    input logic clk,
    input logic [63:0] a_raw, b_raw,
    input logic [3:0] mode, lane_active,
    input logic [7:0] a_scale, b_scale,
    output logic [579:0] exact_word,
    output logic [2:0] negative_count,
    output logic nan_value, plus_inf, minus_inf
);
    t10_reference_fp_quad_exact #(.SUPPORT_CLASS(1)) impl (.*);
endmodule

(* keep_hierarchy = "yes" *) module t10_reference_fp_quad_class2_exact (
    input logic clk,
    input logic [63:0] a_raw, b_raw,
    input logic [3:0] mode, lane_active,
    input logic [7:0] a_scale, b_scale,
    output logic [579:0] exact_word,
    output logic [2:0] negative_count,
    output logic nan_value, plus_inf, minus_inf
);
    t10_reference_fp_quad_exact #(.SUPPORT_CLASS(2)) impl (.*);
endmodule
