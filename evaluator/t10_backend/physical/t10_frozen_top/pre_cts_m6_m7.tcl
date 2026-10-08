set_routing_layers -clock M6-M7
set_wire_rc -clock -layer M7
if {[info exists ::env(T10_CTS_CELL_LIB)] &&
    $::env(T10_CTS_CELL_LIB) ne ""} {
  read_liberty $::env(T10_CTS_CELL_LIB)
  puts "T10_TOP_CTS_EXTRA_LIB $::env(T10_CTS_CELL_LIB)"
}
puts "T10_TOP_CLOCK_LAYERS M6-M7 ESTIMATED_CLOCK_RC M7"

# TritonCTS can attach a tile macro clock pin directly to a high-level H-tree
# branch.  On this 10.5 mm parent that leaves several millimetres of unbuffered
# M7 after the last CTS cell.  Build deterministic post-CTS repeater chains in
# the 100 um horizontal and vertical channels around the sixteen routed tiles.
proc t10_nearest_channel {value channels} {
  set nearest [lindex $channels 0]
  set best [expr {abs($value - $nearest)}]
  foreach channel [lrange $channels 1 end] {
    set distance [expr {abs($value - $channel)}]
    if {$distance < $best} {
      set nearest $channel
      set best $distance
    }
  }
  return [list $nearest $best]
}

proc t10_append_axis_points {points_var x0 y0 x1 y1 step} {
  upvar 1 $points_var points
  set dx [expr {$x1 - $x0}]
  set dy [expr {$y1 - $y0}]
  if {abs($dx) > 0.001 && abs($dy) > 0.001} {
    error "T10 macro clock chain segment is not Manhattan: $x0,$y0 -> $x1,$y1"
  }
  set length [expr {abs($dx) + abs($dy)}]
  if {$length <= 0.001} {
    return
  }
  set count [expr {int(ceil($length / $step))}]
  for {set index 1} {$index <= $count} {incr index} {
    set fraction [expr {double($index) / $count}]
    lappend points [list \
      [expr {$x0 + $fraction * $dx}] \
      [expr {$y0 + $fraction * $dy}]]
  }
}

proc t10_buffer_input_pin {buffer} {
  foreach pin [get_pins -of_objects $buffer] {
    if {[string match */A [get_full_name $pin]]} {
      return $pin
    }
  }
  error "T10 macro clock chain buffer input pin missing"
}

proc t10_insert_reference_macro_clock_chains {} {
  set block [ord::get_db_block]
  set dbu [$block getDbUnitsPerMicron]
  set channels {50.0 2650.0 5250.0 7850.0 10450.0}
  set step $::env(T10_REFERENCE_MACRO_CLOCK_CHAIN_STEP)
  set macro_count 0
  set buffer_count 0
  foreach inst [$block getInsts] {
    if {[[$inst getMaster] getName] ne "t10_reference_tile_4x4"} {
      continue
    }
    set macro_pin [get_pins "[$inst getName]/clk"]
    if {[llength $macro_pin] != 1} {
      error "T10 macro clock chain expected one clock pin on [$inst getName], got [llength $macro_pin]"
    }
    set clock_iterm {}
    foreach iterm [$inst getITerms] {
      if {[[$iterm getMTerm] getName] eq "clk"} {
        set clock_iterm $iterm
        break
      }
    }
    if {$clock_iterm eq {}} {
      error "T10 macro clock chain cannot find physical clock pin on [$inst getName]"
    }
    set clock_net [$clock_iterm getNet]
    set driver_iterms {}
    foreach iterm [$clock_net getITerms] {
      if {[[$iterm getMTerm] getIoType] eq "OUTPUT"} {
        lappend driver_iterms $iterm
      }
    }
    if {[llength $driver_iterms] != 1} {
      error "T10 macro clock chain expected one driver on [$clock_net getName], got [llength $driver_iterms]"
    }
    set driver_inst [[lindex $driver_iterms 0] getInst]
    set driver_box [$driver_inst getBBox]
    set driver_x [expr {double([$driver_box xMin] + [$driver_box xMax]) / (2.0 * $dbu)}]
    set driver_y [expr {double([$driver_box yMin] + [$driver_box yMax]) / (2.0 * $dbu)}]
    set inst_box [$inst getBBox]
    set pin_box [$clock_iterm getBBox]
    set macro_x [expr {double([$inst_box xMin]) / $dbu}]
    set macro_y [expr {double([$inst_box yMin]) / $dbu}]
    set row [expr {int(round((7900.032 - $macro_y) / 2600.0))}]
    set col [expr {int(round(($macro_x - 100.032) / 2600.0))}]
    if {$row < 0 || $row > 3 || $col < 0 || $col > 3} {
      error "T10 macro clock chain unexpected macro coordinate [$inst getName] at $macro_x,$macro_y"
    }
    set pin_x [expr {double([$pin_box xMin] + [$pin_box xMax]) / (2.0 * $dbu)}]
    set target_y [expr {double([$inst_box yMax]) / $dbu + 20.0 + 20.0 * $col}]
    set target_vx [expr {double([$inst_box xMax]) / $dbu + 20.0 + 20.0 * $row}]
    lassign [t10_nearest_channel $driver_x $channels] source_vx source_dx
    lassign [t10_nearest_channel $driver_y $channels] source_hy source_dy
    set points {}
    set x $driver_x
    set y $driver_y
    if {$source_dx <= $source_dy} {
      set route_vx [expr {$source_vx - 30.0 + 20.0 * $row}]
      t10_append_axis_points points $x $y $route_vx $y $step
      set x $route_vx
      t10_append_axis_points points $x $y $x $target_y $step
      set y $target_y
    } else {
      set route_hy [expr {$source_hy - 30.0 + 20.0 * $col}]
      t10_append_axis_points points $x $y $x $route_hy $step
      set y $route_hy
      t10_append_axis_points points $x $y $target_vx $y $step
      set x $target_vx
      t10_append_axis_points points $x $y $x $target_y $step
      set y $target_y
    }
    t10_append_axis_points points $x $y $pin_x $y $step
    set load_pin $macro_pin
    set stage 0
    for {set point_index [expr {[llength $points] - 1}]} {$point_index >= 0} {incr point_index -1} {
      set location [lindex $points $point_index]
      set buffer [insert_buffer \
        -buffer_cell $::env(T10_REFERENCE_MACRO_CLOCK_LEAF_CELL) \
        -load_pins [list $load_pin] \
        -location $location \
        -buffer_name t10_macro_clk_chain_${row}_${col}_${stage} \
        -net_name t10_macro_clk_chain_${row}_${col}_${stage}_out_]
      set load_pin [t10_buffer_input_pin $buffer]
      incr stage
      incr buffer_count
    }
    puts "T10_TOP_MACRO_CLOCK_CHAIN row=$row col=$col source=$driver_x,$driver_y target=$pin_x,$target_y buffers=$stage"
    incr macro_count
  }
  if {$macro_count != 16} {
    error "T10 macro clock chain count changed: expected 16, got $macro_count"
  }
  puts "T10_TOP_MACRO_CLOCK_CHAINS macros=$macro_count buffers=$buffer_count step_um=$step cell=$::env(T10_REFERENCE_MACRO_CLOCK_LEAF_CELL)"
}

# Keep a sparse set of parent placement rows for CTS buffer anchoring.  The
# full hierarchical top has 187k row fragments / 6.78e8 sites; TritonCTS
# otherwise spends minutes scanning legal sites after topology generation.
# Existing globally placed shell cells retain their coordinates.  The parent
# detailed-placement gate is intentionally disabled below for this probe.
if { [info exists ::env(T10_REFERENCE_CTS_ROW_STRIDE)] } {
  set stride $::env(T10_REFERENCE_CTS_ROW_STRIDE)
  if {$stride > 1} {
    set block [ord::get_db_block]
    set y_index [dict create]
    set kept 0
    set removed 0
    foreach row [$block getRows] {
      set y [lindex [$row getOrigin] 1]
      if {![dict exists $y_index $y]} {
        dict set y_index $y [dict size $y_index]
      }
      if {[dict get $y_index $y] % $stride != 0} {
        odb::dbRow_destroy $row
        incr removed
      } else {
        incr kept
      }
    }
    puts "T10_TOP_REFERENCE_SPARSE_CTS_ROWS stride=$stride kept=$kept removed=$removed"
  }
}

# The generated top-level clock pin is in the north-east perimeter channel,
# while TritonCTS places its H-tree root near the array centre.  ASAP7 M7 is
# too resistive for that 7.6 mm unbuffered source segment.  Let TritonCTS first
# build the fanout tree from the original clock port, then insert a physical
# repeater trunk on only the source-to-root net.  All trunk points stay in the
# east perimeter and central horizontal channels outside the sixteen macros.
if { [info exists ::env(T10_REFERENCE_CLOCK_TRUNK)] &&
     $::env(T10_REFERENCE_CLOCK_TRUNK) == 1 } {
  proc t10_insert_reference_clock_source_trunk {} {
    set block [ord::get_db_block]
    set trunk_points {}
    for {set y 10200} {$y >= 5400} {incr y -300} {
      lappend trunk_points [list 10450 $y]
    }
    for {set x 10150} {$x >= 5350} {incr x -300} {
      lappend trunk_points [list $x 5250]
    }
    set cts_root_net {}
    set trunk_index 0
    foreach location $trunk_points {
      set buffer_name t10_clk_source_trunk_${trunk_index}_buf
      set next_net t10_clk_source_trunk_net_${trunk_index}_out_
      if {$trunk_index == 0} {
        set insertion_net clk
      } else {
        set insertion_net $cts_root_net
      }
      insert_buffer \
        -buffer_cell $::env(T10_REFERENCE_CLOCK_TRUNK_CELL) \
        -net $insertion_net \
        -location $location \
        -buffer_name $buffer_name \
        -net_name $next_net
      set created_net {}
      foreach candidate_net [$block getNets] {
        set candidate_name [$candidate_net getName]
        if {[string match "${next_net}*" $candidate_name]} {
          set created_net $candidate_name
          break
        }
      }
      if {$created_net eq {}} {
        error "T10 clock trunk failed to resolve output net for $buffer_name"
      }
      if {$trunk_index == 0} {
        set cts_root_net $created_net
      }
      incr trunk_index
    }
    puts "T10_TOP_REFERENCE_CLOCK_SOURCE_TRUNK buffers=$trunk_index endpoint=5350,5250 cts_root_net=$cts_root_net cell=$::env(T10_REFERENCE_CLOCK_TRUNK_CELL)"
  }
  puts "T10_TOP_REFERENCE_CLOCK_SOURCE_TRUNK enabled=1"
}

if {([info exists ::env(T10_REFERENCE_MACRO_CLOCK_CHAINS)] &&
     $::env(T10_REFERENCE_MACRO_CLOCK_CHAINS) == 1) ||
    ([info exists ::env(T10_REFERENCE_CLOCK_TRUNK)] &&
     $::env(T10_REFERENCE_CLOCK_TRUNK) == 1)} {
  rename clock_tree_synthesis t10_openroad_clock_tree_synthesis
  proc clock_tree_synthesis { args } {
    t10_openroad_clock_tree_synthesis {*}$args
    if {[info exists ::env(T10_REFERENCE_MACRO_CLOCK_CHAINS)] &&
        $::env(T10_REFERENCE_MACRO_CLOCK_CHAINS) == 1} {
      t10_insert_reference_macro_clock_chains
    }
    if {[info exists ::env(T10_REFERENCE_CLOCK_TRUNK)] &&
        $::env(T10_REFERENCE_CLOCK_TRUNK) == 1} {
      t10_insert_reference_clock_source_trunk
    }
    # Persist the actual topology before the potentially large timing report.
    # If a higher-priority job needs the host, CTS work can resume from this
    # checkpoint. It still requires post-CTS placement and timing validation.
    if {[info exists ::env(T10_WIDE_CLOCK_NDR)] &&
        $::env(T10_WIDE_CLOCK_NDR) == 1} {
      source $::env(POST_CTS_TCL)
    }
    orfs_write_db $::env(RESULTS_DIR)/4_1_cts_topology.odb
    orfs_write_sdc $::env(RESULTS_DIR)/4_cts_topology.sdc
    puts "T10_TOP_CTS_TOPOLOGY_SAVED $::env(RESULTS_DIR)/4_1_cts_topology.odb"
  }
  set macro_chains_enabled 0
  if {[info exists ::env(T10_REFERENCE_MACRO_CLOCK_CHAINS)]} {
    set macro_chains_enabled $::env(T10_REFERENCE_MACRO_CLOCK_CHAINS)
  }
  set source_trunk_enabled 0
  if {[info exists ::env(T10_REFERENCE_CLOCK_TRUNK)]} {
    set source_trunk_enabled $::env(T10_REFERENCE_CLOCK_TRUNK)
  }
  puts "T10_TOP_REFERENCE_CTS_WRAPPER macro_chains=$macro_chains_enabled source_trunk=$source_trunk_enabled"
}

# The full 10.5 mm ASAP7 parent contains about 6.78e8 legal placement sites.
# OpenROAD's detailed placer materializes enough of that site map to exceed the
# 90 GiB host limit even though the parent has only ~155k movable instances.
# For this hierarchical reference probe, preserve global-placement coordinates
# and run parent CTS without the flat-block legalization pass.
if { [info exists ::env(T10_REFERENCE_SKIP_CTS_DPL)] &&
     $::env(T10_REFERENCE_SKIP_CTS_DPL) == 1 } {
  rename detailed_placement t10_openroad_detailed_placement
  proc detailed_placement { args } {
    puts "T10_TOP_REFERENCE_SKIP_CTS_DPL reason=asap7_parent_site_map_memory"
  }
}
