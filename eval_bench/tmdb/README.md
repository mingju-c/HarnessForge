# RestBench-TMDB Eval Bench

This directory contains `datasets/tmdb.json`, `specs/tmdb_oas.json`, the RestBench runtime wrapper, and env templates for optional live TMDB calls.

By default, RestBench-TMDB can evaluate endpoint selection without external TMDB credentials. Live endpoint execution requires a TMDB credential:

```bash
TMDB_ACCESS_TOKEN=<tmdb-v4-read-access-token>
# or
TMDB_API_KEY=<tmdb-v3-api-key>
```

Benchmark-specific aliases are also supported:

```bash
RESTBENCH_TMDB_ACCESS_TOKEN=<tmdb-v4-read-access-token>
RESTBENCH_TMDB_API_KEY=<tmdb-v3-api-key>
```

Get credentials from your TMDB account API settings after creating/logging into a TMDB account: https://www.themoviedb.org/settings/api. See also the TMDB developer docs: https://developer.themoviedb.org/docs/getting-started.
