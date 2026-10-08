# Hard placement blockages at the measured CPA, class-2 and class-1 macro-pin
# escape corners. They prevent detailed placement from repopulating the exact
# regions that dominated the PE boundary DRC reports.
create_blockage -region {195 208.2 230 225}
create_blockage -region {195 190 210 208.2}
create_blockage -region {350 195 390 210}
create_blockage -region {350 210 365 225}

create_blockage -region {195 280 230 300}
create_blockage -region {195 300 210 320}
create_blockage -region {295 280 330 300}
create_blockage -region {316.4 300 330 320}
