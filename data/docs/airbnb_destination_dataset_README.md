# Airbnb listings matched to Expedia flight destinations

## Files

- `airbnb_flight_destination_markets_full_listings_2026.csv.gz` contains all listing rows and detailed source columns from 13 city snapshots. Added fields include listing ID/key, source market and snapshot date, matching airport codes, match type, current snapshot price, and `is_group_stay_candidate`.
- `airbnb_flight_destination_markets_availability_2022_synthetic.csv.gz` contains synthetic availability for group-stay candidates, for each distinct 2022 `flightDate` in the Expedia sample.
- `expedia_airport_airbnb_market_map.csv` shows airport coverage and gaps.
- `airbnb_destination_source_manifest.csv` records all source markets, snapshot dates, URLs, and row counts.

## Coverage

Inside Airbnb advertises country-wide archive files, including for the United States. I did not find a direct U.S.-wide archive link in the current public city download table, so this build combines the 13 U.S. city/region markets listed below that match the flight destinations. It is a complete combined file for these markets, not a nationwide U.S. extract: Boston, Broward County, Chicago, Dallas, Denver, Fort Worth, Jersey City, Los Angeles, New York City, Newark, Oakland, San Francisco, and Washington, D.C.

Markets in the file serve BOS, DFW, ORD, DEN, LAX, JFK, LGA, EWR, OAK, SFO, and IAD. MIA is represented by Broward County as a regional proxy, not Miami proper. ATL, CLT, DTW, and PHL are not covered by the selected city snapshots. The direct city/metro matches cover 13,986 of 20,000 flight rows; the Broward proxy adds 1,268 MIA rows.

## Interpreting dates and prices

Listings and prices are from September 2026 snapshots, not historical 2022 listings or prices. Synthetic availability maps each Expedia sample travel date to a source-calendar date with the same month and weekday, choosing the closest day of the month. This keeps the season and weekday/weekend pattern for a demo; it is not actual 2022 availability or booking history. `source_template_date` records the donor date and `availability_is_synthetic` is true on every output row. The output includes only the 216 unique `flightDate` values present in the supplied flight sample, from 2022-04-17 through 2022-11-19, not every date in 2022. Source calendars provide 17,477,737 of 17,515,224 expected listing/date combinations (99.79%); 37,487 combinations are absent in the source calendar files and are omitted. Treat an omitted pair as unknown, not as unavailable.

`is_group_stay_candidate` is true for an entire home/apartment with positive nightly price and at least one person of capacity. The full listing file itself is not filtered, so other room types and unpriced listings remain available for analysis.

## Attribution

Source: Inside Airbnb, Get the Data: https://insideairbnb.com/get-the-data/. Inside Airbnb lists its data under Creative Commons Attribution 4.0 International: https://creativecommons.org/licenses/by/4.0/.
