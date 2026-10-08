# Source after detailed-route extraction, while the OpenDB RSegs are live.
# Reports actual clock-net layer use without trusting global-route guides.
if {![info exists ::env(REPORTS_DIR)]} {
    error "REPORTS_DIR is required for the T10 clock route audit"
}
set block [ord::get_db_block]
set dbu [$block getDbUnitsPerMicron]
array set wire_len_um {}
array set segment_count {}
set clock_nets 0
set clock_vias 0
set clock_segments 0
foreach net [$block getNets] {
    if {[$net getSigType] ne "CLOCK"} {
        continue
    }
    set wire [$net getWire]
    if {$wire eq "NULL"} {
        continue
    }
    incr clock_nets
    foreach rseg [$net getRSegs] {
        set shape [$wire getShape [$rseg getShapeId]]
        if {![$shape isSegment]} {
            incr clock_vias
            continue
        }
        set layer [[$shape getTechLayer] getName]
        set span_um [expr {double(max([$shape getDX], [$shape getDY])) / $dbu}]
        if {![info exists wire_len_um($layer)]} {
            set wire_len_um($layer) 0.0
            set segment_count($layer) 0
        }
        set wire_len_um($layer) [expr {$wire_len_um($layer) + $span_um}]
        incr segment_count($layer)
        incr clock_segments
    }
}
if {$clock_nets == 0 || $clock_segments == 0} {
    error "no extracted CLOCK-net routed segments available for audit"
}
set output [file join $::env(REPORTS_DIR) t10_clock_route_audit.tsv]
set handle [open $output w]
puts $handle "metric\tvalue"
puts $handle "clock_nets\t$clock_nets"
puts $handle "clock_segments\t$clock_segments"
puts $handle "clock_via_shapes\t$clock_vias"
puts $handle "layer\tsegment_count\tbbox_span_um"
foreach layer [lsort -dictionary [array names wire_len_um]] {
    puts $handle "$layer\t$segment_count($layer)\t[format %.3f $wire_len_um($layer)]"
}
close $handle
puts "T10 clock route audit: $clock_nets nets, $clock_segments segments, $clock_vias via shapes -> $output"
