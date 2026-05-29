# Harness Rounds

This package holds importable harness candidates by evolution round.

Layout:

```text
harness_factory/rounds/
  round_01/
    harness_a/
    harness_b/
```

Import names for `run_infer.py` use dotted module paths:

```bash
--harness_package harness_factory
--harness rounds.round_01.harness_a
```

Keep one harness per directory. Each harness directory should export
`build_agent_from_context(context)` from its `__init__.py` or builder module,
matching `harness_factory/base_harness`.
