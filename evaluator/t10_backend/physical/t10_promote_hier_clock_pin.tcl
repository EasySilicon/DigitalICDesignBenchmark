# Extend an already routed hierarchy clock terminal to the macro boundary.
# The caller supplies a rectangle that must overlap the existing routed clock
# metal.  This creates real terminal metal in the ODB and a matching abstract
# pin in the LEF; it is not an abstract-only accessibility exception.

proc require_env {name} {
  if {![info exists ::env($name)] || $::env($name) eq ""} {
    error "missing required environment variable $name"
  }
  return $::env($name)
}

set input_odb [require_env T10_INPUT_ODB]
set output_odb [require_env T10_OUTPUT_ODB]
set output_lef [require_env T10_OUTPUT_LEF]
set layer_name [require_env T10_CLOCK_PIN_LAYER]
set x_min [require_env T10_CLOCK_PIN_X_MIN_DBU]
set y_min [require_env T10_CLOCK_PIN_Y_MIN_DBU]
set x_max [require_env T10_CLOCK_PIN_X_MAX_DBU]
set y_max [require_env T10_CLOCK_PIN_Y_MAX_DBU]

read_db $input_odb
set block [ord::get_db_block]
set bterm [$block findBTerm clk]
if {$bterm == "NULL"} {
  error "missing clk block terminal"
}
set layer [[ord::get_db_tech] findLayer $layer_name]
if {$layer == "NULL"} {
  error "missing technology layer $layer_name"
}
if {$x_min >= $x_max || $y_min >= $y_max} {
  error "invalid promoted clock pin rectangle"
}

set bpin [odb::dbBPin_create $bterm]
$bpin setPlacementStatus PLACED
set box [odb::dbBox_create $bpin $layer $x_min $y_min $x_max $y_max]
puts "T10_PROMOTED_CLOCK_PIN layer=$layer_name rect=[$box xMin],[$box yMin],[$box xMax],[$box yMax]"

write_abstract_lef $output_lef
write_db $output_odb
exit
