`timescale 1ns/1ps

module serdes_rx_comma_aligner (
  input  logic       clk,
  input  logic       rst_n,
  input  logic       rx_valid,
  input  logic [9:0] rx_bits,
  output logic       locked,
  output logic       symbol_valid,
  output logic [9:0] symbol_out
);
  localparam logic [9:0] COMMA_P = 10'b0011111010;
  localparam logic [9:0] COMMA_N = 10'b1100000101;

  logic [9:0] previous_bits;
  logic       previous_valid;
  logic [19:0] bit_window;
  logic [9:0] scan_window [0:9];
  logic [1:0] train_count [0:9];
  logic [1:0] train_count_next [0:9];
  logic       acquisition_found;
  logic [3:0] acquisition_phase;
  logic [3:0] locked_phase;
  logic [3:0] frame_position;
  logic       marker_missed_once;

  function automatic logic is_comma(input logic [9:0] symbol);
    is_comma = symbol == COMMA_P || symbol == COMMA_N;
  endfunction

  always_comb begin
    bit_window = '0;
    bit_window[9:0] = previous_bits;
    bit_window[19:10] = rx_bits;
    scan_window[0] = rx_bits;
    for (int phase = 1; phase < 10; phase++)
      scan_window[phase] = bit_window[phase +: 10];
    acquisition_found = 1'b0;
    acquisition_phase = '0;
    for (int phase = 0; phase < 10; phase++) begin
      train_count_next[phase] = train_count[phase];
      if (rx_valid && (phase == 0 || previous_valid)) begin
        if (is_comma(scan_window[phase])) begin
          if (train_count[phase] == 2) begin
            train_count_next[phase] = 2;
            if (!acquisition_found) begin
              acquisition_found = 1'b1;
              acquisition_phase = 4'(phase);
            end
          end else begin
            train_count_next[phase] = train_count[phase] + 1'b1;
          end
        end else begin
          train_count_next[phase] = '0;
        end
      end
    end
  end

  always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      previous_bits <= '0;
      previous_valid <= 1'b0;
      locked <= 1'b0;
      locked_phase <= '0;
      frame_position <= '0;
      marker_missed_once <= 1'b0;
      symbol_valid <= 1'b0;
      symbol_out <= '0;
      for (int phase = 0; phase < 10; phase++)
        train_count[phase] <= '0;
    end else begin
      symbol_valid <= 1'b0;
      if (rx_valid) begin
        previous_bits <= rx_bits;
        previous_valid <= 1'b1;
        if (!locked) begin
          for (int phase = 0; phase < 10; phase++)
            train_count[phase] <= train_count_next[phase];
          if (acquisition_found) begin
            locked <= 1'b1;
            locked_phase <= acquisition_phase;
            frame_position <= '0;
            marker_missed_once <= 1'b0;
            for (int phase = 0; phase < 10; phase++)
              train_count[phase] <= '0;
          end
        end else begin
          symbol_valid <= 1'b1;
          symbol_out <= scan_window[locked_phase];
          if (frame_position == 15) begin
            frame_position <= '0;
            if (is_comma(scan_window[locked_phase])) begin
              marker_missed_once <= 1'b0;
            end else if (marker_missed_once) begin
              locked <= 1'b0;
              symbol_valid <= 1'b0;
              marker_missed_once <= 1'b0;
              for (int phase = 0; phase < 10; phase++)
                train_count[phase] <= '0;
            end else begin
              marker_missed_once <= 1'b1;
            end
          end else begin
            frame_position <= frame_position + 1'b1;
          end
        end
      end
    end
  end
endmodule
