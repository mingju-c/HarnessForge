"""Regression tests for the shared, model-free mixed-task SFT pipeline."""
from __future__ import annotations

import ast
import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest

ROOT = Path(__file__).resolve().parents[1]


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


sft = load_module("shared_mixed_sft", ROOT / "tools/prepare_mixed_sft.py")
SOURCE = dict(round_id="round01", harness="rounds.r1.h1", policy_id="policy0", dataset_id="evolution_r1", data_split="evolution")


def msg(role, text):
    return {"role": role, "content": [{"type": "text", "text": text}]}


def call(name, **arguments):
    return msg("assistant", "Calling tools:\n" + repr({"tools": [{"name": name, "arguments": arguments, "id": "call_1"}]}))


def row(benchmark="envscaler", index=1, score=1.0):
    return {
        "item_index": index, "question": f"Task {index}", "mixed_benchmark": benchmark,
        "provenance": copy.deepcopy(SOURCE), "scoring_version": sft.SCORING_VERSION,
        "status": "success", "score": score, "envscaler_score": score, "envscaler_done": 1,
        "answer_correct": 1, "path_score": 2 * score - 1, "answer_f1": score,
        "agent_messages": [
            msg("system", "Use the supplied tools."),
            msg("user", f"New task:\nTask {index}"),
            msg("assistant", "[PLAN]: inspect the state, then call complete_task if done."),
            msg("user", "Choose the next action."), call("inspect", key="state"),
            msg("tool-response", "Tool calling observation:\nready"),
            call("complete_task" if benchmark == "envscaler" else "final_answer", answer="ready"),
            msg("tool-response", "completed"), msg("assistant", "completed"),
        ],
    }


class MixedSFTTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.config = sft.load_config(None)
        self.config["eval_ratio"] = 0

    def inputs(self, rows, manifest_update=None):
        source = self.base / "results.jsonl"
        source.write_text("".join(json.dumps(record) + "\n" for record in rows))
        manifest = {**SOURCE, "sources": [source.name], **(manifest_update or {})}
        path = self.base / "sources.json"
        path.write_text(json.dumps(manifest))
        return path

    def build(self, rows, name="out", allow_declared=False, manifest_update=None):
        manifest = self.inputs(rows, manifest_update)
        out = self.base / name
        stats = sft.build_dataset(manifest, out, "test", self.config, allow_declared)
        return stats, out

    def test_all_families_keep_plan_action_terminal_and_mask_observations(self):
        stats, out = self.build([row("envscaler", 1), row("searchqa", 2), row("toolhop", 3)])
        self.assertEqual(stats["accepted_trajectories"], 3)
        self.assertEqual(stats["cleaning_actions"]["kept_terminal_action"], 3)
        self.assertEqual(stats["cleaning_actions"]["dropped_terminal_echo_or_tail"], 6)
        records = [json.loads(line) for line in (out / "train.jsonl").read_text().splitlines()]
        for record in records:
            messages = record["messages"]
            self.assertEqual(record["system"], "Use the supplied tools.")
            self.assertEqual([m["role"] for m in messages], ["user", "assistant"] * 3)
            self.assertIn("[PLAN]", messages[1]["content"])
            self.assertIn("[Tool observation]", messages[4]["content"])
            self.assertIn("Calling tools:", messages[-1]["content"])
            self.assertEqual(record["metadata"]["provenance_check"], "row_metadata_matched")
        self.assertEqual(json.loads((out / "training_options.json").read_text()), {"mask_history": False, "train_on_prompt": False})
        self.assertEqual(json.loads((out / "dataset_info.json").read_text())["test_train"]["formatting"], "sharegpt")

    def test_final_acceptance_rules_and_environment_threshold_boundaries(self):
        records = [row("envscaler", 1, .9), row("envscaler", 2, .8999),
                   row("searchqa", 3, 1), row("toolhop", 4, 1),
                   row("searchqa", 5, .999999), row("toolhop", 6, .999999)]
        stats, _ = self.build(records)
        self.assertEqual(stats["accepted_trajectories"], 3)
        self.assertEqual(stats["rejections"], {"below_score_threshold": 1, "qa_score_not_perfect": 2})
        # Thresholds apply to the environment reward, including when the
        # duplicate score field differs by less than the consistency tolerance.
        near_boundary = row(score=.9); near_boundary["envscaler_score"] = .8999999
        with self.assertRaisesRegex(sft.Reject, "below_score_threshold"):
            sft.validate_score(near_boundary, "envscaler", self.config)

    def test_qa_requires_correct_answer_even_when_f1_is_perfect(self):
        for benchmark in ("searchqa", "toolhop"):
            record = row(benchmark); record["answer_correct"] = 0
            with self.subTest(benchmark=benchmark), self.assertRaisesRegex(sft.Reject, f"{benchmark}_answer_incorrect"):
                sft.validate_score(record, benchmark, self.config)
        # Token F1 can be one for a reordered answer while exact match is zero.
        record = row("searchqa")
        record.update(answer_f1=1.0, score=1.0, answer_correct=0.0)
        stats, _ = self.build([record])
        self.assertEqual(stats["rejections"], {"searchqa_answer_incorrect": 1})

    def test_final_configs_share_acceptance_and_do_not_relax_qa(self):
        for mode in ("full", "prefix"):
            config = sft.load_config(ROOT / f"examples/mixed_sft/final_{mode}.json")
            self.assertEqual(config["sample_mode"], mode)
            self.assertEqual(config["min_scores"], {"toolhop": 1.0, "searchqa": 1.0, "envscaler": .9})
            self.assertEqual(sft.validate_score(row(score=.9), "envscaler", config), .9)
        invalid = self.base / "relaxed_qa.json"
        invalid.write_text(json.dumps({"min_scores": {"toolhop": 1, "searchqa": .9, "envscaler": .9}}))
        with self.assertRaisesRegex(ValueError, "QA score thresholds must be 1"):
            sft.load_config(invalid)

    def test_score_components_and_completion_are_checked(self):
        bad_env = row(score=.9); bad_env["envscaler_done"] = 0
        bad_qa = row("toolhop", 2); bad_qa["answer_correct"] = 0
        inconsistent = row("searchqa", 3); inconsistent["answer_f1"] = .5
        nonfinite = row("envscaler", 4); nonfinite["score"] = float("nan")
        stats, _ = self.build([bad_env, bad_qa, inconsistent, nonfinite])
        self.assertEqual(stats["accepted_trajectories"], 0)
        self.assertEqual(set(stats["rejections"]), {"envscaler_not_done", "toolhop_answer_incorrect", "score_component_mismatch", "missing_or_invalid_metric:score"})

    def test_failed_calls_reject_whole_trajectory(self):
        for marker in ("ROUND01_GUARD_BLOCK", "Error:\nfailed", "Unknown tool", "ROUND01_PARTIAL_COMMIT"):
            record = row()
            record["agent_messages"][5] = msg("tool-response", marker)
            with self.subTest(marker=marker), self.assertRaisesRegex(sft.Reject, "failed_or_guarded"):
                sft.clean_dialogue(record, "envscaler", self.config)
        record = row(); record["agent_trajectory"] = [{"error": "failed"}]
        with self.assertRaisesRegex(sft.Reject, "trajectory_execution_error"):
            sft.clean_dialogue(record, "envscaler", self.config)

    def test_stateful_repeated_actions_are_preserved(self):
        record = row()
        record["agent_messages"][6:6] = [call("inspect", key="state"), msg("tool-response", "still ready")]
        messages, _, _ = sft.clean_dialogue(record, "envscaler", self.config)
        self.assertEqual(sum("'name': 'inspect'" in m["content"] for m in messages), 2)

    def test_invalid_transitions_and_terminal_contracts(self):
        cases = []
        r = row(); r["agent_messages"].append(call("inspect")); cases.append((r, "tool_call_after_terminal"))
        r = row(); del r["agent_messages"][5]; cases.append((r, "missing_tool_observation"))
        r = row(); r["agent_messages"][6] = call("final_answer"); cases.append((r, "wrong_terminal_tool"))
        r = row(); r["agent_messages"] = r["agent_messages"][:6]; cases.append((r, "missing_terminal_action"))
        r = row(); r["agent_messages"][4] = msg("assistant", "Calling tools:\nnot valid"); cases.append((r, "malformed_tool_payload"))
        r = row(); r["agent_messages"].insert(1, msg("tool", "orphan")); cases.append((r, "orphan_tool_observation"))
        for record, reason in cases:
            with self.subTest(reason=reason), self.assertRaisesRegex(sft.Reject, reason):
                sft.clean_dialogue(record, "envscaler", self.config)

    def test_native_calls_and_environment_terminal_alias(self):
        record = row()
        record["agent_messages"][6] = {"role": "assistant", "content": None, "tool_calls": [{"function": {
            "name": "chat_with_user", "arguments": json.dumps({"content": "Task Completed"}),
        }}]}
        messages, _, _ = sft.clean_dialogue(record, "envscaler", self.config)
        self.assertIn("chat_with_user", messages[-1]["content"])
        self.assertIsNone(sft.terminal_domain({"name": "chat_with_user", "arguments": {"content": None}}))

    def test_provenance_required_and_override_is_audited(self):
        record = row(); del record["provenance"]
        with self.assertRaisesRegex(ValueError, "lack provenance"):
            self.build([record])
        stats, out = self.build([record], allow_declared=True)
        self.assertEqual(stats["provenance_checks"], {"manifest_declared": 1})
        self.assertTrue(json.loads((out / "manifest.json").read_text())["allow_declared_provenance"])

    def test_conflicting_round_pair_dataset_or_test_split_fails_even_with_override(self):
        for key in SOURCE:
            record = row(); record["provenance"][key] = "different"
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, "conflicts"):
                self.build([record], allow_declared=True)
        for split in ("validation", "test", "unspecified"):
            with self.subTest(split=split), self.assertRaisesRegex(ValueError, "never validation or test"):
                self.build([row()], manifest_update={"data_split": split})

    def test_legacy_scores_cannot_be_silently_relabelled(self):
        record = row(); del record["scoring_version"]
        with self.assertRaisesRegex(ValueError, "re-score"):
            self.build([record], allow_declared=True)

    def test_task_deduplication_keeps_shorter_trace_and_audits_other(self):
        long = row(); long["agent_messages"][2]["content"][0]["text"] += " more planning" * 10
        short = row()
        stats, out = self.build([long, short])
        self.assertEqual(stats["accepted_trajectories"], 1)
        self.assertEqual(stats["rejections"], {"duplicate_task": 1})
        audit = [json.loads(line) for line in (out / "audit.jsonl").read_text().splitlines()]
        self.assertEqual([item["decision"] for item in audit], ["rejected", "accepted"])
        self.build([short, long], "reversed")
        a = json.loads((out / "train.jsonl").read_text())["messages"]
        b = json.loads((self.base / "reversed/train.jsonl").read_text())["messages"]
        self.assertEqual(a, b)

    def test_task_split_precedes_prefix_expansion_and_is_stable(self):
        self.config.update(sample_mode="prefix", eval_ratio=.5)
        records = [row(index=i) for i in range(1, 31)]
        # Different IDs with identical questions must stay in the same partition.
        records[1]["question"] = records[0]["question"].upper()
        stats, out = self.build(records)
        self.assertGreater(stats["samples_by_partition"]["train"], 0)
        self.assertGreater(stats["samples_by_partition"]["eval"], 0)
        groups = {}
        for name in ("train", "eval"):
            samples = [json.loads(line) for line in (out / f"{name}.jsonl").read_text().splitlines()]
            for sample in samples:
                key = sample["metadata"]["split_key"]
                self.assertEqual(groups.setdefault(key, name), name)
        self.assertTrue(json.loads((out / "training_options.json").read_text())["mask_history"])
        _, other = self.build(records[::2][::-1], "subset")
        for name in ("train", "eval"):
            for line in (other / f"{name}.jsonl").read_text().splitlines():
                self.assertEqual(groups[json.loads(line)["metadata"]["split_key"]], name)

    def test_output_preservation_and_manifest_source_hashes(self):
        _, out = self.build([row()])
        info = json.loads((out / "manifest.json").read_text())
        self.assertEqual(len(info["source_file_sha256"]), 1)
        self.assertEqual(len(info["script_sha256"]), 64)
        with self.assertRaisesRegex(ValueError, "not empty"):
            self.build([row()])

    def test_both_workspace_commands_produce_same_data(self):
        manifest = self.inputs([row(score=.9)])
        config = self.base / "config.json"; config.write_text(json.dumps(self.config))
        outputs = []
        for workspace in ("HarnessForge_4B", "HarnessForge_8B"):
            out = self.base / workspace
            result = subprocess.run([sys.executable, str(ROOT / workspace / "tools/prepare_mixed_sft.py"),
                "--manifest", str(manifest), "--output-dir", str(out), "--dataset-name", "fixture", "--config", str(config)],
                text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            outputs.append((out / "train.jsonl").read_bytes())
        self.assertEqual(*outputs)

    def test_cli_empty_acceptance_is_failure_with_audit(self):
        manifest = self.inputs([row(score=.5)])
        out = self.base / "empty"
        result = subprocess.run([sys.executable, str(ROOT / "tools/prepare_mixed_sft.py"), "--manifest", str(manifest),
            "--output-dir", str(out), "--dataset-name", "fixture"], text=True, capture_output=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("No training samples", result.stderr)
        self.assertTrue((out / "audit.jsonl").exists())

    def test_runner_provenance_checks_both_workspaces(self):
        source = self.base / "input.jsonl"; source.write_text('{}\n')
        args = SimpleNamespace(registry_round="round01", registry_dataset="evolution_r1", harness="rounds.r1.h1",
            model_alias="policy0", data_split="evolution", model_adapter=None)
        for workspace in ("HarnessForge_4B", "HarnessForge_8B"):
            mod = load_module("provenance", ROOT / workspace / "tools/rollout_provenance.py")
            expected = mod.build_rollout_provenance(args, str(source), "actual-model")
            self.assertEqual({key: expected[key] for key in SOURCE}, SOURCE)
            self.assertEqual(len(expected["input_sha256"]), 64)
            mod.validate_resume_provenance([{"provenance": expected}], expected)
            with self.assertRaisesRegex(ValueError, "conflicting rollout provenance"):
                mod.validate_resume_provenance([{}], expected)
            with self.assertRaisesRegex(ValueError, "conflicting rollout provenance"):
                mod.validate_resume_provenance([{"provenance": {**expected, "data_split": "test"}}], expected)

    def test_training_options_match_bundled_trainer_argument_names(self):
        tree = ast.parse((ROOT / "LlamaFactory/src/llamafactory/hparams/data_args.py").read_text())
        fields = {node.target.id for node in ast.walk(tree) if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name)}
        self.config["sample_mode"] = "prefix"
        _, out = self.build([row()])
        options = json.loads((out / "training_options.json").read_text())
        self.assertTrue(set(options) <= fields)
        self.assertEqual(options, {"mask_history": True, "train_on_prompt": False})


if __name__ == "__main__":
    unittest.main()
