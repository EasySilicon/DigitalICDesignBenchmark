# Keep the 64-bit systolic forwarding registers near the PE boundaries they
# drive.  The external timing budget is 200 ps, so unconstrained placement in
# the macro interior leaves an avoidable 300-450 um boundary wire.
set block [ord::get_db_block]
set a_region [$block findRegion t10_a_forward_boundary]
set b_region [$block findRegion t10_b_forward_boundary]

# This hook is used for both global-placement passes.  The first pass creates
# the regions and they persist through IO placement into the second pass.
if {$a_region != "NULL" || $b_region != "NULL"} {
    if {$a_region == "NULL" || $b_region == "NULL"} {
        error "T10 forwarding region state is incomplete"
    }
    puts "T10_FORWARD_REGIONS reuse"
    return
}

source /home/reefshark/research/agent_os/ic_bcmk_eval_private/physical/t10_pe_pin_escape_soft_plus_blockages.tcl

# Coordinates are in database units (1000 DBU/um).  Both fences avoid the
# fixed child macros while leaving ample legalization and clock-routing room.
set a_region [odb::dbRegion_create $block t10_a_forward_boundary]
$a_region setRegionType INCLUSIVE
odb::dbBox_create $a_region 445000 540 488430 488430
set a_group [odb::dbGroup_create $a_region t10_a_forward_cells]
$a_group setType PHYSICAL_CLUSTER

set b_region [odb::dbRegion_create $block t10_b_forward_boundary]
$b_region setRegionType INCLUSIVE
odb::dbBox_create $b_region 540 540 488430 45000
set b_group [odb::dbGroup_create $b_region t10_b_forward_cells]
$b_group setType PHYSICAL_CLUSTER

set a_count 0
set b_count 0
foreach inst [$block getInsts] {
    set master_name [[$inst getMaster] getName]
    if {![string match {DFF*} $master_name]} { continue }
    set inst_name [$inst getName]
    if {[string match {a_out_n*} $inst_name] ||
        [string match {at_out_payload*} $inst_name] ||
        [string match {at_out_valid_n*} $inst_name]} {
        $a_group addInst $inst
        incr a_count
    } elseif {[string match {b_out_n*} $inst_name] ||
              [string match {bt_out_payload*} $inst_name] ||
              [string match {bt_out_valid_n*} $inst_name]} {
        $b_group addInst $inst
        incr b_count
    }
}
if {$a_count != 92 || $b_count != 92} {
    error "T10 forwarding register count mismatch: a=$a_count b=$b_count"
}
puts "T10_FORWARD_REGIONS created grouped_a=$a_count grouped_b=$b_count"
