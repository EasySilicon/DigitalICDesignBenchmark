# Exact-name lookup, not glob matching. This avoids treating literal bus
# brackets as patterns or slash-bearing flat names as hierarchy separators.
set activities [dict create]
set stream [open $::env(T10_ACTIVITY_NETS) r]
while {[gets $stream line] >= 0} {
    if {[llength $line] != 3} { error "invalid SAIF net activity row" }
    lassign $line name density duty
    if {[dict exists $activities $name]} { error "duplicate activity net: $name" }
    dict set activities $name [list $density $duty]
}
close $stream
set found [dict create]
set annotated_pins [dict create]
set pins_annotated 0
set absent 0
foreach net [get_nets -hierarchical *] {
    set name [string map {\\ ""} [get_full_name $net]]
    if {![dict exists $activities $name]} {
        if {$name ni {VDD VSS}} { error "physical signal net lacks SAIF activity: $name" }
        incr absent
        continue
    }
    if {[dict exists $found $name]} { error "ambiguous physical net: $name" }
    dict set found $name 1
    lassign [dict get $activities $name] density duty
    foreach pin [get_pins -of_objects $net] {
        # Identical SI density/duty convention to SaifReader::setNetDurations.
        sta::set_power_pin_activity $pin $density $duty
        dict set annotated_pins $pin 1
        incr pins_annotated
    }
}
if {[dict size $found] != [dict size $activities]} {
    set missing {}
    dict for {name value} $activities {
        if {![dict exists $found $name]} { lappend missing $name }
    }
    error "SAIF nets absent from physical design: $missing"
}
puts "T10_ACTIVITY_IMPORT nets=[dict size $found] pins=$pins_annotated physical_nets_without_activity=$absent"
set sequential_total 0
set sequential_annotated 0
foreach pin [get_pins -of_objects [all_registers -cells]] {
    incr sequential_total
    if {[dict exists $annotated_pins $pin]} { incr sequential_annotated }
}
if {$sequential_total == 0 || double($sequential_annotated)/$sequential_total < 0.95} {
    error "sequential SAIF annotation below 95%: $sequential_annotated/$sequential_total"
}
puts "T10_SEQUENTIAL_ACTIVITY annotated=$sequential_annotated total=$sequential_total"
