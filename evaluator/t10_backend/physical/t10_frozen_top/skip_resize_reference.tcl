# Full 16x16 hierarchical reference top.
#
# Generic repair_design treats conservative macro-boundary Liberty arcs as
# ordinary unbuffered top-level nets and has inserted hundreds of thousands of
# cells in earlier probes. Build bounded trees only for measured shell control
# nets. Every load selection is checked so hierarchy drift stops the run.

proc t10_buffer_output_net {inst} {
  foreach pin [get_pins -of_objects $inst] {
    if {[string match */Y [get_full_name $pin]]} {
      return [get_nets -of_objects $pin]
    }
  }
  error "T10 buffer output pin not found"
}

proc t10_expect_loads {tag pins expected} {
  set actual [llength $pins]
  puts "T10_TOP_TREE_LOADS tag=$tag actual=$actual expected=$expected"
  if {$actual != $expected} {
    error "T10 $tag load count changed: expected $expected, got $actual"
  }
}

proc t10_insert_output_queue_tree {source_name tag expected} {
  set source_net [get_nets $source_name]
  set lane_pins {}
  foreach pin [get_pins -of_objects $source_net] {
    if {[string first "output_expand_slot" [get_full_name $pin]] == 0} {
      lappend lane_pins $pin
    }
  }
  t10_expect_loads $tag $lane_pins $expected
  set root [insert_buffer -buffer_cell BUFx12_ASAP7_75t_R -net $source_net \
    -load_pins $lane_pins -buffer_name t10_${tag}_root \
    -net_name t10_${tag}_root_n]
  set root_net [t10_buffer_output_net $root]
  for {set s 0} {$s < 4} {incr s} {
    set s_pins {}
    set sp "output_expand_slot\[$s\]."
    foreach pin $lane_pins {
      if {[string first $sp [get_full_name $pin]] == 0} {lappend s_pins $pin}
    }
    set sb [insert_buffer -buffer_cell BUFx12_ASAP7_75t_R -net $root_net \
      -load_pins $s_pins -buffer_name t10_${tag}_s${s} \
      -net_name t10_${tag}_s${s}_n]
    set s_net [t10_buffer_output_net $sb]
    for {set q 0} {$q < 4} {incr q} {
      set q_pins {}
      for {set c [expr {$q * 4}]} {$c < ($q + 1) * 4} {incr c} {
        set prefix "output_expand_slot\[$s\].output_expand_cell\[$c\]."
        foreach pin $s_pins {
          if {[string first $prefix [get_full_name $pin]] == 0} {
            lappend q_pins $pin
          }
        }
      }
      set qb [insert_buffer -buffer_cell BUFx12_ASAP7_75t_R -net $s_net \
        -load_pins $q_pins -buffer_name t10_${tag}_s${s}q${q} \
        -net_name t10_${tag}_s${s}q${q}_n]
      set q_net [t10_buffer_output_net $qb]
      for {set c [expr {$q * 4}]} {$c < ($q + 1) * 4} {incr c} {
        set c_pins {}
        set prefix "output_expand_slot\[$s\].output_expand_cell\[$c\]."
        foreach pin $q_pins {
          if {[string first $prefix [get_full_name $pin]] == 0} {
            lappend c_pins $pin
          }
        }
        insert_buffer -buffer_cell BUFx8_ASAP7_75t_R -net $q_net \
          -load_pins $c_pins -buffer_name t10_${tag}_s${s}c${c} \
          -net_name t10_${tag}_s${s}c${c}_n
      }
    }
  }
}

# out_ready enters beside the scalar output controls while the 64 queue lanes
# span the bottom of the full chip.  A four-level fanout tree still leaves
# multi-millimeter RC segments.  Keep a short shared trunk for each output slot,
# then give every lane a serial repeater chain so no final_pop segment crosses
# a large fraction of the 10.5 mm parent in one cycle.
proc t10_insert_output_lane_chain {source_name tag expected per_lane} {
  set source_net [get_nets $source_name]
  set lane_pins {}
  foreach pin [get_pins -of_objects $source_net] {
    if {[string first "output_expand_slot" [get_full_name $pin]] == 0} {
      lappend lane_pins $pin
    }
  }
  t10_expect_loads $tag $lane_pins $expected
  set root [insert_buffer -buffer_cell BUFx16f_ASAP7_75t_R \
    -net $source_net -load_pins $lane_pins \
    -buffer_name t10_${tag}_root -net_name t10_${tag}_root_n]
  set root_net [t10_buffer_output_net $root]
  for {set s 0} {$s < 4} {incr s} {
    set s_pins {}
    set sp "output_expand_slot\[$s\]."
    foreach pin $lane_pins {
      if {[string first $sp [get_full_name $pin]] == 0} {lappend s_pins $pin}
    }
    t10_expect_loads ${tag}_s${s} $s_pins [expr {16 * $per_lane}]
    set trunk_net $root_net
    for {set stage 0} {$stage < 4} {incr stage} {
      set trunk [insert_buffer -buffer_cell BUFx16f_ASAP7_75t_R \
        -net $trunk_net -load_pins $s_pins \
        -buffer_name t10_${tag}_s${s}t${stage} \
        -net_name t10_${tag}_s${s}t${stage}_n]
      set trunk_net [t10_buffer_output_net $trunk]
    }
    for {set c 0} {$c < 16} {incr c} {
      set c_pins {}
      set cp "output_expand_slot\[$s\].output_expand_cell\[$c\]."
      foreach pin $s_pins {
        if {[string first $cp [get_full_name $pin]] == 0} {lappend c_pins $pin}
      }
      t10_expect_loads ${tag}_s${s}c${c} $c_pins $per_lane
      set branch_net $trunk_net
      for {set stage 0} {$stage < 12} {incr stage} {
        set repeater [insert_buffer -buffer_cell BUFx8_ASAP7_75t_R \
          -net $branch_net -load_pins $c_pins \
          -buffer_name t10_${tag}_s${s}c${c}r${stage} \
          -net_name t10_${tag}_s${s}c${c}r${stage}_n]
        set branch_net [t10_buffer_output_net $repeater]
      }
    }
  }
}

proc t10_insert_gather_ready_tree {} {
  set source_net [get_nets gather_stage_ready]
  set lane_pins {}
  foreach pin [get_pins -of_objects $source_net] {
    if {[string first "gather_slot" [get_full_name $pin]] == 0} {
      lappend lane_pins $pin
    }
  }
  t10_expect_loads gatherready $lane_pins 1280
  set root [insert_buffer -buffer_cell BUFx16f_ASAP7_75t_R -net $source_net \
    -load_pins $lane_pins -buffer_name t10_gatherready_root \
    -net_name t10_gatherready_root_n]
  set root_net [t10_buffer_output_net $root]
  for {set s 0} {$s < 4} {incr s} {
    set s_pins {}
    set sp "gather_slot\[$s\]."
    foreach pin $lane_pins {
      if {[string first $sp [get_full_name $pin]] == 0} {lappend s_pins $pin}
    }
    set sb [insert_buffer -buffer_cell BUFx12_ASAP7_75t_R -net $root_net \
      -load_pins $s_pins -buffer_name t10_gatherready_s${s} \
      -net_name t10_gatherready_s${s}_n]
    set s_net [t10_buffer_output_net $sb]
    for {set g 0} {$g < 4} {incr g} {
      set g_pins {}
      set gp "gather_slot\[$s\].gather_group\[$g\]."
      foreach pin $s_pins {
        if {[string first $gp [get_full_name $pin]] == 0} {lappend g_pins $pin}
      }
      set gb [insert_buffer -buffer_cell BUFx12_ASAP7_75t_R -net $s_net \
        -load_pins $g_pins -buffer_name t10_gatherready_s${s}g${g} \
        -net_name t10_gatherready_s${s}g${g}_n]
      set g_net [t10_buffer_output_net $gb]
      for {set q 0} {$q < 4} {incr q} {
        set q_pins {}
        for {set c [expr {$q * 4}]} {$c < ($q + 1) * 4} {incr c} {
          set cp "gather_slot\[$s\].gather_group\[$g\].gather_cell\[$c\]."
          foreach pin $g_pins {
            if {[string first $cp [get_full_name $pin]] == 0} {lappend q_pins $pin}
          }
        }
        set qb [insert_buffer -buffer_cell BUFx12_ASAP7_75t_R -net $g_net \
          -load_pins $q_pins -buffer_name t10_gatherready_s${s}g${g}q${q} \
          -net_name t10_gatherready_s${s}g${g}q${q}_n]
        set q_net [t10_buffer_output_net $qb]
        for {set c [expr {$q * 4}]} {$c < ($q + 1) * 4} {incr c} {
          set c_pins {}
          set cp "gather_slot\[$s\].gather_group\[$g\].gather_cell\[$c\]."
          foreach pin $q_pins {
            if {[string first $cp [get_full_name $pin]] == 0} {
              lappend c_pins $pin
            }
          }
          t10_expect_loads gatherready_s${s}g${g}c${c} $c_pins 5
          insert_buffer -buffer_cell BUFx8_ASAP7_75t_R -net $q_net \
            -load_pins $c_pins \
            -buffer_name t10_gatherready_s${s}g${g}c${c} \
            -net_name t10_gatherready_s${s}g${g}c${c}_n
        }
      }
    }
  }
}

proc t10_insert_prefetch_trees {} {
  for {set s 0} {$s < 4} {incr s} {
    set source_name "prefetch_valid\[$s\]"
    set source_net [get_nets $source_name]
    set lane_pins {}
    set sp "gather_slot\[$s\]."
    foreach pin [get_pins -of_objects $source_net] {
      if {[string first $sp [get_full_name $pin]] == 0} {lappend lane_pins $pin}
    }
    t10_expect_loads prefetch_s${s} $lane_pins 64
    set root [insert_buffer -buffer_cell BUFx16f_ASAP7_75t_R -net $source_net \
      -load_pins $lane_pins -buffer_name t10_prefetch_s${s}_root \
      -net_name t10_prefetch_s${s}_root_n]
    set root_net [t10_buffer_output_net $root]
    for {set g 0} {$g < 4} {incr g} {
      set g_pins {}
      set gp "gather_slot\[$s\].gather_group\[$g\]."
      foreach pin $lane_pins {
        if {[string first $gp [get_full_name $pin]] == 0} {lappend g_pins $pin}
      }
      set gb [insert_buffer -buffer_cell BUFx12_ASAP7_75t_R -net $root_net \
        -load_pins $g_pins -buffer_name t10_prefetch_s${s}g${g} \
        -net_name t10_prefetch_s${s}g${g}_n]
      set g_net [t10_buffer_output_net $gb]
      for {set q 0} {$q < 4} {incr q} {
        set q_pins {}
        for {set c [expr {$q * 4}]} {$c < ($q + 1) * 4} {incr c} {
          set cp "gather_slot\[$s\].gather_group\[$g\].gather_cell\[$c\]."
          foreach pin $g_pins {
            if {[string first $cp [get_full_name $pin]] == 0} {lappend q_pins $pin}
          }
        }
        insert_buffer -buffer_cell BUFx8_ASAP7_75t_R -net $g_net \
          -load_pins $q_pins -buffer_name t10_prefetch_s${s}g${g}q${q} \
          -net_name t10_prefetch_s${s}g${g}q${q}_n
      }
    }
  }
}

proc t10_insert_row_select_trees {} {
  for {set r 0} {$r < 16} {incr r} {
    set g [expr {$r / 4}]
    for {set s 0} {$s < 4} {incr s} {
      set source_name "prefetch_row_select\[$r\]\[$s\]"
      set source_net [get_nets $source_name]
      set lane_pins {}
      set gp "gather_slot\[$s\].gather_group\[$g\]."
      foreach pin [get_pins -of_objects $source_net] {
        if {[string first $gp [get_full_name $pin]] == 0} {
          lappend lane_pins $pin
        }
      }
      t10_expect_loads rowsel_r${r}s${s} $lane_pins 32
      set root [insert_buffer -buffer_cell BUFx12_ASAP7_75t_R -net $source_net \
        -load_pins $lane_pins -buffer_name t10_rowsel_r${r}s${s}_root \
        -net_name t10_rowsel_r${r}s${s}_root_n]
      set root_net [t10_buffer_output_net $root]
      for {set q 0} {$q < 4} {incr q} {
        set q_pins {}
        for {set c [expr {$q * 4}]} {$c < ($q + 1) * 4} {incr c} {
          set cp "gather_slot\[$s\].gather_group\[$g\].gather_cell\[$c\]."
          foreach pin $lane_pins {
            if {[string first $cp [get_full_name $pin]] == 0} {
              lappend q_pins $pin
            }
          }
        }
        set qb [insert_buffer -buffer_cell BUFx12_ASAP7_75t_R -net $root_net \
          -load_pins $q_pins -buffer_name t10_rowsel_r${r}s${s}q${q} \
          -net_name t10_rowsel_r${r}s${s}q${q}_n]
        set q_net [t10_buffer_output_net $qb]
        for {set c [expr {$q * 4}]} {$c < ($q + 1) * 4} {incr c} {
          set c_pins {}
          set cp "gather_slot\[$s\].gather_group\[$g\].gather_cell\[$c\]."
          foreach pin $q_pins {
            if {[string first $cp [get_full_name $pin]] == 0} {
              lappend c_pins $pin
            }
          }
          insert_buffer -buffer_cell BUFx8_ASAP7_75t_R -net $q_net \
            -load_pins $c_pins -buffer_name t10_rowsel_r${r}s${s}c${c} \
            -net_name t10_rowsel_r${r}s${s}c${c}_n
        }
      }
    }
  }
}

proc t10_insert_output_stage_ready_tree {} {
  set source_net [get_nets final_stage_ready]
  set lane_pins {}
  foreach pin [get_pins -of_objects $source_net] {
    if {[string first "compact_slot" [get_full_name $pin]] == 0} {
      lappend lane_pins $pin
    }
  }
  t10_expect_loads outready $lane_pins 192
  set root [insert_buffer -buffer_cell BUFx16f_ASAP7_75t_R -net $source_net \
    -load_pins $lane_pins -buffer_name t10_outready_root \
    -net_name t10_outready_root_n]
  set root_net [t10_buffer_output_net $root]
  for {set s 0} {$s < 4} {incr s} {
    set s_pins {}
    set sp "compact_slot\[$s\]."
    foreach pin $lane_pins {
      if {[string first $sp [get_full_name $pin]] == 0} {lappend s_pins $pin}
    }
    set sb [insert_buffer -buffer_cell BUFx12_ASAP7_75t_R -net $root_net \
      -load_pins $s_pins -buffer_name t10_outready_s${s} \
      -net_name t10_outready_s${s}_n]
    set s_net [t10_buffer_output_net $sb]
    for {set q 0} {$q < 4} {incr q} {
      set q_pins {}
      for {set c [expr {$q * 4}]} {$c < ($q + 1) * 4} {incr c} {
        set cp "compact_slot\[$s\].compact_cell\[$c\]."
        foreach pin $s_pins {
          if {[string first $cp [get_full_name $pin]] == 0} {lappend q_pins $pin}
        }
      }
      set qb [insert_buffer -buffer_cell BUFx12_ASAP7_75t_R -net $s_net \
        -load_pins $q_pins -buffer_name t10_outready_s${s}q${q} \
        -net_name t10_outready_s${s}q${q}_n]
      set q_net [t10_buffer_output_net $qb]
      for {set c [expr {$q * 4}]} {$c < ($q + 1) * 4} {incr c} {
        set c_pins {}
        set cp "compact_slot\[$s\].compact_cell\[$c\]."
        foreach pin $q_pins {
          if {[string first $cp [get_full_name $pin]] == 0} {lappend c_pins $pin}
        }
        insert_buffer -buffer_cell BUFx8_ASAP7_75t_R -net $q_net \
          -load_pins $c_pins -buffer_name t10_outready_s${s}c${c} \
          -net_name t10_outready_s${s}c${c}_n
      }
    }
  }
}

proc t10_insert_gather_valid_trees {} {
  for {set s 0} {$s < 4} {incr s} {
    set source_name "gather_valid\[$s\]"
    set source_net [get_nets $source_name]
    set lane_pins {}
    set sp "compact_slot\[$s\]."
    foreach pin [get_pins -of_objects $source_net] {
      if {[string first $sp [get_full_name $pin]] == 0} {lappend lane_pins $pin}
    }
    t10_expect_loads gvalid_s${s} $lane_pins 48
    set root [insert_buffer -buffer_cell BUFx12_ASAP7_75t_R -net $source_net \
      -load_pins $lane_pins -buffer_name t10_gvalid_s${s}_root \
      -net_name t10_gvalid_s${s}_root_n]
    set root_net [t10_buffer_output_net $root]
    for {set q 0} {$q < 4} {incr q} {
      set q_pins {}
      for {set c [expr {$q * 4}]} {$c < ($q + 1) * 4} {incr c} {
        set cp "compact_slot\[$s\].compact_cell\[$c\]."
        foreach pin $lane_pins {
          if {[string first $cp [get_full_name $pin]] == 0} {lappend q_pins $pin}
        }
      }
      set qb [insert_buffer -buffer_cell BUFx12_ASAP7_75t_R -net $root_net \
        -load_pins $q_pins -buffer_name t10_gvalid_s${s}q${q} \
        -net_name t10_gvalid_s${s}q${q}_n]
      set q_net [t10_buffer_output_net $qb]
      for {set c [expr {$q * 4}]} {$c < ($q + 1) * 4} {incr c} {
        set c_pins {}
        set cp "compact_slot\[$s\].compact_cell\[$c\]."
        foreach pin $q_pins {
          if {[string first $cp [get_full_name $pin]] == 0} {lappend c_pins $pin}
        }
        insert_buffer -buffer_cell BUFx8_ASAP7_75t_R -net $q_net \
          -load_pins $c_pins -buffer_name t10_gvalid_s${s}c${c} \
          -net_name t10_gvalid_s${s}c${c}_n
      }
    }
  }
}

# Each row read pointer drives the four tile macros in that physical tile row.
# The 10.5 mm parent is too large for an unbuffered macro-input branch, so give
# every macro pin an explicit repeater chain. RePlAce distributes the serial
# cells along the source-to-macro path during the second global placement.
proc t10_insert_row_read_trees {} {
  for {set r 0} {$r < 16} {incr r} {
    for {set b 0} {$b < 4} {incr b} {
      set source_name "row_read_slot\[$r\]\[$b\]"
      set source_net [get_nets $source_name]
      set macro_pins {}
      foreach pin [get_pins -of_objects $source_net] {
        if {[string first "/read_slot\[" [get_full_name $pin]] >= 0} {
          lappend macro_pins $pin
        }
      }
      t10_expect_loads rowread_r${r}b${b} $macro_pins 4
      set root [insert_buffer -buffer_cell BUFx12_ASAP7_75t_R \
        -net $source_net -load_pins $macro_pins \
        -buffer_name t10_rowread_r${r}b${b}_root \
        -net_name t10_rowread_r${r}b${b}_root_n]
      set root_net [t10_buffer_output_net $root]
      set branch 0
      foreach pin $macro_pins {
        set branch_net $root_net
        for {set stage 0} {$stage < 8} {incr stage} {
          set cell [expr {$stage == 7 ? "BUFx8_ASAP7_75t_R" : \
                                      "BUFx12_ASAP7_75t_R"}]
          set repeater [insert_buffer -buffer_cell $cell -net $branch_net \
            -load_pins [list $pin] \
            -buffer_name t10_rowread_r${r}b${b}m${branch}s${stage} \
            -net_name t10_rowread_r${r}b${b}m${branch}s${stage}_n]
          set branch_net [t10_buffer_output_net $repeater]
        }
        incr branch
      }
    }
  }
}

rename repair_design_helper t10_orfs_repair_design_helper
proc repair_design_helper {} {
  puts "T10_TOP_REFERENCE_TARGETED_TREES begin"
  # Delay ordinary I/O buffers until this stage so the channel projection
  # below can assign them before placement. Leaving them ungrouped in the
  # preceding multi-region global placement creates an infeasible top region.
  buffer_ports
  t10_insert_output_lane_chain final_push finalpush 384 6
  t10_insert_output_lane_chain output_queue_write_ptr writeptr 256 4
  t10_insert_output_lane_chain final_pop finalpop 64 1
  t10_insert_gather_ready_tree
  t10_insert_prefetch_trees
  t10_insert_row_select_trees
  t10_insert_output_stage_ready_tree
  t10_insert_gather_valid_trees
  t10_insert_row_read_trees
  # Port buffers and the targeted trees above were created after the initial
  # channel projection. Rebuild all clusters from current coordinates so every
  # new shell instance is covered before the second global placement.
  source [file join $::env(T10_BACKEND_ROOT) physical t10_frozen_top/top_shell_regions.tcl]
  global_placement -density 0.60 -pad_left 0 -pad_right 0 \
    -force_center_initial_place -min_phi_coef 0.95 -max_phi_coef 1.05 \
    -bin_grid_count 128 -overflow 0.10
  estimate_parasitics -placement
  puts "T10_TOP_REFERENCE_TARGETED_TREES done buffers=6405"
}
