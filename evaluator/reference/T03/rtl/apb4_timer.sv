module apb4_timer (
  input logic clk, rst_n,
  input logic PSEL, PENABLE, PWRITE,
  input logic [11:0] PADDR,
  input logic [31:0] PWDATA,
  input logic [3:0] PSTRB,
  input logic [2:0] PPROT,
  output logic [31:0] PRDATA,
  output logic PREADY, PSLVERR, irq
);
  logic [31:0] ctrl, load_reg, count_reg;
  logic pending;
  logic [31:0] ctrl_next, load_next, count_next;
  logic pending_next;
  logic address_ok, access;
  function automatic logic [31:0] merge_bytes(
      input logic [31:0] old_value, new_value,
      input logic [3:0] strobes);
    logic [31:0] merged;
    merged = old_value;
    for (int i=0; i<4; i++)
      if (strobes[i]) merged[8*i +: 8] = new_value[8*i +: 8];
    merge_bytes = merged;
  endfunction
  assign access = PSEL && PENABLE;
  assign address_ok = PADDR == 12'h000 || PADDR == 12'h004 ||
                      PADDR == 12'h008 || PADDR == 12'h00c;
  assign PREADY = access;
  assign PSLVERR = access && !address_ok;
  assign irq = pending && ctrl[2];
  always_comb begin
    case (PADDR)
      12'h000: PRDATA = ctrl;
      12'h004: PRDATA = load_reg;
      12'h008: PRDATA = count_reg;
      12'h00c: PRDATA = {31'b0, pending};
      default: PRDATA = '0;
    endcase
    ctrl_next = ctrl;
    load_next = load_reg;
    count_next = count_reg;
    pending_next = pending;
    if (ctrl[0]) begin
      if (count_reg != 0) count_next = count_reg - 1'b1;
      else begin
        pending_next = 1'b1;
        if (ctrl[1]) count_next = load_reg;
        else ctrl_next[0] = 1'b0;
      end
    end
    if (access && PWRITE && address_ok) begin
      case (PADDR)
        12'h000: if (|PSTRB) ctrl_next = merge_bytes(ctrl, PWDATA, PSTRB) & 32'h7;
        12'h004: load_next = merge_bytes(load_reg, PWDATA, PSTRB);
        12'h008: if (|PSTRB) count_next = merge_bytes(count_reg, PWDATA, PSTRB);
        12'h00c: if (PSTRB[0] && PWDATA[0]) pending_next = 1'b0;
        default: ;
      endcase
    end
  end
  always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      ctrl <= '0;
      load_reg <= '0;
      count_reg <= '0;
      pending <= 1'b0;
    end else begin
      ctrl <= ctrl_next;
      load_reg <= load_next;
      count_reg <= count_next;
      pending <= pending_next;
    end
  end
endmodule
