foreach name {T10_INPUT_ODB T10_OUTPUT_ODB T10_PLUGIN_DIR} {
  if {![info exists ::env($name)]} {error "$name is required"}
}
read_db $::env(T10_INPUT_ODB)
load $::env(T10_PLUGIN_DIR)/t10_manual_v15_case5.so T10manualv15patch
puts "T10_MANUAL_V15_PATCH [t10_manual_v15_patch 5]"
load $::env(T10_PLUGIN_DIR)/t10_manual_v15_compact_v2.so T10manualv15enclosure
puts "T10_MANUAL_V15_ENCLOSURE [t10_manual_v15_enclosure]"
load $::env(T10_PLUGIN_DIR)/t10_manual_v15_local_v2.so T10manualv15local
puts "T10_MANUAL_V15_LOCAL [t10_manual_v15_local]"
write_db $::env(T10_OUTPUT_ODB)
exit
