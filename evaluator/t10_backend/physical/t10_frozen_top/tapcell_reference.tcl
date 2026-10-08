# Hierarchical reference probe only.
#
# The ASAP7 default tap insertion creates roughly 730k physical-only instances
# across this 10.5 mm square parent, even though 16 fixed tile macros occupy
# nearly all of the core.  That physical-only population dominates OpenROAD's
# memory without materially changing this benchmark's timing, standard-cell
# area, or vectorless power estimate.  Preserve the required macro row cuts,
# and leave well-tap/endcap signoff to the independently qualified tile views.
puts "T10_TOP_REFERENCE_TAPCELL_SKIP physical_only_cells_omitted=1"
cut_rows
