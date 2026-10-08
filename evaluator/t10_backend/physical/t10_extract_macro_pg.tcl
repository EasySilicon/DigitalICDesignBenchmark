# ODB_INPUT and PG_OUTPUT are supplied by the caller. Use the routed final
# database so the abstract exposes physically present M8 power wires.
read_db $::env(ODB_INPUT)
set block [ord::get_db_block]
set dbu [[ord::get_db_tech] getDbUnitsPerMicron]
set fp [open $::env(PG_OUTPUT) w]
foreach netname {VDD VSS} {
    set net [$block findNet $netname]
    if {$net eq "NULL"} { error "Missing $netname net" }
    foreach sw [$net getSWires] {
        foreach box [$sw getWires] {
            if {[$box isVia]} { continue }
            if {[[$box getTechLayer] getName] ne "M8"} { continue }
            puts $fp "$netname [expr {double([$box xMin]) / $dbu}] [expr {double([$box yMin]) / $dbu}] [expr {double([$box xMax]) / $dbu}] [expr {double([$box yMax]) / $dbu}]"
        }
    }
}
close $fp
