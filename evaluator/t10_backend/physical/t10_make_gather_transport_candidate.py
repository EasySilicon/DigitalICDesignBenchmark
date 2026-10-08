"""Generate an isolated full-DUT candidate with an elastic gather transport.

The two-entry packet queue breaks the combinational output-credit to gather
ready dependency, sustains one packet per cycle, and adds one empty-path
cycle. Reuse the existing 38-bit queue lane; all submodule bodies stay exact.
"""
import argparse
import hashlib
import json
from pathlib import Path


def replace_once(text, old, new):
    if text.count(old) != 1: raise ValueError(f'Expected one candidate anchor: {old[:80]}')
    return text.replace(old,new,1)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('source_sv');p.add_argument('output_dir')
    p.add_argument('--pair-groups',action='store_true')
    args=p.parse_args()
    source=Path(args.source_sv); root=Path(args.output_dir)
    before=source.read_text(); text=before
    text=replace_once(text,'    logic [607:0] gather_group_data [0:3][0:3];\n',
'''    logic [607:0] gather_group_data [0:3][0:3];
    // An independent two-entry transport queue decouples the spatial gather
    // stage from the final queue's credit/ready chain. Every packet carries
    // all four slot vectors and their original metadata. A full queue does
    // not borrow same-cycle pop credit, preserving a local ready predicate.
    logic [607:0] transport_group_data [0:3][0:3];
    logic [1:0] transport_count;
    logic transport_read_ptr, transport_write_ptr;
    logic transport_ready, transport_push, transport_pop;
    logic [3:0] transport_valid_bank [0:1];
    logic [63:0] transport_block_id_bank [0:1];
    logic [15:0] transport_row_bank [0:1];
    logic [3:0] transport_valid;
    logic [63:0] transport_block_id;
    logic [15:0] transport_row;
''')
    text=replace_once(text,'    assign gather_stage_ready = !(|gather_valid) || output_stage_ready;',
'''    assign gather_stage_ready = !(|gather_valid) || transport_ready;
    assign transport_ready = transport_count != 2;
    assign transport_push = (|gather_valid) && transport_ready;
    assign transport_pop = (transport_count != 0) && output_stage_ready;
    assign transport_valid = transport_count == 0 ? 4'b0 :
                             transport_valid_bank[transport_read_ptr];
    assign transport_block_id = transport_block_id_bank[transport_read_ptr];
    assign transport_row = transport_row_bank[transport_read_ptr];
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            transport_count <= 2'b0;
            transport_read_ptr <= 1'b0;
            transport_write_ptr <= 1'b0;
        end else begin
            case ({transport_push, transport_pop})
                2'b10: transport_count <= transport_count + 2'd1;
                2'b01: transport_count <= transport_count - 2'd1;
                default: transport_count <= transport_count;
            endcase
            if (transport_push) transport_write_ptr <= ~transport_write_ptr;
            if (transport_pop) transport_read_ptr <= ~transport_read_ptr;
        end
    end
    always_ff @(posedge clk) begin
        if (transport_push) begin
            transport_valid_bank[transport_write_ptr] <= gather_valid;
            transport_block_id_bank[transport_write_ptr] <= gather_block_id;
            transport_row_bank[transport_write_ptr] <= gather_row;
        end
    end
    for (genvar s=0; s<4; s++) begin : gather_transport_slot
        for (genvar g=0; g<4; g++) begin : gather_transport_group
            for (genvar c=0; c<16; c++) begin : gather_transport_cell
                t10_reference_output_queue_lane transport_lane (
                    .clk,
                    .rst_n,
                    .write_enable(transport_push),
                    .write_select(transport_write_ptr),
                    .write_data(gather_group_data[s][g][c*38 +: 38]),
                    .read_advance(transport_pop),
                    .read_data(transport_group_data[s][g][c*38 +: 38])
                );
            end
        end
    end''')
    text=replace_once(text,'        else if (output_stage_ready) output_stage_valid <= gather_valid;',
                     '        else if (output_stage_ready) output_stage_valid <= transport_valid;')
    text=replace_once(text,'''        if (output_stage_ready && (|gather_valid)) begin
            output_stage_block_id <= gather_block_id;
            output_stage_row <= gather_row;''',
'''        if (output_stage_ready && (|transport_valid)) begin
            output_stage_block_id <= transport_block_id;
            output_stage_row <= transport_row;''')
    text=replace_once(text,'.gather_valid(gather_valid[s]),','.gather_valid(transport_valid[s]),')
    for group in range(4):
        text=replace_once(text,f'.group_data_{group}(gather_group_data[s][{group}][c*38 +: 38]),',
                          f'.group_data_{group}(transport_group_data[s][{group}][c*38 +: 38]),')
    if args.pair_groups:
        # OR is associative. Combining adjacent row groups before transport
        # halves the new payload storage while preserving the original
        # slot-valid masking and every exact encoded numeric result.
        text=replace_once(text,'    logic [607:0] transport_group_data [0:3][0:3];',
                         '    logic [607:0] transport_group_data [0:3][0:1];')
        text=replace_once(text,'for (genvar g=0; g<4; g++) begin : gather_transport_group',
                         'for (genvar g=0; g<2; g++) begin : gather_transport_group')
        text=replace_once(text,'.write_data(gather_group_data[s][g][c*38 +: 38]),',
                         '.write_data(gather_group_data[s][2*g][c*38 +: 38] |\n'
                         '                                gather_group_data[s][2*g+1][c*38 +: 38]),')
        for group in (2,3):
            text=replace_once(text,f'.group_data_{group}(transport_group_data[s][{group}][c*38 +: 38]),',
                              f".group_data_{group}(38'b0),")
    delimiter='\nendmodule\n'
    old_modules=before.split(delimiter,1)[1];new_modules=text.split(delimiter,1)[1]
    if old_modules!=new_modules: raise ValueError('PE, tile, arithmetic or helper submodule changed')
    rtl=root/'rtl';rtl.mkdir(parents=True,exist_ok=True)
    output=rtl/'npu_systolic_matmul_16x16.sv'
    if output.exists(): raise FileExistsError('Refuse to overwrite a candidate checkpoint')
    output.write_text(text);(rtl/'files.f').write_text(output.name+'\n')
    record={'diagnostic_only':True,'qualification_passed':False,'source':str(source),
            'source_sha256':hashlib.sha256(before.encode()).hexdigest(),
            'rtl_sha256':hashlib.sha256(text.encode()).hexdigest(),
            'all_submodule_definitions_byte_identical':True,
            'submodule_definitions_sha256':hashlib.sha256(new_modules.encode()).hexdigest(),
            'change':'two-entry gather transport queue; one-cycle minimum latency increment',
            'adjacent_row_group_pair_merge':args.pair_groups,
            'tile_macros':16,'pe_count':256,'nominal_added_state_bits':10028 if args.pair_groups else 19884,
            'state_bound_note':'Final state count is determined by the unchanged independent structure check.'}
    (root/'rtl_delta.json').write_text(json.dumps(record,indent=2)+'\n');print(json.dumps(record,indent=2))


if __name__=='__main__':main()
