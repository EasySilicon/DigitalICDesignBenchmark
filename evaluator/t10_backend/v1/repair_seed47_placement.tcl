# Exact local repair of the one measured seed47 fence violation. No search,
# region relaxation, legalization rerun, cell replacement or logic change.
source $::env(SCRIPTS_DIR)/load.tcl
load_design 3_5_place_dp-failed.odb 2_floorplan.sdc
set block [ord::get_db_block]
set target {at_out_payload\[4\]$_DFF_PN0_}
set cell [$block findInst $target]
if {$cell == "NULL" || [[$cell getMaster] getName] ne "DFFASRHQNx1_ASAP7_75t_R" ||
    [$cell getLocation] ne {444960 245700} || [$cell getOrient] ne "MY"} {
    error "unexpected failed placement; do not apply this seed-specific repair"
}
set region [[[$cell getGroup] getRegion] getName]
if {$region ne "t10_a_forward_boundary"} { error "unexpected placement region" }
proc snapshot {block} {
    set rows [dict create]
    foreach inst [$block getInsts] {
        set connections {}
        foreach terminal [$inst getITerms] {
            set net [$terminal getNet]
            lappend connections [list [[$terminal getMTerm] getName] \
                [expr {$net eq "NULL" ? "NULL" : [$net getName]}]]
        }
        dict set rows [$inst getName] [list [[$inst getMaster] getName] \
            [$inst getLocation] [$inst getOrient] [$inst getPlacementStatus] $connections]
    }
    return $rows
}
set before [snapshot $block]
# 54 DBU is one site; 540 DBU is two rows, retaining the legal orientation.
# The destination row has no overlapping cell, and is inside the same fence.
$cell setLocation 445014 246240
set after [snapshot $block]
set expected [dict get $before $target]
lset expected 1 {445014 246240}
dict set before $target $expected
if {$before ne $after} { error "repair changed another placement/master/connection" }
set_placement_padding -global -left $::env(CELL_PAD_IN_SITES_DETAIL_PLACEMENT) \
    -right $::env(CELL_PAD_IN_SITES_DETAIL_PLACEMENT)
check_placement -verbose
puts "T10_MANUAL_PLACEMENT_PASS one_cell_only all_instances_and_connections_checked=[dict size $after]"
estimate_parasitics -placement
report_metrics 3 "manual detailed-place fence repair" true false
orfs_write_db $::env(RESULTS_DIR)/3_5_place_dp.odb
orfs_write_sdc $::env(RESULTS_DIR)/3_place.sdc
