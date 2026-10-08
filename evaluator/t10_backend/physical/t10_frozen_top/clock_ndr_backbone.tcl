# Physical A/B candidate: wide M6/M7 backbone and normal-width local branches.
# The previous blanket NDR produced repeated global-router soft-NDR retries.
# Keep explicit long trunks, macro input branches and upper CTS levels wide.
set block [ord::get_db_block]
set changed 0
set kept 0
set fp [open $::env(REPORTS_DIR)/t10_clock_ndr_policy.tsv w]
puts $fp "net\tpolicy\treason"
foreach net [$block getNets] {
    if {[$net getNonDefaultRule] eq "NULL"} { continue }
    if {[$net getSigType] ne "CLOCK"} { continue }
    set name [$net getName]
    set reason local_branch
    set wide 0
    if {$name eq "clk" || [string match t10_clk_source_trunk* $name] ||
        [string match t10_macro_clk_chain* $name] ||
        [string match t10_clk_channel_repair_* $name] ||
        [string match t10_top_clock_* $name]} {
        set wide 1
        set reason explicit_backbone
    }
    if {[regexp {^clknet_([0-9]+)_} $name -> level] && $level <= 3} {
        set wide 1
        set reason upper_cts
    }
    foreach pin [$net getITerms] {
        if {[[$pin getInst] getMaster] eq "NULL"} { continue }
        if {[[[$pin getInst] getMaster] isBlock] && [[$pin getMTerm] getSigType] eq "CLOCK"} {
            set wide 1
            set reason macro_clock_input
        }
    }
    if {$wide} {
        incr kept
        puts $fp "$name\twide_M6_M7\t$reason"
    } else {
        $net setNonDefaultRule NULL
        incr changed
        puts $fp "$name\tnormal_M6_M7\t$reason"
    }
}
close $fp
if {$changed == 0 || $kept == 0} { error "Clock NDR policy did not select both path classes" }
puts "T10_CLOCK_NDR_POLICY wide_backbone=$kept normal_local=$changed clock_layers=M6-M7"
