# Keep each row's result pipeline and quarter bank in the routing channel
# immediately below its PE row.  The systolic forwarding registers live in
# the routed PE macros, so the 100 um macro channels carry only the short
# PE-output-to-next-PE-input links; no duplicate shell forwarding banks are
# created or constrained here.
set block [ord::get_db_block]
set dbu [$block getDbUnitsPerMicron]
set y_bounds {
    {1794.0 1892.8}
    {1200.5 1299.3}
    {607.0 705.8}
    {0.54 112.3}
}
set x_bounds {
    {113.0 333.0}
    {706.5 926.5}
    {1573.0 1793.0}
    {2166.5 2386.5}
}

set cell_groups {}
for {set row 0} {$row < 4} {incr row} {
    set stale_name t10_result_row_$row
    set stale_group [$block findGroup $stale_name]
    if {$stale_group ne "NULL"} { odb::dbGroup_destroy $stale_group }
    set stale_region [$block findRegion $stale_name]
    if {$stale_region ne "NULL"} { odb::dbRegion_destroy $stale_region }

    lassign [lindex $y_bounds $row] y0 y1
    set row_groups {}
    for {set col 0} {$col < 4} {incr col} {
        set name t10_result_cell_${row}_${col}
        set previous_group [$block findGroup $name]
        if {$previous_group ne "NULL"} { odb::dbGroup_destroy $previous_group }
        set previous_region [$block findRegion $name]
        if {$previous_region ne "NULL"} { odb::dbRegion_destroy $previous_region }

        set region [odb::dbRegion_create $block $name]
        odb::dbRegion_setRegionType $region INCLUSIVE
        lassign [lindex $x_bounds $col] x0 x1
        odb::dbBox_create $region \
            [expr {round($x0 * $dbu)}] [expr {round($y0 * $dbu)}] \
            [expr {round($x1 * $dbu)}] [expr {round($y1 * $dbu)}]
        set group [odb::dbGroup_create $block $name]
        odb::dbGroup_setType $group PHYSICAL_CLUSTER
        odb::dbRegion_addGroup $region $group
        lappend row_groups $group
    }
    lappend cell_groups $row_groups
}

set row_counts {0 0 0 0}
set cell_counts [lrepeat 4 {0 0 0 0}]
set duplicate_forward_flops 0
foreach inst [$block getInsts] {
    set normalized [$inst getName]
    regsub -all {\\} $normalized {} normalized
    if {[regexp {^result_row\[([0-3])\]\.} $normalized -> row]} {
        if {[regexp {^result_row\[([0-3])\]\.(?:bank/cell_bank|result_cell)\[([0-3])\]\.} \
                $normalized -> row col]} {
            odb::dbGroup_addInst [lindex [lindex $cell_groups $row] $col] $inst
            set counts [lindex $cell_counts $row]
            lset counts $col [expr {[lindex $counts $col] + 1}]
            lset cell_counts $row $counts
        }
        lset row_counts $row [expr {[lindex $row_counts $row] + 1}]
    }
    if {[regexp {^(a|at|b|bt)_forward\[[0-9]+\]\[[0-9]+\]\$_DFF} $normalized]} {
        incr duplicate_forward_flops
    }
}

if {$duplicate_forward_flops != 0} {
    error "T10 direct-mesh tile unexpectedly contains $duplicate_forward_flops duplicate shell forwarding flops"
}
for {set row 0} {$row < 4} {incr row} {
    if {[lindex $row_counts $row] < 1000} {
        error "T10 result row $row captured only [lindex $row_counts $row] instances"
    }
    puts "T10_RESULT_REGION row=$row instances=[lindex $row_counts $row] bounds=[lindex $y_bounds $row]"
    for {set col 0} {$col < 4} {incr col} {
        set count [lindex [lindex $cell_counts $row] $col]
        if {$count < 500} {
            error "T10 result cell $row,$col captured only $count instances"
        }
        puts "T10_RESULT_CELL_REGION row=$row col=$col instances=$count"
    }
}
puts "T10_DIRECT_MESH_REGIONS duplicate_forward_flops=$duplicate_forward_flops"
