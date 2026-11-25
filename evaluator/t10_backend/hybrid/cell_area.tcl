# One area definition for both routed PE and integrated shell. Keep taps,
# clock cells and repair cells; exclude only cells marked as fillers by OpenDB.
proc t10_is_filler_cell {cell} {
    if {![llength [info commands ord::get_db_block]]} { return 0 }
    set physical [[ord::get_db_block] findInst [get_full_name $cell]]
    return [expr {$physical ne "NULL" && [[$physical getMaster] isFiller]}]
}

proc t10_is_physical_only_cell {cell} {
    if {![llength [info commands ord::get_db_block]]} { return 0 }
    set physical [[ord::get_db_block] findInst [get_full_name $cell]]
    if {$physical eq "NULL"} { return 0 }
    foreach terminal [[$physical getMaster] getMTerms] {
        if {[$terminal getSigType] ni {POWER GROUND}} { return 0 }
    }
    return 1
}

proc t10_cell_area {block excluded_macros} {
    set dbu [$block getDbUnitsPerMicron]
    set area 0.0
    set filler_area 0.0
    set macro_count 0
    set macro_area 0.0
    foreach inst [$block getInsts] {
        set master [$inst getMaster]
        set value [expr {double([$master getWidth])*[$master getHeight]/$dbu/$dbu}]
        if {[lsearch -exact $excluded_macros [$master getName]] >= 0} {
            incr macro_count
            set macro_area [expr {$macro_area+$value}]
            continue
        }
        if {[$master isBlock]} { error "unaccounted nested macro [$master getName]" }
        if {[$master isFiller]} {
            set filler_area [expr {$filler_area+$value}]
        } else {
            set area [expr {$area+$value}]
        }
    }
    return [dict create area_um2 $area filler_area_um2 $filler_area macro_count $macro_count macro_area_um2 $macro_area]
}
