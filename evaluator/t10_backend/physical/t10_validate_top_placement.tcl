source [file join [file dirname [info script]] t10_audit_top_placement.tcl]
puts "T10_TOP_NATIVE_PLACEMENT_CHECK begin"
check_placement -verbose -report_file_name $::env(T10_PLACEMENT_CHECK_REPORT)
puts "T10_TOP_NATIVE_PLACEMENT_CHECK passed"
if {[info exists ::env(T10_VALIDATED_ODB)] && $::env(T10_VALIDATED_ODB) ne {}} {
  write_db $::env(T10_VALIDATED_ODB)
}
exit
