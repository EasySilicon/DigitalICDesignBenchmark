# Keep each row's result pipeline and quarter bank in the routing channel
# immediately below its PE row. Without these regions, global placement can
# spread one bank across the full 2.25 mm tile and make its write decoder and
# read mux wire dominated.
set block [ord::get_db_block]
set dbu [$block getDbUnitsPerMicron]
set y_bounds {
    {1794.0 1892.8}
    {1200.5 1299.3}
    {607.0 705.8}
    {0.54 112.3}
}
# Compact bank windows sit directly below their source PE.  A quarter-column
# window was still wide enough for the 16:1 read mux to become wire dominated;
# 220 um keeps the complete store and its result pipeline near one another.
set x_bounds {
    {113.0 333.0}
    {706.5 926.5}
    {1573.0 1793.0}
    {2166.5 2386.5}
}
set cell_regions {}
set cell_groups {}
for {set row 0} {$row < 4} {incr row} {
    # Remove any stale broad row fence from an incremental database.  Only
    # the non-overlapping per-cell fences are needed; overlapping row and cell
    # fences cannot be legalized reliably by detailed placement.
    set name t10_result_row_$row
    set previous_group [$block findGroup $name]
    if {$previous_group ne "NULL"} {
        odb::dbGroup_destroy $previous_group
    }
    set previous [$block findRegion $name]
    if {$previous ne "NULL"} {
        odb::dbRegion_destroy $previous
    }
    lassign [lindex $y_bounds $row] y0 y1
    set per_row {}
    set per_row_groups {}
    for {set col 0} {$col < 4} {incr col} {
        set cell_name t10_result_cell_${row}_${col}
        set previous_group [$block findGroup $cell_name]
        if {$previous_group ne "NULL"} {
            odb::dbGroup_destroy $previous_group
        }
        set previous [$block findRegion $cell_name]
        if {$previous ne "NULL"} {
            odb::dbRegion_destroy $previous
        }
        set cell_region [odb::dbRegion_create $block $cell_name]
        odb::dbRegion_setRegionType $cell_region INCLUSIVE
        lassign [lindex $x_bounds $col] x0 x1
        odb::dbBox_create $cell_region \
            [expr {round($x0 * $dbu)}] [expr {round($y0 * $dbu)}] \
            [expr {round($x1 * $dbu)}] [expr {round($y1 * $dbu)}]
        lappend per_row $cell_region
        set cell_group [odb::dbGroup_create $block $cell_name]
        odb::dbGroup_setType $cell_group PHYSICAL_CLUSTER
        odb::dbRegion_addGroup $cell_region $cell_group
        lappend per_row_groups $cell_group
    }
    lappend cell_regions $per_row
    lappend cell_groups $per_row_groups
}

# The tile shell owns one A/AT and one B/BT forwarding register bank per PE.
# A forward bank is physically placed at the next PE to the east, and a B
# forward bank at the next PE to the south; the final banks sit at the tile
# output edge.  These are launch registers for the following PE/tile, not
# ingress registers for the PE with the same array index.
set a_x_bounds {
    {680.0 706.4}
    {1273.5 1299.9}
    {1867.0 1893.4}
    {2387.0 2498.8}
}
set pe_y_bounds {
    {1893.6 2386.8}
    {1300.1 1793.3}
    {706.6 1199.8}
    {113.1 606.3}
}
set pe_x_bounds {
    {113.1 606.3}
    {706.6 1199.8}
    {1300.1 1793.3}
    {1893.6 2386.8}
}
set b_y_bounds {
    {1867.0 1892.4}
    {1273.5 1299.4}
    {680.0 705.9}
    {0.54 112.4}
}
set forward_a_groups {}
set forward_b_groups {}
for {set row 0} {$row < 4} {incr row} {
    set row_a_groups {}
    set row_b_groups {}
    for {set col 0} {$col < 4} {incr col} {
        set cell_index [expr {$row * 4 + $col}]
        set a_name t10_forward_a_${row}_${col}
        set b_name t10_forward_b_${row}_${col}
        foreach name [list $a_name $b_name] {
            set previous_group [$block findGroup $name]
            if {$previous_group ne "NULL"} { odb::dbGroup_destroy $previous_group }
            set previous [$block findRegion $name]
            if {$previous ne "NULL"} { odb::dbRegion_destroy $previous }
        }

        set a_region [odb::dbRegion_create $block $a_name]
        odb::dbRegion_setRegionType $a_region INCLUSIVE
        lassign [lindex $a_x_bounds $col] ax0 ax1
        lassign [lindex $pe_y_bounds $row] ay0 ay1
        odb::dbBox_create $a_region \
            [expr {round($ax0 * $dbu)}] [expr {round($ay0 * $dbu)}] \
            [expr {round($ax1 * $dbu)}] [expr {round($ay1 * $dbu)}]
        set a_group [odb::dbGroup_create $block $a_name]
        odb::dbGroup_setType $a_group PHYSICAL_CLUSTER
        odb::dbRegion_addGroup $a_region $a_group
        lappend row_a_groups $a_group

        set b_region [odb::dbRegion_create $block $b_name]
        odb::dbRegion_setRegionType $b_region INCLUSIVE
        lassign [lindex $pe_x_bounds $col] bx0 bx1
        lassign [lindex $b_y_bounds $row] by0 by1
        odb::dbBox_create $b_region \
            [expr {round($bx0 * $dbu)}] [expr {round($by0 * $dbu)}] \
            [expr {round($bx1 * $dbu)}] [expr {round($by1 * $dbu)}]
        set b_group [odb::dbGroup_create $block $b_name]
        odb::dbGroup_setType $b_group PHYSICAL_CLUSTER
        odb::dbRegion_addGroup $b_region $b_group
        lappend row_b_groups $b_group
    }
    lappend forward_a_groups $row_a_groups
    lappend forward_b_groups $row_b_groups
}

set counts {0 0 0 0}
set cell_counts {}
set forward_a_counts {}
set forward_b_counts {}
for {set row 0} {$row < 4} {incr row} {
    lappend cell_counts {0 0 0 0}
    lappend forward_a_counts {0 0 0 0}
    lappend forward_b_counts {0 0 0 0}
}
foreach inst [$block getInsts] {
    set normalized [$inst getName]
    regsub -all {\\} $normalized {} normalized
    set master_name [[$inst getMaster] getName]
    if {[regexp {^result_row\[([0-3])\]\.} $normalized -> row]} {
        if {[regexp {^result_row\[([0-3])\]\.(?:bank/cell_bank|result_cell)\[([0-3])\]\.} \
                $normalized -> row col]} {
            odb::dbGroup_addInst [lindex [lindex $cell_groups $row] $col] $inst
            set row_cell_counts [lindex $cell_counts $row]
            lset row_cell_counts $col [expr {[lindex $row_cell_counts $col] + 1}]
            lset cell_counts $row $row_cell_counts
        }
        lset counts $row [expr {[lindex $counts $row] + 1}]
    }
    if {[string match {DFF*} $master_name] && \
        [regexp {^(a|at)_forward\[([0-9]+)\]\[[0-9]+\]} \
            $normalized -> signal cell_index]} {
        set row [expr {$cell_index / 4}]
        set col [expr {$cell_index % 4}]
        odb::dbGroup_addInst [lindex [lindex $forward_a_groups $row] $col] $inst
        set row_counts [lindex $forward_a_counts $row]
        lset row_counts $col [expr {[lindex $row_counts $col] + 1}]
        lset forward_a_counts $row $row_counts
    } elseif {[string match {DFF*} $master_name] && \
              [regexp {^(b|bt)_forward\[([0-9]+)\]\[[0-9]+\]} \
            $normalized -> signal cell_index]} {
        set row [expr {$cell_index / 4}]
        set col [expr {$cell_index % 4}]
        odb::dbGroup_addInst [lindex [lindex $forward_b_groups $row] $col] $inst
        set row_counts [lindex $forward_b_counts $row]
        lset row_counts $col [expr {[lindex $row_counts $col] + 1}]
        lset forward_b_counts $row $row_counts
    }
}
for {set row 0} {$row < 4} {incr row} {
    if {[lindex $counts $row] < 1000} {
        error "T10 result row $row region captured only [lindex $counts $row] instances"
    }
    puts "T10_RESULT_REGION row=$row instances=[lindex $counts $row] bounds=[lindex $y_bounds $row]"
    for {set col 0} {$col < 4} {incr col} {
        set count [lindex [lindex $cell_counts $row] $col]
        if {$count < 500} {
            error "T10 result cell $row,$col region captured only $count instances"
        }
        puts "T10_RESULT_CELL_REGION row=$row col=$col instances=$count"
        set a_count [lindex [lindex $forward_a_counts $row] $col]
        set b_count [lindex [lindex $forward_b_counts $row] $col]
        if {$a_count != 92 || $b_count != 92} {
            error "T10 forward region $row,$col expected 92 A and 92 B flops, found a=$a_count b=$b_count"
        }
        puts "T10_FORWARD_REGION row=$row col=$col a=$a_count b=$b_count"
    }
}
