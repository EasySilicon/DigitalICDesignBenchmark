set_thread_count 8
read_db $::env(T10_INPUT_ODB)
drt::check_drc -box {0 0 1000 1000} -output_file $::env(T10_DRC_REPORT).init
load $::env(T10_PATCH_SO) T10window
puts [t10_gc_window $::env(T10_DRC_REPORT) {*}$::env(T10_CHECK_BOX)]
exit
