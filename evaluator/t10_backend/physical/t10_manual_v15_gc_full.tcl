set_thread_count 8
read_db $::env(T10_INPUT_ODB)
# Initialize the unchanged native router/parser/technology and region query.
drt::check_drc -box {0 0 1000 1000} -output_file $::env(T10_DRC_REPORT).init
load $::env(T10_PATCH_SO) T10manualv15gcdiag
puts "T10_FULL_CHECK [t10_manual_v15_gc_full $::env(T10_DRC_REPORT)]"
exit
