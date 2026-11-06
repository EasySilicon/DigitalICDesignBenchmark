// Reduced from the legacy Kimi K3 row-assembly write pattern.
// The write after the reset if/else is triggered by BOTH sensitivity edges.
// Moving it to a clock-only process is a semantic change, not a frontend fix.
module reset_event_write(input wire clk,rst_n,we,input wire [7:0] d,output reg [7:0] q,output reg ready);
 always @(posedge clk or negedge rst_n) begin
  if (!rst_n) ready <= 0; else ready <= 1;
  if (we) q <= d;
 end
endmodule
module clock_only_write(input wire clk,rst_n,we,input wire [7:0] d,output reg [7:0] q,output reg ready);
 always @(posedge clk or negedge rst_n)
  if (!rst_n) ready <= 0; else ready <= 1;
 always @(posedge clk) if (we) q <= d;
endmodule
