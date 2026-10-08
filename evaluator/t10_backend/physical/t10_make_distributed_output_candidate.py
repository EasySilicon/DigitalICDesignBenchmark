"""Create an isolated candidate with one output slot per physical tile row.

Existing PE/tile/arithmetic definitions are byte-identical. The new egress
controllers are replicated per tile column, retaining data and control locally.
"""
import argparse
import hashlib
import json
from pathlib import Path


def replace_once(text, old, new):
    if text.count(old) != 1:
        raise ValueError(f'Expected one anchor: {old[:100]}')
    return text.replace(old, new, 1)


EGRESS = r'''
// One physical tile supplies a quarter of its row group's output lane.
// Replicated controllers execute identical transactions independently;
// bank addresses, queue enables and row selection stay beside the data.
(* keep_hierarchy = "yes" *) module t10_reference_distributed_tile_egress #(
    parameter integer ROW_GROUP = 0
) (
    input logic clk, rst_n,
    input logic [1023:0] read_data,
    output logic [15:0] read_slot,
    input logic [15:0] complete_bits,
    input logic [255:0] block_ids,
    input logic [4:0] previous_retired,
    input logic external_accept,
    output logic offered_valid,
    output logic [15:0] block_id,
    output logic [3:0] row,
    output logic [255:0] data,
    output logic [4:0] retired,
    output logic [4:0] next_captured,
    output logic [3:0] captured_slot,
    output logic capture_commit
);
    logic [3:0] source_slot;
    logic [1:0] source_row;
    logic [3:0] bank_slot [0:3];
    logic [3:0] consumed_1, consumed_2;
    logic source_ready, source_fire;
    logic prefetch_valid, gather_valid;
    logic [3:0] prefetch_select;
    logic [1:0] prefetch_row, gather_row;
    logic [15:0] prefetch_id, gather_id;
    logic gather_ready, queue_ready, queue_push, queue_pop;
    logic [1:0] queue_count;
    logic queue_read_ptr, queue_write_ptr;
    logic [1:0] queue_row [0:1];
    logic [15:0] queue_id [0:1];
    logic [4:0] captured;
    wire eligible = ROW_GROUP == 0 || previous_retired != retired;

    assign queue_ready = queue_count != 2;
    assign gather_ready = !gather_valid || queue_ready;
    assign source_ready = !prefetch_valid || gather_ready;
    assign source_fire = complete_bits[source_slot] && source_ready;
    assign queue_push = gather_valid && queue_ready;
    assign offered_valid = queue_count != 0 && eligible;
    assign queue_pop = external_accept;
    assign row = 4'(ROW_GROUP*4) + {2'b0, queue_row[queue_read_ptr]};
    assign block_id = queue_id[queue_read_ptr];
    assign capture_commit = gather_ready && prefetch_valid && prefetch_row == 3;
    assign captured_slot = captured[3:0];
    assign next_captured = captured + {4'b0, capture_commit};

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            source_slot <= '0;
            source_row <= '0;
            prefetch_valid <= 1'b0;
            gather_valid <= 1'b0;
            consumed_1 <= '0;
            consumed_2 <= '0;
            queue_count <= '0;
            queue_read_ptr <= 1'b0;
            queue_write_ptr <= 1'b0;
            retired <= '0;
            captured <= '0;
            for (int r=0; r<4; r++) bank_slot[r] <= '0;
        end else begin
            if (capture_commit) captured <= captured + 5'd1;
            consumed_1 <= source_fire ? (4'b1 << source_row) : 4'b0;
            consumed_2 <= consumed_1;
            for (int r=0; r<4; r++)
                if (consumed_2[r]) bank_slot[r] <= bank_slot[r] + 4'd1;
            if (source_fire) begin
                source_row <= source_row + 2'd1;
                if (source_row == 3) source_slot <= source_slot + 4'd1;
            end
            if (source_ready) prefetch_valid <= complete_bits[source_slot];
            if (gather_ready) gather_valid <= prefetch_valid;
            case ({queue_push, queue_pop})
                2'b10: queue_count <= queue_count + 2'd1;
                2'b01: queue_count <= queue_count - 2'd1;
                default: queue_count <= queue_count;
            endcase
            if (queue_push) queue_write_ptr <= ~queue_write_ptr;
            if (queue_pop) begin
                queue_read_ptr <= ~queue_read_ptr;
                if (queue_row[queue_read_ptr] == 3) retired <= retired + 5'd1;
            end
        end
    end
    always_ff @(posedge clk) begin
        if (source_ready) prefetch_select <= source_fire ? (4'b1 << source_row) : 4'b0;
        if (source_fire) begin
            prefetch_row <= source_row;
            prefetch_id <= block_ids[source_slot*16 +: 16];
        end
        if (gather_ready && prefetch_valid) begin
            gather_row <= prefetch_row;
            gather_id <= prefetch_id;
        end
        if (queue_push) begin
            queue_row[queue_write_ptr] <= gather_row;
            queue_id[queue_write_ptr] <= gather_id;
        end
    end
    for (genvar r=0; r<4; r++) begin : address
        assign read_slot[r*4 +: 4] = bank_slot[r];
    end
    for (genvar c=0; c<4; c++) begin : local_column
        wire [37:0] selected_data, output_data;
        t10_reference_gather_lane local_selector (
            .clk, .rst_n, .gather_stage_ready(gather_ready),
            .prefetch_any_valid(prefetch_valid), .row_select(prefetch_select),
            .source_data_0(read_data[c*64 +: 38]),
            .source_data_1(read_data[256+c*64 +: 38]),
            .source_data_2(read_data[512+c*64 +: 38]),
            .source_data_3(read_data[768+c*64 +: 38]),
            .gather_data(selected_data)
        );
        t10_reference_output_queue_lane local_queue (
            .clk, .rst_n, .write_enable(queue_push), .write_select(queue_write_ptr),
            .write_data(selected_data), .read_advance(queue_pop), .read_data(output_data)
        );
        assign data[c*64 +: 64] = {{26{output_data[37]}}, output_data};
    end
endmodule
'''


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('source_sv'); p.add_argument('output_dir')
    p.add_argument('--local-ready', action='store_true')
    p.add_argument('--queue-depth', type=int, choices=(2,4), default=2)
    p.add_argument('--capture-credit', action='store_true')
    p.add_argument('--one-credit-stage', action='store_true')
    p.add_argument('--local-accept', action='store_true')
    p.add_argument('--independent-mask-capture', action='store_true')
    args = p.parse_args()
    source = Path(args.source_sv); root = Path(args.output_dir)
    before = source.read_text(); text = before
    text = replace_once(text, '    logic [1023:0] row_read_data [0:15];', '''    logic [1023:0] row_read_data [0:15];
    wire [1023:0] tile_result_data [0:3][0:3];
    wire [15:0] tile_result_read_slot [0:3][0:3];
    wire [4:0] tile_retired [0:3][0:3];
    wire [3:0] tile_offered [0:3];
    wire [15:0] complete_bits;
    wire [255:0] block_ids;
    logic output_mask_locked;
    logic [3:0] locked_output_mask;
    wire [3:0] offered_output_mask;''')
    text = replace_once(text, '                assign tile_read_slot[i*4 +: 4] = row_read_slot[R];\n', '')
    text = replace_once(text, '            t10_reference_tile_4x4 tile (', '''            assign tile_read_slot = tile_result_read_slot[tr][tc];
            assign tile_result_data[tr][tc] = tile_read_data;
            t10_reference_tile_4x4 tile (''')
    start = text.index('    for (genvar r=0; r<16; r++) begin : result_row')
    end = text.index('    always_ff @(posedge clk or negedge rst_n) begin\n        if (!rst_n) begin\n            active <=', start)
    text = text[:start] + '''    for (genvar slot=0; slot<16; slot++) begin : egress_metadata
        assign complete_bits[slot] = complete[slot];
        assign block_ids[slot*16 +: 16] = slot_id[slot];
    end
    // Each architectural output slot belongs to one physical tile row.
    // Adjacent tile columns drive disjoint 256-bit slices of that slot.
    for (genvar g=0; g<4; g++) begin : distributed_output_row
        assign offered_output_mask[g] = tile_offered[g][0];
        for (genvar tc=0; tc<4; tc++) begin : tile_column
            wire [15:0] local_block_id;
            wire [3:0] local_row;
            t10_reference_distributed_tile_egress #(.ROW_GROUP(g)) egress (
                .clk, .rst_n,
                .read_data(tile_result_data[g][tc]),
                .read_slot(tile_result_read_slot[g][tc]),
                .complete_bits, .block_ids,
                .previous_retired(g == 0 ? 5'b0 : tile_retired[g-1][tc]),
                .external_accept(out_valid[g] && out_ready),
                .offered_valid(tile_offered[g][tc]),
                .block_id(local_block_id), .row(local_row),
                .data(out_data[g*1024+tc*256 +: 256]),
                .retired(tile_retired[g][tc])
            );
            if (tc == 0) begin : metadata
                assign out_block_id[g*16 +: 16] = local_block_id;
                assign out_row[g*4 +: 4] = local_row;
            end
        end
    end
    // The interface freezes the entire valid mask on backpressure. Local
    // queues may fill while stalled, but newly offered slots stay hidden
    // until the existing atomic packet is accepted.
    assign out_valid = output_mask_locked ? locked_output_mask : offered_output_mask;
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            output_mask_locked <= 1'b0;
            locked_output_mask <= '0;
        end else if (out_ready) begin
            output_mask_locked <= 1'b0;
        end else if (!output_mask_locked && (|out_valid)) begin
            output_mask_locked <= 1'b1;
            locked_output_mask <= out_valid;
        end
    end
    // A block's storage credit is released only after its final row is
    // externally accepted, by which point the earlier groups have retired.
    assign output_last = out_valid[3] && out_ready && out_row[15:12] == 4'd15;
''' + text[end:]
    start = text.index('            // Start a block\'s w-cycle readout')
    end = text.index('            if (output_last) begin', start)
    text = text[:start] + '''            // Local egress controllers can prefetch their own rows once
            // all results are available; ordering is enforced at retirement.
            if (pe_boundary_done_s2[15])
                complete[pe_boundary_slot_s2[15]] <= 1'b1;
''' + text[end:]
    text = replace_once(text, '''            end else if (output_fire)
                output_row <= next_output_row[3:0];''', '            end')
    if args.local_ready:
        text = replace_once(text, '    wire [15:0] complete_bits;', '''    wire [15:0] complete_bits;
    logic local_ready [0:3][0:15];
    wire [15:0] local_ready_bits [0:3];''')
        text = replace_once(text, '                .complete_bits, .block_ids,',
                            '                .complete_bits(local_ready_bits[g]), .block_ids,')
        text = replace_once(text, '    // Each architectural output slot belongs to one physical tile row.', '''    // Each four-row group starts from its own first row's completion token.
    // Later rows arrive at one row/cycle. Waiting for the final row of the
    // entire matrix unnecessarily delays output and exhausts block credits.
    for (genvar g=0; g<4; g++) begin : local_completion
        for (genvar slot=0; slot<16; slot++) begin : bits
            assign local_ready_bits[g][slot] = local_ready[g][slot];
        end
        always_ff @(posedge clk or negedge rst_n) begin
            if (!rst_n) begin
                for (int slot=0; slot<16; slot++) local_ready[g][slot] <= 1'b0;
            end else begin
                if (input_first) local_ready[g][write_slot] <= 1'b0;
                if (pe_boundary_done_s2[g*4])
                    local_ready[g][pe_boundary_slot_s2[g*4]] <= 1'b1;
                if (out_valid[g] && out_ready && out_row[g*4 +: 4] == 4'(g*4+3))
                    local_ready[g][tile_retired[g][0][3:0]] <= 1'b0;
            end
        end
    end
    // Each architectural output slot belongs to one physical tile row.''')
    if args.capture_credit:
        assert args.local_ready
        text = replace_once(text, '    wire [4:0] tile_retired [0:3][0:3];', '''    wire [4:0] tile_retired [0:3][0:3];
    wire [4:0] tile_next_captured [0:3][0:3];
    wire [3:0] tile_captured_slot [0:3][0:3];
    wire tile_capture_commit [0:3][0:3];
    wire [15:0] tile_credit_available;''')
        text = replace_once(text, '                .retired(tile_retired[g][tc])', '''                .retired(tile_retired[g][tc]),
                .next_captured(tile_next_captured[g][tc]),
                .captured_slot(tile_captured_slot[g][tc]),
                .capture_commit(tile_capture_commit[g][tc])''')
        text = replace_once(text, '            if (tc == 0) begin : metadata', '''            assign tile_credit_available[g*4+tc] =
                tile_next_captured[g][tc] != {read_wrap, read_slot};
            if (tc == 0) begin : metadata''')
        text = replace_once(text, '''                if (out_valid[g] && out_ready && out_row[g*4 +: 4] == 4'(g*4+3))
                    local_ready[g][tile_retired[g][0][3:0]] <= 1'b0;''', '''                if (tile_capture_commit[g][0])
                    local_ready[g][tile_captured_slot[g][0]] <= 1'b0;''')
        text = replace_once(text, '''    // A block's storage credit is released only after its final row is
    // externally accepted, by which point the earlier groups have retired.
    assign output_last = out_valid[3] && out_ready && out_row[15:12] == 4'd15;''', '''    // Release the result-bank slot once every physical tile has captured
    // its four rows into elastic storage. All sixteen slices participate.
    // Backpressure retains those values in local FIFOs/gather registers;
    // no subsequent external retirement clears a newly reused slot's flag.
    assign output_last = &tile_credit_available;''')
    if args.one_credit_stage:
        text = replace_once(text, '    assign in_ready = ingress_open || !slot_full_io;',
                            '    assign in_ready = ingress_open || !slot_full_state;')
    if args.independent_mask_capture:
        text = replace_once(text, '''        end else if (!output_mask_locked && (|out_valid)) begin
            output_mask_locked <= 1'b1;
            locked_output_mask <= out_valid;
        end''', '''        end else if (!output_mask_locked) begin
            // Capture each offered bit while unlocked. A zero mask leaves
            // the interface unlocked; no global any-valid is needed on
            // individual held-mask register enables.
            output_mask_locked <= |offered_output_mask;
            locked_output_mask <= offered_output_mask;
        end''')
    old_modules = before.split('\nendmodule\n', 1)[1]
    assert text.split('\nendmodule\n', 1)[1] == old_modules
    egress = EGRESS
    if args.local_accept:
        text = replace_once(text, '                .external_accept(out_valid[g] && out_ready),',
                            '''                .ready_in(out_ready), .output_mask_locked,
                .locked_valid(locked_output_mask[g]),''')
        egress = replace_once(egress, '    input logic external_accept,',
                              '''    input logic ready_in, output_mask_locked, locked_valid,''')
        egress = replace_once(egress, '    assign queue_pop = external_accept;',
                              '''    // Replicated state offers the same valid in each tile column.
    // Form accept beside each queue, without canonical-column round trips.
    assign queue_pop = ready_in && (output_mask_locked ? locked_valid : offered_valid);''')
    if args.queue_depth == 4:
        egress = replace_once(egress, '    logic [1:0] queue_count;', '    logic [2:0] queue_count;')
        egress = replace_once(egress, '    logic queue_read_ptr, queue_write_ptr;', '    logic [1:0] queue_read_ptr, queue_write_ptr;')
        egress = egress.replace('queue_row [0:1]', 'queue_row [0:3]').replace('queue_id [0:1]', 'queue_id [0:3]')
        egress = replace_once(egress, 'assign queue_ready = queue_count != 2;', 'assign queue_ready = queue_count != 4;')
        egress = egress.replace('queue_count + 2\'d1', 'queue_count + 3\'d1').replace('queue_count - 2\'d1', 'queue_count - 3\'d1')
        egress = egress.replace('queue_write_ptr <= ~queue_write_ptr', "queue_write_ptr <= queue_write_ptr + 2'd1")
        egress = egress.replace('queue_read_ptr <= ~queue_read_ptr', "queue_read_ptr <= queue_read_ptr + 2'd1")
        egress = replace_once(egress, '''        t10_reference_output_queue_lane local_queue (
            .clk, .rst_n, .write_enable(queue_push), .write_select(queue_write_ptr),
            .write_data(selected_data), .read_advance(queue_pop), .read_data(output_data)
        );''', '''        // Four local entries absorb the group-to-group retirement offset
        // without borrowing a combinational out_ready credit on full.
        logic [37:0] data_bank [0:3];
        always_ff @(posedge clk)
            if (queue_push) data_bank[queue_write_ptr] <= selected_data;
        assign output_data = data_bank[queue_read_ptr];''')
    text += egress
    rtl = root/'rtl'; rtl.mkdir(parents=True, exist_ok=True)
    output = rtl/'npu_systolic_matmul_16x16.sv'
    if output.exists(): raise FileExistsError(output)
    output.write_text(text); (rtl/'files.f').write_text(output.name+'\n')
    record = {'diagnostic_only': True, 'qualification_passed': False,
              'source': str(source), 'source_sha256': hashlib.sha256(before.encode()).hexdigest(),
              'rtl_sha256': hashlib.sha256(text.encode()).hexdigest(),
              'existing_submodule_definitions_byte_identical': True,
              'existing_submodule_definitions_sha256': hashlib.sha256(old_modules.encode()).hexdigest(),
              'added_egress_helper_sha256': hashlib.sha256(egress.encode()).hexdigest(),
              'change': 'four output slots fixed to physical tile rows; sixteen local egress controllers',
              'local_row_group_completion': args.local_ready,
              'local_output_queue_depth': args.queue_depth,
              'credit_released_after_all_tile_captures': args.capture_credit,
              'input_credit_status_register_stages':1 if args.one_credit_stage else 2,
              'accept_formed_inside_each_tile_controller':args.local_accept,
              'held_mask_capture_independent_of_any_valid':args.independent_mask_capture,
              'tile_macros': 16, 'pe_count': 256}
    (root/'rtl_delta.json').write_text(json.dumps(record, indent=2)+'\n')
    print(json.dumps(record, indent=2))


if __name__ == '__main__': main()
