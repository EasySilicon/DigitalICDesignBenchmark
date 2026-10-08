# Diagnostic-only checkpointing. Preserve real pin access, nets and capacities.
if {![info exists ::env(T10_REFERENCE_GRID_PROBE)] || $::env(T10_REFERENCE_GRID_PROBE) ne "1"} {
    error "This checkpoint hook requires an explicitly labeled grid probe"
}
set t10_gcell_dbu [[ord::get_db_block] getGCellTileSize]
if {$t10_gcell_dbu != $::env(T10_EXPECT_GCELL_DBU)} {
    error "Unexpected GCell size: $t10_gcell_dbu"
}
puts "T10_GRID_PROBE diagnostic_only=1 gcell_dbu=$t10_gcell_dbu track_grids_unmodified=1"
if {[info exists ::env(T10_CLOCK_NDR_POLICY)] && $::env(T10_CLOCK_NDR_POLICY) eq "backbone_only"} {
    source [file join $::env(T10_BACKEND_ROOT) physical t10_frozen_top/clock_ndr_backbone.tcl]
}

rename pin_access t10_native_pin_access
proc pin_access {args} {
    if {[info exists ::env(T10_RESUME_VERIFIED_PIN_ACCESS)] && $::env(T10_RESUME_VERIFIED_PIN_ACCESS) eq "1"} {
        # The launcher verifies exact checkpoint hashes, native PA completion,
        # zero missing-access counts and unchanged placement before this path.
        if {![file isfile $::env(RESULTS_DIR)/verified_pin_access_resume.json]} {
            error "Missing verified PA resume provenance"
        }
        puts "T10_PIN_ACCESS_RESUME verified_native_checkpoint=1"
        return
    }
    # A native failure throws before any successful checkpoint is emitted.
    set result [t10_native_pin_access {*}$args]
    set checkpoint $::env(RESULTS_DIR)/4_cts_pin_access.odb
    write_db ${checkpoint}.pending
    file rename -force ${checkpoint}.pending $checkpoint
    orfs_write_sdc $::env(RESULTS_DIR)/4_cts_pin_access.sdc
    set fp [open $::env(RESULTS_DIR)/4_cts_pin_access.receipt w]
    puts $fp "native_pin_access_completed=1"
    puts $fp "gcell_dbu=[[ord::get_db_block] getGCellTileSize]"
    puts $fp "instance_count=[llength [[ord::get_db_block] getInsts]]"
    close $fp
    puts "T10_PIN_ACCESS_CHECKPOINT $checkpoint"
    if {[info exists ::env(T10_PROBE_STOP_AFTER_PIN_ACCESS)] && $::env(T10_PROBE_STOP_AFTER_PIN_ACCESS) eq "1"} {
        puts "T10_PIN_ACCESS_ONLY_COMPLETE route_not_started=1"
        exit 0
    }
    return $result
}

rename global_route t10_native_global_route
proc global_route {args} {
    if {[info exists ::env(T10_PROBE_CONGESTION_ITERATIONS)] &&
        [lsearch -exact $args -start_incremental] < 0 &&
        [lsearch -exact $args -end_incremental] < 0} {
        set index [lsearch -exact $args -congestion_iterations]
        if {$index >= 0} {
            set args [lreplace $args [expr {$index + 1}] [expr {$index + 1}] $::env(T10_PROBE_CONGESTION_ITERATIONS)]
        }
        # Diagnostics retain and report overflow; none qualify a baseline.
        if {[lsearch -exact $args -allow_congestion] < 0} { lappend args -allow_congestion }
        puts "T10_DIAGNOSTIC_ROUTE_ARGS $args"
    }
    set result [t10_native_global_route {*}$args]
    if {[lsearch -exact $args -start_incremental] < 0 && [lsearch -exact $args -end_incremental] < 0} {
        set checkpoint $::env(RESULTS_DIR)/5_global_route_topology.odb
        write_db ${checkpoint}.pending
        file rename -force ${checkpoint}.pending $checkpoint
        write_guides $::env(RESULTS_DIR)/route_topology.guide
        write_global_route_segments $::env(RESULTS_DIR)/route_topology.segments
        puts "T10_GLOBAL_ROUTE_CHECKPOINT $checkpoint"
    }
    return $result
}
