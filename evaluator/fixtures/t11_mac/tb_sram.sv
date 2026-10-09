`timescale 1ns/1ps
module tb_t11_sram;
    logic clk_A = 0, clk_B = 0;
    logic ce_in_A = 0, ce_in_B = 0, we_in_A = 0;
    logic [11:0] addr_in_A = 0, addr_in_B = 0;
    logic [31:0] wd_in_A = 0, w_mask_in_A = '1;
    wire [31:0] rd_out_A, rd_out_B;
    fakeram7_tdp_4096x32 dut (
        .clk_A(clk_A), .ce_in_A(ce_in_A), .we_in_A(we_in_A),
        .addr_in_A(addr_in_A), .wd_in_A(wd_in_A), .w_mask_in_A(w_mask_in_A),
        .rd_out_A(rd_out_A),
        .clk_B(clk_B), .ce_in_B(ce_in_B), .we_in_B(1'b0),
        .addr_in_B(addr_in_B), .wd_in_B(32'b0), .w_mask_in_B(32'b0),
        .rd_out_B(rd_out_B)
    );
    always #0.5 clk_A = ~clk_A;
    initial begin #0.17; forever #0.65 clk_B = ~clk_B; end
    function automatic logic [31:0] pattern(input int index);
        return 32'h5a31_c79d ^ (32'h0101_1235 * index);
    endfunction
    task automatic write_word(input int index, input logic [31:0] data,
                              input logic [31:0] mask);
        @(negedge clk_A);
        ce_in_A = 1; we_in_A = 1;
        addr_in_A = 12'(index); wd_in_A = data; w_mask_in_A = mask;
        @(posedge clk_A); #0.01;
    endtask
    task automatic read_word(input int index, input logic [31:0] expected);
        @(negedge clk_B); ce_in_B = 1; addr_in_B = 12'(index);
        @(posedge clk_B); #0.01;
        if (rd_out_B !== expected)
            $fatal(1, "SRAM mismatch addr=%0d expected=%h actual=%h", index, expected, rd_out_B);
    endtask
    initial begin
        // Exercise every physical row, highest data/address bits and bit masks.
        for (int i = 0; i < 4096; i++) write_word(i, pattern(i), '1);
        @(negedge clk_A); ce_in_A = 0; we_in_A = 0;
        for (int i = 4095; i >= 0; i--) read_word(i, pattern(i));
        for (int i = 0; i < 4096; i++) write_word(i, ~pattern(i), 32'hff00_00ff);
        @(negedge clk_A); ce_in_A = 0; we_in_A = 0;
        for (int i = 0; i < 4096; i++)
            read_word(i, (pattern(i) & 32'h00ff_ff00) | (~pattern(i) & 32'hff00_00ff));
        // Concurrent, independent-clock read and write to disjoint address sets.
        fork
            begin
                for (int i = 0; i < 2048; i++) write_word(i, 32'hdead_0000 + i, '1);
                @(negedge clk_A); ce_in_A = 0; we_in_A = 0;
            end
            begin
                for (int i = 2048; i < 4096; i++)
                    read_word(i, (pattern(i) & 32'h00ff_ff00) | (~pattern(i) & 32'hff00_00ff));
            end
        join
        for (int i = 0; i < 2048; i++) read_word(i, 32'hdead_0000 + i);
        $display("T11_SRAM_MODEL_PASS rows=4096 masked_writes=4096 concurrent_reads=2048");
        $finish;
    end
    initial begin #100000; $fatal(1, "SRAM self-test watchdog"); end
endmodule
