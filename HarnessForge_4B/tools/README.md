# Tools

See the [tool directory index](../../docs/tools_index.md) for each script's
purpose, workspace availability, and the removed utilities.

`run_infer.py` depends on `rollout_provenance.py` and, when registry recording
is enabled, `harness_pool_registry.py`. `half_select_harnesses.py` performs
candidate selection. Do not delete the directory as a whole.

For mixed-task SFT, use `prepare_mixed_sft.py` and follow the
[shared recipe](../../docs/mixed_sft.md). The older standalone ToolHop and
trainer-bundle exporters are optional utilities with different policies.
