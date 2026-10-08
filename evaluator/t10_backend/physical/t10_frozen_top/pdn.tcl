add_global_connection -net {VDD} -inst_pattern {.*} -pin_pattern {^VDD$} -power
add_global_connection -net {VDD} -inst_pattern {.*} -pin_pattern {^VDDPE$}
add_global_connection -net {VDD} -inst_pattern {.*} -pin_pattern {^VDDCE$}
add_global_connection -net {VSS} -inst_pattern {.*} -pin_pattern {^VSS$} -ground
add_global_connection -net {VSS} -inst_pattern {.*} -pin_pattern {^VSSE$}
global_connect
set_voltage_domain -name {CORE} -power {VDD} -ground {VSS}

define_pdn_grid -name {top} -voltage_domains {CORE} -pins {M9}
add_pdn_stripe -grid {top} -layer {M1} -width {0.018} -pitch {0.54} -offset {0} -followpins
add_pdn_stripe -grid {top} -layer {M2} -width {0.018} -pitch {0.54} -offset {0} -followpins
add_pdn_stripe -grid {top} -layer {M5} -width {0.12} -spacing {0.072} -pitch {43.2} -offset {0.300}
add_pdn_stripe -grid {top} -layer {M6} -width {0.288} -spacing {0.096} -pitch {43.2} -offset {0.513}
add_pdn_stripe -grid {top} -layer {M7} -width {0.288} -spacing {0.096} -pitch {43.2} -offset {0.513}
add_pdn_stripe -grid {top} -layer {M8} -width {0.288} -spacing {0.096} -pitch {43.2} -offset {0.513}
add_pdn_stripe -grid {top} -layer {M9} -width {0.288} -spacing {0.096} -pitch {43.2} -offset {0.513}
add_pdn_connect -grid {top} -layers {M1 M2}
add_pdn_connect -grid {top} -layers {M2 M5}
add_pdn_connect -grid {top} -layers {M5 M6}
add_pdn_connect -grid {top} -layers {M6 M7}
add_pdn_connect -grid {top} -layers {M7 M8}
add_pdn_connect -grid {top} -layers {M8 M9}

# The tile view used for this full-DUT PPA reference is a global-route
# abstract.  It has signal timing and M9 PG shapes, but it is not a signoff PG
# macro view.  Build the continuous parent grid here and leave per-tile PG
# closure outside the reference PPA flow; attempting macro-grid vias against
# the abstract can fail nondeterministically for otherwise identical tiles.
