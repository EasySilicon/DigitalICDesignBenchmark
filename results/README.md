# Model result archive

This directory stores machine-readable benchmark runs for publication.  Each
model has one directory containing `summary.json` and one `Txx.json` record per
task.  A result record reports the measurements that were actually available;
missing PPA or time components remain `null` and are never silently converted
to zero.

The archive distinguishes three result classes:

- `official`: generated from one frozen benchmark revision and tool image with
  all release gates satisfied;
- `pre_release_pilot`: useful engineering evidence collected while the suite
  or evaluator was still changing;
- `diagnostic`: incomplete or targeted runs that are not comparable as a full
  benchmark result.

`ranking_eligible` must be `true` before a result can be used in a public model
ranking.  The task records intentionally exclude hidden vectors, evaluator
source, private filesystem paths, conversations, and candidate RTL.

The initial archived run is [gpt-6-sol](gpt-6-sol/README.md).

