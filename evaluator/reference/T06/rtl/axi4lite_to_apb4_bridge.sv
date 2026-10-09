module axi4lite_to_apb4_bridge (
  input logic clk, rst_n,
  input logic [31:0] AWADDR,
  input logic [2:0] AWPROT,
  input logic AWVALID,
  output logic AWREADY,
  input logic [31:0] WDATA,
  input logic [3:0] WSTRB,
  input logic WVALID,
  output logic WREADY,
  output logic [1:0] BRESP,
  output logic BVALID,
  input logic BREADY,
  input logic [31:0] ARADDR,
  input logic [2:0] ARPROT,
  input logic ARVALID,
  output logic ARREADY,
  output logic [31:0] RDATA,
  output logic [1:0] RRESP,
  output logic RVALID,
  input logic RREADY,
  output logic [15:0] PADDR,
  output logic PSEL, PENABLE, PWRITE,
  output logic [31:0] PWDATA,
  output logic [3:0] PSTRB,
  output logic [2:0] PPROT,
  input logic [31:0] PRDATA,
  input logic PREADY, PSLVERR
);
  typedef enum logic [1:0] {IDLE, SETUP, ACCESS} apb_state_t;
  apb_state_t state;
  logic have_aw, have_w, have_ar;
  logic [31:0] aw_addr, w_data, ar_addr;
  logic [2:0] aw_prot, ar_prot;
  logic [3:0] w_strb;
  logic [15:0] apb_addr;
  logic [31:0] apb_data;
  logic [3:0] apb_strb;
  logic [2:0] apb_prot;
  logic apb_write;
  logic prefer_write;
  logic write_busy, read_busy, write_pending, read_pending;

  assign write_busy = state != IDLE && apb_write;
  assign read_busy = state != IDLE && !apb_write;
  assign AWREADY = !have_aw && !write_busy && !BVALID;
  assign WREADY = !have_w && !write_busy && !BVALID;
  assign ARREADY = !have_ar && !read_busy && !RVALID;
  assign write_pending = have_aw && have_w;
  assign read_pending = have_ar;
  assign PSEL = state != IDLE;
  assign PENABLE = state == ACCESS;
  assign PWRITE = apb_write;
  assign PADDR = apb_addr;
  assign PWDATA = apb_data;
  assign PSTRB = apb_strb;
  assign PPROT = apb_prot;

  always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      state <= IDLE;
      have_aw <= 0;
      have_w <= 0;
      have_ar <= 0;
      aw_addr <= '0;
      aw_prot <= '0;
      w_data <= '0;
      w_strb <= '0;
      ar_addr <= '0;
      ar_prot <= '0;
      BVALID <= 0;
      BRESP <= '0;
      RVALID <= 0;
      RRESP <= '0;
      RDATA <= '0;
      prefer_write <= 1;
      apb_addr <= '0;
      apb_data <= '0;
      apb_strb <= '0;
      apb_prot <= '0;
      apb_write <= 0;
    end else begin
      if (AWVALID && AWREADY) begin
        have_aw <= 1;
        aw_addr <= AWADDR;
        aw_prot <= AWPROT;
      end
      if (WVALID && WREADY) begin
        have_w <= 1;
        w_data <= WDATA;
        w_strb <= WSTRB;
      end
      if (ARVALID && ARREADY) begin
        have_ar <= 1;
        ar_addr <= ARADDR;
        ar_prot <= ARPROT;
      end
      if (BVALID && BREADY) BVALID <= 0;
      if (RVALID && RREADY) RVALID <= 0;
      case (state)
        IDLE: begin
          if (write_pending && (!read_pending || prefer_write)) begin
            have_aw <= 0;
            have_w <= 0;
            prefer_write <= 0;
            if (aw_addr[31:16] != 0 || aw_addr[1:0] != 0) begin
              BVALID <= 1;
              BRESP <= 2'b11;
            end else if (w_strb == 0) begin
              BVALID <= 1;
              BRESP <= 2'b00;
            end else begin
              apb_addr <= aw_addr[15:0];
              apb_data <= w_data;
              apb_strb <= w_strb;
              apb_prot <= aw_prot;
              apb_write <= 1;
              state <= SETUP;
            end
          end else if (read_pending) begin
            have_ar <= 0;
            prefer_write <= 1;
            if (ar_addr[31:16] != 0 || ar_addr[1:0] != 0) begin
              RVALID <= 1;
              RRESP <= 2'b11;
              RDATA <= 0;
            end else begin
              apb_addr <= ar_addr[15:0];
              apb_data <= 0;
              apb_strb <= 0;
              apb_prot <= ar_prot;
              apb_write <= 0;
              state <= SETUP;
            end
          end
        end
        SETUP: state <= ACCESS;
        ACCESS: if (PREADY) begin
          state <= IDLE;
          if (apb_write) begin
            BVALID <= 1;
            BRESP <= PSLVERR ? 2'b10 : 2'b00;
          end else begin
            RVALID <= 1;
            RRESP <= PSLVERR ? 2'b10 : 2'b00;
            RDATA <= PSLVERR ? 0 : PRDATA;
          end
        end
        default: state <= IDLE;
      endcase
    end
  end
endmodule
