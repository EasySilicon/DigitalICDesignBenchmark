# The placement regions are guidance for global placement.  OpenROAD's
# detailed placer scales poorly when tens of thousands of cells retain fence
# membership, so release the groups after their compact coordinates are fixed.
set block [ord::get_db_block]
set removed_groups 0
set removed_regions 0
for {set row 0} {$row < 4} {incr row} {
    foreach name [list t10_result_row_$row] {
        set group [$block findGroup $name]
        if {$group ne "NULL"} { odb::dbGroup_destroy $group; incr removed_groups }
        set region [$block findRegion $name]
        if {$region ne "NULL"} { odb::dbRegion_destroy $region; incr removed_regions }
    }
    for {set col 0} {$col < 4} {incr col} {
        foreach name [list \
                t10_result_cell_${row}_${col} \
                t10_forward_a_${row}_${col} \
                t10_forward_b_${row}_${col}] {
            set group [$block findGroup $name]
            if {$group ne "NULL"} { odb::dbGroup_destroy $group; incr removed_groups }
            set region [$block findRegion $name]
            if {$region ne "NULL"} { odb::dbRegion_destroy $region; incr removed_regions }
        }
    }
}
puts "T10_RELEASE_PLACEMENT_GUIDES groups=$removed_groups regions=$removed_regions"
