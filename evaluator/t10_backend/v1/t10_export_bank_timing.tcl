# Export a routed ASAP7 macro timing view from the exact final ODB/SPEF.
# Set TIMING_EXTRA_LIBS to a Tcl list of Liberty paths for any child macros.
foreach variable {ASAP7_PLATFORM ODB_INPUT SDC_INPUT SPEF_INPUT LIB_OUTPUT} {
    if {![info exists ::env($variable)] || $::env($variable) eq ""} {
        error "missing environment variable $variable"
    }
}
set lib_dir [file join $::env(ASAP7_PLATFORM) lib NLDM]
foreach lib {
    asap7sc7p5t_AO_RVT_SS_nldm_211120.lib.gz
    asap7sc7p5t_INVBUF_RVT_SS_nldm_220122.lib.gz
    asap7sc7p5t_OA_RVT_SS_nldm_211120.lib.gz
    asap7sc7p5t_SEQ_RVT_SS_nldm_220123.lib
    asap7sc7p5t_SIMPLE_RVT_SS_nldm_211120.lib.gz
} {
    read_liberty [file join $lib_dir $lib]
}
if {[info exists ::env(TIMING_EXTRA_LIBS)] && $::env(TIMING_EXTRA_LIBS) ne ""} {
    foreach lib $::env(TIMING_EXTRA_LIBS) {
        if {![file isfile $lib]} {
            error "missing timing macro Liberty $lib"
        }
        read_liberty $lib
    }
}
read_db $::env(ODB_INPUT)
read_sdc $::env(SDC_INPUT)
source [file join $::env(ASAP7_PLATFORM) setRC.tcl]
read_spef $::env(SPEF_INPUT)
report_worst_slack -max
report_worst_slack -min
# A parent block builds its own clock tree.  Remove leaf source latency before
# characterization so hierarchical STA does not count it a second time.
set_clock_latency -source 0 [all_clocks]
write_timing_model $::env(LIB_OUTPUT)
