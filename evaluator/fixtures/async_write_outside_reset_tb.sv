module tb;
 reg clk=0,rst_n=1,we=0; reg [7:0] d=0;wire [7:0] reset_event_write_q,clock_only_write_q;
 reset_event_write b(clk,rst_n,we,d,reset_event_write_q,);clock_only_write g(clk,rst_n,we,d,clock_only_write_q,);
 initial begin
  #1;we=1;d=8'h11;#1;clk=1;#1;clk=0;we=0;
  #1;we=1;d=8'h22;#1;rst_n=0;#1;
  if (reset_event_write_q !== 8'h22 || clock_only_write_q !== 8'h11) $fatal(1,"unexpected reset semantics");
  $display("RESET_EDGE event_q=%h clock_q=%h clk=%b",reset_event_write_q,clock_only_write_q,clk);$finish;
 end
endmodule
