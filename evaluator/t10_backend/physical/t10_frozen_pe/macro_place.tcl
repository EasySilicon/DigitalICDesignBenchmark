# Nine fixed macros, >=20 um mutual halo gaps and >=35 um die-edge clearance.
set block [ord::get_db_block]
set fp2 0
set intidx 0
foreach inst [$block getInsts] {
    set master [$inst getMaster]
    if {![$master isBlock]} { continue }
    set name [$inst getName]
    if {[string first "cpa_postprocess" $name] >= 0} {
        set xy {210 100}
    } elseif {[string first "class0" $name] >= 0} {
        set xy {50 300}
    } elseif {[string first "class1" $name] >= 0} {
        set xy {210 300}
    } elseif {[string first "class2" $name] >= 0} {
        if {$fp2 == 0} { set xy {365 325} } else { set xy {365 210} }
        incr fp2
    } elseif {[string first "int_group" $name] >= 0} {
        set coords {{50 50} {120 50} {50 120} {120 120}}
        set xy [lindex $coords $intidx]
        incr intidx
    } else {
        error "Unexpected T10 macro: $name"
    }
    place_macro -macro_name $name -location $xy -orientation R0
    puts "T10_FIXED_MACRO $name $xy"
}
if {$fp2 != 2 || $intidx != 4} { error "T10 macro count mismatch" }
