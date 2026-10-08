# Fixed floorplan T10 PE: bridge clipped macro VSS straps and offset upper
# integer-group VDD rails.  Units are OpenDB units (1000 units/um); M8/M9 are
# used for power only.
if {[info exists ::env(T10_PG_INPUT_ODB)] && $::env(T10_PG_INPUT_ODB) ne ""} {
    read_db $::env(T10_PG_INPUT_ODB)
}
set block [ord::get_db_block]
set vss [$block findNet VSS]
if {$vss eq "NULL"} { error "VSS net is missing" }
set vss_sw [lindex [$vss getSWires] 0]
if {$vss_sw eq ""} { error "VSS special wire is missing" }
set db [ord::get_db]
set m8 [[$db getTech] findLayer M8]
set m9 [[$db getTech] findLayer M9]
set via [$block findVia via8_9_288_288_3_3_97_97]
if {$m8 eq "NULL" || $m9 eq "NULL" || $via eq "NULL"} {
    error "M8, M9, or M8/M9 PDN via is missing"
}
set vss_bridges {
    {55053 298400 301053}
    {217053 298350 301053}
    {368253 323400 326053}
    {368253 208400 211053}
}
foreach bridge $vss_bridges {
    lassign $bridge x ystart yvia
    set rect [odb::dbSBox_create $vss_sw $m9 \
      [expr {$x-144}] $ystart [expr {$x+144}] [expr {$yvia+147}] STRIPE]
    set cut [odb::dbSBox_create $vss_sw $via $x $yvia STRIPE]
    if {$rect eq "NULL" || $cut eq "NULL"} { error "failed to create VSS bridge $bridge" }
}

set vdd [$block findNet VDD]
if {$vdd eq "NULL"} { error "VDD net is missing" }
set vdd_sw [lindex [$vdd getSWires] 0]
if {$vdd_sw eq ""} { error "VDD special wire is missing" }
set vdd_bridges {
    {78450 82437 121293 121581 82293 121437}
    {114549 121437 121293 121581 114693 121437}
}
foreach bridge $vdd_bridges {
    lassign $bridge x0 x1 y0 y1 xvia yvia
    set rect [odb::dbSBox_create $vdd_sw $m8 $x0 $y0 $x1 $y1 STRIPE]
    set cut [odb::dbSBox_create $vdd_sw $via $xvia $yvia STRIPE]
    if {$rect eq "NULL" || $cut eq "NULL"} { error "failed to create VDD bridge $bridge" }
}

puts "T10_PDN_VSS_BRIDGES [llength $vss_bridges]"
puts "T10_PDN_UPPER_INT_VDD_BRIDGES [llength $vdd_bridges]"
check_power_grid -net VDD
check_power_grid -net VSS
if {[info exists ::env(T10_PG_OUTPUT_ODB)] && $::env(T10_PG_OUTPUT_ODB) ne ""} {
    write_db $::env(T10_PG_OUTPUT_ODB)
}
