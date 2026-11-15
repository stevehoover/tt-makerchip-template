\m5_TLV_version 1d --inlineGen --debugSigsYosys --fmtFlatSignals: tl-x.org
\m5
   /**
   This template is for developing Tiny Tapeout designs using Makerchip.
   Verilog, SystemVerilog, and/or TL-Verilog can be used.
   Use of Tiny Tapeout Demo Boards (as virtualized in the VIZ tab) is supported.
   See the corresponding Git repository for build instructions.
   **/

   use(m5-1.0)  // See M5 docs in Makerchip IDE Learn menu.

   // ---SETTINGS---
   var(my_design, tt_um_example)  /// Change tt_um_example to tt_um_<your-github-username>_<name-of-your-project>. (See README.md.)
   var(target, ASIC) /// Use "FPGA" for TT03 Demo Boards (without bidirectional I/Os).
   var(in_fpga, 1)   /// 1 to include the demo board visualization. (Note: Logic will be under /fpga_pins/fpga.)
   var(vga, 0)       /// 1 for a VGA design on the Tiny VGA Pmod (uo_out): drive R, G and B (all [1:0]; see tt_vga() in tiny_tapeout_lib.tlv)
                     /// Enables VGA features in Makerchip.
   var(vga_makerchip_scale, 1)
                     /// In Makerchip only, divide the VGA timing by this (e.g. 8 for 80x60), so whole frames fit in the
                     /// simulation (and its VIZ). Makerchip's TT VGA view then shows the small frame too.
   var(gamepad, 0)   /// 1 or 2: controllers on the Gamepad Pmod (ui_in[6:4]); read gamepad_up, etc. (see tt_gamepad()).
   var(debounce_inputs, 0)
                     /// Legal values:
                     ///   1: Provide synchronization and debouncing on all input signals.
                     ///   0: Don't provide synchronization and debouncing.
                     ///   m5_if_defined_as(MAKERCHIP, 1, 0, 1): Debounce unless in Makerchip.
   // --------------

   // If debouncing, your top module is wrapped within a debouncing module, so it has a different name.
   var(user_module_name, m5_if(m5_debounce_inputs, my_design, m5_my_design))
   var(debounce_cnt, m5_if_defined_as(MAKERCHIP, 1, 8'h03, 8'hff))
   // No TT lab outside of Makerchip.
   if_defined_as(MAKERCHIP, 1, [''], ['m5_set(in_fpga, 0)'])
   var(vga_scale, m5_if_defined_as(MAKERCHIP, 1, m5_vga_makerchip_scale, 1))  // (Read by the library.)
\SV
   // Include Tiny Tapeout Lab.
   m4_include_lib(['https://raw.githubusercontent.com/os-fpga/Virtual-FPGA-Lab/f18361f1ebbf39c6a910cfcee7b40bc1979360fd/tlv_lib/tiny_tapeout_lib.tlv'])

// Your design, in scope /_top (/fpga, in the TT demo board's FPGA, or /top), with the VGA and gamepad support its
// settings ask for.
\TLV my_design(/_top)
   m5_if(m5_vga, ['m5+tt_vga(0)'])  // 0: the pixel latency (see tt_vga()).
   m5_if(m5_gamepad, ['m5+tt_gamepad(/_top, m5_gamepad)'])

   //   #####  #            #   #      #   #  #####  ####   #####
   //     #    #            #   #      #   #  #      #   #  #
   //     #    #      ###   #   #      #####  ####   ####   ####
   //     #    #             # #       #   #  #      #  #   #
   //     #    #####          #        #   #  #####  #   #  #####
   //
   // Your TL-Verilog logic, if any, and optionally \viz_js (for TL-Verilog or Verilog logic), which overlays the
   // demo board's FPGA chip. Inputs: *ui_in[7:0], *uio_in[7:0] (the bits where uio_oe[7:0] is 0). From deeper
   // scopes, reach this one's signals as /_top$sig.



   /*
   // Connect Tiny Tapeout outputs
   // Uncomment outputs here, and comment/delete them at the end of this file.
   m5_if(m5_vga, ['// (uo_out is driven by tt_vga().)'], ['*uo_out = 8'b0;'])
   *uio_out = 8'b0;
   *uio_oe = 8'b0;
   */


// Set up the Tiny Tapeout lab environment.
\TLV tt_lab()
   /* verilator lint_off UNOPTFLAT */
   // Connect Tiny Tapeout I/Os to Virtual FPGA Lab.
   m5+tt_connections()

   // Instantiate the Virtual FPGA Lab.
   m5+board(/top, /fpga, 7, $, , my_design)
   // Label the switch inputs [0..7] (1..8 on the physical switch panel) (bottom-to-top).
   m5+tt_input_labels_viz(['"UNUSED", "UNUSED", "UNUSED", "UNUSED", "UNUSED", "UNUSED", "UNUSED", "UNUSED"'])

\SV


// ================================================
// A simple Makerchip Verilog test bench driving random stimulus.
// Modify the module contents to your needs.
// Only Makerchip's simulation defines MAKERCHIP, so other tools compiling this file (e.g. VGA Playground) skip it.
// ================================================

`ifdef MAKERCHIP
module top(input logic clk, input logic reset, input logic [31:0] cyc_cnt, output logic passed, output logic failed);
   // Tiny tapeout I/O signals.
   logic [7:0] ui_in, uio_in, uo_out, uio_out, uio_oe;
   logic [31:0] r;
   always @(posedge clk) r <= m5_if_defined_as(MAKERCHIP, 1, ['$urandom()'], ['0']);
   assign ui_in = r[7:0];
   assign uio_in = r[15:8];
   wire ena = 1'b1;  // High while the design is selected.
   wire rst_n = ! reset;

   /*
   // Or, to provide specific inputs at specific times...
   // BE SURE TO COMMENT THE ASSIGNMENT OF INPUTS ABOVE.
   // BE SURE TO DRIVE THESE ON THE B-PHASE OF THE CLOCK (ODD STEPS).
   // Driving on the rising clock edge creates a race with the clock that has unpredictable simulation behavior.
   initial begin
      #1  // Drive inputs on the B-phase.
         ui_in = 8'h0;
      #10 // Step past reset.
         ui_in = 8'hFF;
      // ...etc.
   end
   */

   // Instantiate the Tiny Tapeout module.
   m5_my_design tt(.*);

   assign passed = m5_if(m5_vga, ['cyc_cnt > m5_vga_sim_cycles'], ['cyc_cnt > 100']);
   assign failed = 1'b0;
endmodule
`endif

// Provide a wrapper module to debounce input signals if requested.
// TODO: The debounce module is conditioned for TT03.
m5_if(m5_debounce_inputs, ['m5_tt_top(m5_my_design)'])
// The above macro expands to multiple lines. We enter a new \SV block to reset line tracking.
\SV



// The Tiny Tapeout module.
module m5_user_module_name (
    input  wire [7:0] ui_in,    // Dedicated inputs - connected to the input switches
    output wire [7:0] uo_out,   // Dedicated outputs - connected to the 7 segment display
    input  wire [7:0] uio_in,   // IOs: Bidirectional Input path
    output wire [7:0] uio_out,  // IOs: Bidirectional Output path
    output wire [7:0] uio_oe,   // IOs: Bidirectional Enable path (active high: 0=input, 1=output)
    input  wire       ena,      // will go high when the design is enabled
    input  wire       clk,      // clock
    input  wire       rst_n     // reset_n - low to reset
);

   wire reset = ! rst_n;

   // List all potentially-unused inputs to prevent warnings
   (* keep *) wire _unused = &{ena, clk, reset, ui_in, uio_in, 1'b1};

\TLV
   m5_if(m5_in_fpga, ['m5+tt_lab()'], ['m5+my_design(/top)'])
   m5_if(m5_vga, ['m5+tt_vga_viz()'])

\SV_plus

   //   #   #  #####  ####   ###  #       ###    ####      #   #  #####  ####   #####
   //   #   #  #      #   #   #   #      #   #  #          #   #  #      #   #  #
   //   #   #  ####   ####    #   #      #   #  #  ##      #####  ####   ####   ####
   //    # #   #      #  #    #   #      #   #  #   #      #   #  #      #  #   #
   //     #    #####  #   #  ###  #####   ###    ####      #   #  #####  #   #  #####
   //
   // Your (System)Verilog logic, if any. (Module interface above.)



   // Connect Tiny Tapeout outputs
   m5_if(m5_vga, ['// (uo_out is driven by tt_vga().)'], ['assign uo_out = 8'b0;'])
   assign uio_out = 8'b0;
   assign uio_oe = 8'b0;

endmodule
