# gpt-6-sol pre-release pilot

This archive reconciles the latest retained `gpt-6-sol` evidence with the
current 1 GHz scoring method.  It is a pre-release pilot and is not eligible
for a model ranking.  T01 and T02 have current-task functional results but no
retained current-task 1 GHz candidate PPA measurement, so their PPA and time
fields are `null`.

| Task | Function /75 | PPA /20 | Time /5 | Display subtotal | Status |
| --- | ---: | ---: | ---: | ---: | --- |
| T01 | 75 | — | — | 75.000 | PPA not measured |
| T02 | 75 | — | — | 75.000 | PPA not measured |
| T03 | 75 | 13.765 | 4.639 | 93.404 | scored |
| T04 | 75 | 14.408 | 4.656 | 94.065 | scored |
| T05 | 75 | 13.440 | 4.728 | 93.168 | scored |
| T06 | 75 | 14.040 | 4.745 | 93.786 | scored |
| T07 | 75 | 16.068 | 4.853 | 95.921 | scored |
| T08 | 75 | 0 | 0 | 75.000 | 1 GHz physical gate failed |
| T09 | 60.5 | 0 | 0 | 60.500 | functional gate failed |
| T10 | 62.5 | 0 | 0 | 62.500 | full-range MX functional gate failed |

The run passed all functional groups on 8 of 10 tasks and obtained 723/750
functional points.  PPA and time sum to 71.722 and 23.622 points over the
available records.  The 818.343 display subtotal omits the unmeasured T01/T02
PPA and time components and therefore is not a score out of 1000.

See [summary.json](summary.json) for suite-level metadata and `T01.json`
through `T10.json` for task-level evidence.  The original pilot was collected
across several pre-release revisions; T10 was rescored from the same candidate
after the full-range MX and automatic mesh rules were restored.

