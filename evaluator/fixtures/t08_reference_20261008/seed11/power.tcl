read_liberty {/mnt/ubu_3T/ic_bcmk_trials/t11_single_seed_opt_20261008_WW0FuF/frozen_runner/vendor/asap7/lib/NLDM/asap7sc7p5t_AO_RVT_TT_nldm_211120.lib.gz}
read_liberty {/mnt/ubu_3T/ic_bcmk_trials/t11_single_seed_opt_20261008_WW0FuF/frozen_runner/vendor/asap7/lib/NLDM/asap7sc7p5t_INVBUF_RVT_TT_nldm_220122.lib.gz}
read_liberty {/mnt/ubu_3T/ic_bcmk_trials/t11_single_seed_opt_20261008_WW0FuF/frozen_runner/vendor/asap7/lib/NLDM/asap7sc7p5t_OA_RVT_TT_nldm_211120.lib.gz}
read_liberty {/mnt/ubu_3T/ic_bcmk_trials/t11_single_seed_opt_20261008_WW0FuF/frozen_runner/vendor/asap7/lib/NLDM/asap7sc7p5t_SEQ_RVT_TT_nldm_220123.lib}
read_liberty {/mnt/ubu_3T/ic_bcmk_trials/t11_single_seed_opt_20261008_WW0FuF/frozen_runner/vendor/asap7/lib/NLDM/asap7sc7p5t_SIMPLE_RVT_TT_nldm_211120.lib.gz}
read_liberty {/mnt/ubu_3T/ic_bcmk_trials/t11_single_seed_opt_20261008_WW0FuF/frozen_runner/vendor/lambdapdk_fakeram7/upstream/nldm/fakeram7_tdp_4096x32.lib}
read_db {/mnt/ubu_3T/ic_bcmk_orfs_asap7/flow/results/asap7/mac_1g_repair/ic_probe_t11_wc_p1000_u10_d0.6_s11_1fd5f91928/6_final.odb}
read_sdc {/mnt/ubu_3T/ic_bcmk_orfs_asap7/flow/results/asap7/mac_1g_repair/ic_probe_t11_wc_p1000_u10_d0.6_s11_1fd5f91928/6_final.sdc}
read_spef {/mnt/ubu_3T/ic_bcmk_orfs_asap7/flow/results/asap7/mac_1g_repair/ic_probe_t11_wc_p1000_u10_d0.6_s11_1fd5f91928/6_final.spef}
read_vcd -scope tb_t11_power/dut {/mnt/ubu_3T/ic_bcmk_trials/t11_single_seed_opt_20261008_WW0FuF/single_seed/seed11/power/activity.vcd}
report_activity_annotation
report_power
puts "T11_SRAM_POWER_BEGIN"
set macro_cells [get_cells -hierarchical -filter {ref_name == fakeram7_tdp_4096x32} *]
report_power -instances $macro_cells
foreach inst $macro_cells {
  lassign [sta::instance_power $inst [sta::cmd_scene]] internal switching leakage total
  puts "T11_SRAM_POWER name=[sta::get_full_name $inst] internal=$internal switching=$switching leakage=$leakage total=$total"
}
puts "T11_SRAM_POWER_END"
