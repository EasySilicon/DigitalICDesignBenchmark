# Clear only the two measured macro-pin escape corners.
create_blockage -soft -region {195 208.2 230 225}
create_blockage -soft -region {195 190 210 208.2}
create_blockage -soft -region {350 195 390 210}
create_blockage -soft -region {350 210 365 225}

# Residual class-1 FP macro lower left/right escape corners at (210,300) and (316,300).
create_blockage -soft -region {195 280 230 300}
create_blockage -soft -region {195 300 210 320}
create_blockage -soft -region {295 280 330 300}
create_blockage -soft -region {316.4 300 330 320}
