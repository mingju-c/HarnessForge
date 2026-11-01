"""Run for each workspace with HF_TEST_WORKSPACE=HarnessForge_4B (or _8B)."""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT / os.environ.get("HF_TEST_WORKSPACE", "HarnessForge_4B")
sys.path.insert(0, str(WORKSPACE))

from mixeddata.evaluation import (
    evaluate_mixeddata_item,
    summarize_mixeddata_results,
    validate_mixeddata_scoring_items,
)
from mixeddata.mixed_reward import SCORING_VERSION, compute_score
from tools import half_select_harnesses as selection
from tools import harness_pool_registry as registry


def qa(prediction, gold, **extra):
    return compute_score("searchqa", json.dumps({"answer": prediction}), gold, extra)


def env(score):
    row = compute_score("envscaler", "", None, {
        "rollout_reward_scores": {"envscaler_score": score, "envscaler_done": 1},
    })
    row.update(status="success", metrics={"total_tokens": 100, "elapsed_time": 2})
    return row


class MixedScoringTests(unittest.TestCase):
    def test_normalized_token_f1(self):
        cases = [
            ("New York", ["New York City"], 0.8),
            ("New York City USA", ["New York City"], 6 / 7),
            ("The NEW, York City!", ["new york city"], 1.0),
            ("red red blue", ["red blue"], 0.8),
            ("NYC", ["New York City", "NYC"], 1.0),
            ("unrelated", ["New York City"], 0.0),
            ("", ["Paris"], 0.0),
            ("Paris", [], 0.0),
        ]
        for predicted, gold, expected in cases:
            with self.subTest(predicted=predicted, gold=gold):
                result = qa(predicted, gold)
                self.assertAlmostEqual(result["score"], expected)
                self.assertEqual(result["score"], result["answer_f1"])
                self.assertEqual(result["scoring_version"], SCORING_VERSION)

    def test_toolhop_answer_and_path_are_independent(self):
        item = {"benchmark": "toolhop", "answer": "France", "sub_task": {"city": "Paris", "country": "France"}}
        for answer, observation, expected in [
            ("France", "", 0.5),
            ("France", "Paris", 0.75),
            ("France", "Paris, France", 1.0),
            ("wrong", "Paris, France", 0.5),
            ("France and Germany", "", 0.0),
        ]:
            with self.subTest(answer=answer, observation=observation):
                trajectory = [{"name": "action", "tool_calls": [{"name": "lookup"}], "obs": observation}]
                row = evaluate_mixeddata_item(item=item, pred_answer=answer, trajectory=trajectory)
                self.assertAlmostEqual(row["score"], expected)

    def test_final_answer_and_planning_do_not_count_as_path_evidence(self):
        item = {"benchmark": "toolhop", "answer": "France", "extra_info": {"sub_task": {"city": "Paris"}}}
        trajectory = [
            {"name": "planning", "tool_calls": [{"name": "lookup"}], "obs": "Paris"},
            {"name": "action", "tool_calls": [{"name": "final_answer"}], "obs": "Paris"},
        ]
        row = evaluate_mixeddata_item(item=item, pred_answer="Paris", trajectory=trajectory)
        self.assertEqual(row["path_score"], 0.0)
        self.assertEqual(row["score"], 0.0)

    def test_tool_json_answer_is_not_a_model_final_answer(self):
        item = {"benchmark": "toolhop", "answer": "Paris", "sub_task": {"city": "Paris"}}
        row = evaluate_mixeddata_item(item=item, pred_answer=None, trajectory=[{
            "name": "action", "tool_calls": [{"name": "lookup"}], "obs": '{"answer":"Paris"}',
        }])
        self.assertEqual(row["answer_correct"], 0.0)
        self.assertEqual(row["path_score"], 1.0)
        self.assertEqual(row["score"], 0.5)

    def test_canonical_benchmark_controls_scorer(self):
        row = evaluate_mixeddata_item(
            item={"benchmark": "toolhop", "data_source": "offline", "answer": "Paris", "sub_task": {"city": "Paris"}},
            pred_answer="Paris", trajectory=[],
        )
        self.assertEqual(row["score"], 0.5)
        for source in ("nq", "hotpotqa", "2wikimultihopqa", "offline"):
            with self.subTest(source=source):
                row = evaluate_mixeddata_item(
                    item={"data_source": source, "answer": "New York City"},
                    pred_answer="New York", trajectory=[],
                )
                self.assertEqual(row["mixed_benchmark"], "searchqa")
                self.assertEqual(row["score"], 0.8)

    def test_missing_toolhop_labels_fail_before_rollout(self):
        with self.assertRaisesRegex(ValueError, "sub_task"):
            validate_mixeddata_scoring_items([{"benchmark": "toolhop", "answer": "France"}])
        with self.assertRaisesRegex(ValueError, "sub_task"):
            compute_score("toolhop", '{"answer":"France"}', "France")
        validate_mixeddata_scoring_items([{
            "benchmark": "toolhop",
            "reward_model": {"ground_truth": {"answer": "France", "sub_task": {"city": "Paris"}}},
        }])

    def test_micro_average_includes_envscaler_without_changing_answer_fields(self):
        rows = [env(0.0), env(0.8), qa("Paris", ["Paris"])]
        summary = summarize_mixeddata_results(rows)
        self.assertAlmostEqual(summary["avg_score"], 0.6)  # macro average would be 0.7
        self.assertEqual(summary["score_aggregation"], "micro")
        self.assertEqual(summary["by_benchmark"]["envscaler"]["count"], 2)
        self.assertEqual(rows[1]["answer_correct"], 0.0)
        self.assertEqual(rows[1]["has_valid_answer"], 0.0)
        for summary_arg in ({}, summary):
            metrics = registry.merge_summary_metrics(
                result_summary=registry.summarize_results(rows), benchmark_summary=summary_arg,
            )
            self.assertAlmostEqual(metrics["primary_score"], 0.6)
            self.assertEqual(metrics["scoring_version"], SCORING_VERSION)

    def test_error_rows_remain_in_denominator(self):
        for stale_score in (None, 1.0):
            rows = [env(1.0), {"status": "error", "mixed_benchmark": "envscaler", "score": stale_score, "scoring_version": SCORING_VERSION}]
            with self.subTest(stale_score=stale_score):
                self.assertEqual(summarize_mixeddata_results(rows)["avg_score"], 0.5)
                self.assertEqual(registry.summarize_results(rows)["avg_score"], 0.5)

    def test_bad_scores_and_mixed_versions_are_rejected(self):
        for score in (float("nan"), float("inf"), -0.1, 1.1, None):
            row = env(0.0)
            row["score"] = score
            for summarize in (summarize_mixeddata_results, registry.summarize_results):
                with self.subTest(score=score, summarize=summarize.__name__):
                    with self.assertRaises(ValueError):
                        summarize([row])
        rows = [env(0.0), env(1.0)]
        rows[0].pop("scoring_version")
        for summarize in (summarize_mixeddata_results, registry.summarize_results):
            with self.assertRaisesRegex(ValueError, "scoring versions"):
                summarize(rows)

    def test_old_results_are_not_relabelled(self):
        old = env(0.8)
        old.pop("scoring_version")
        summary = summarize_mixeddata_results([old])
        self.assertEqual(summary["scoring_version"], "legacy_unversioned")
        merged = registry.merge_summary_metrics(result_summary=registry.summarize_results([old]), benchmark_summary=summary)
        self.assertEqual(merged["scoring_version"], "legacy_unversioned")

    def test_primary_score_has_no_cost_or_diagnostic_bonus(self):
        for diagnostic in (0.0, 1.0):
            self.assertEqual(registry.compute_primary_score({
                "avg_score": 0.75, "accuracy": diagnostic, "path_score": diagnostic,
                "valid_answer_rate": diagnostic, "avg_tool_calls": 100 * diagnostic,
            }), 0.75)


class SelectionTests(unittest.TestCase):
    def test_six_default_objectives_and_explicit_three_objective_mode(self):
        args = selection.parse_args(["--output", "unused.json"])
        self.assertEqual(args.quality_metric, ["primary_score", "accuracy", "valid_answer_rate"])
        self.assertEqual(args.cost_metric, ["avg_tokens", "avg_elapsed_time", "avg_tool_calls"])
        args = selection.parse_args([
            "--output", "unused.json", "--quality-metric", "primary_score",
            "--cost-metric", "avg_tokens", "--cost-metric", "avg_elapsed_time",
        ])
        self.assertEqual(args.quality_metric, ["primary_score"])
        self.assertEqual(args.cost_metric, ["avg_tokens", "avg_elapsed_time"])
        args = selection.parse_args([
            "--output", "unused.json", "--primary-metric", "accuracy",
            "--quality-metric", "accuracy", "--cost-metric", "avg_tool_calls",
        ])
        self.assertEqual(args.quality_metric, ["accuracy"])
        self.assertEqual(args.cost_metric, ["avg_tool_calls"])

    def test_registry_to_cli_selection_rewards_envscaler(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "registries/harness_pool.yaml"
            for name, score in [("low_env", 0.1), ("high_env", 0.9)]:
                row = env(score)
                registry.record_run_from_summary(
                    registry_path=path, project_root=root, harness=name, package="harness_factory",
                    round_id="round1", dataset="mixed", dataset_type="mixeddata", model_name="test",
                    run_id=name, result_summary=registry.summarize_results([row]),
                    benchmark_summary=summarize_mixeddata_results([row]),
                )
            output = root / "selection.json"
            command = [sys.executable, str(WORKSPACE / "tools/half_select_harnesses.py"),
                       "--registry-file", str(path), "--round", "round1", "--dataset", "mixed",
                       "--min-survivors", "1", "--output", str(output)]
            subprocess.run(command, check=True, capture_output=True, text=True)
            payload = json.loads(output.read_text())
            self.assertEqual(payload["selected"][0]["harness"], "high_env")
            self.assertEqual(payload["selected_count"], 1)
            self.assertEqual(payload["cost_metrics"], ["avg_tokens", "avg_elapsed_time", "avg_tool_calls"])
            self.assertEqual(payload["quality_metrics"], ["primary_score", "accuracy", "valid_answer_rate"])
            data = registry.load_registry(path)
            latest = data["harnesses"]["high_env"]["latest"]
            self.assertEqual(latest["primary_score"], latest["avg_score"])
            self.assertEqual(latest["scoring_version"], SCORING_VERSION)
            args = selection.parse_args(["--output", "unused.json"])
            for bad_metric in ("scoring_version", "avg_tokens", "avg_elapsed_time", "accuracy", "valid_answer_rate", "avg_tool_calls"):
                bad = copy.deepcopy(data)
                bad["harnesses"]["high_env"]["runs"][0]["metrics"].pop(bad_metric)
                with self.subTest(bad_metric=bad_metric):
                    with self.assertRaises(ValueError):
                        selection.collect_candidates(bad, args)

    def test_pareto_tradeoff_and_performance_tiebreak(self):
        args = selection.parse_args(["--output", "unused.json", "--min-survivors", "1"])
        rows = [
            {"harness": "fast", "run_id": "fast", "primary_score": 0.5,
             "quality": {"primary_score": 0.5, "accuracy": 0.5, "valid_answer_rate": 1.0},
             "cost": {"avg_tokens": 10, "avg_elapsed_time": 1, "avg_tool_calls": 2}},
            {"harness": "accurate", "run_id": "accurate", "primary_score": 0.8,
             "quality": {"primary_score": 0.8, "accuracy": 0.5, "valid_answer_rate": 1.0},
             "cost": {"avg_tokens": 20, "avg_elapsed_time": 2, "avg_tool_calls": 2}},
        ]
        self.assertEqual(len(selection.pareto_front(rows, args.quality_metric, args.cost_metric)), 2)
        self.assertEqual(selection.half_select(rows, args)[0]["harness"], "accurate")

    def test_extra_objectives_can_change_dominance_and_are_not_small_weights(self):
        a = {"quality": {"primary_score": 0.8, "accuracy": 0.6, "valid_answer_rate": 1},
             "cost": {"avg_tokens": 100, "avg_elapsed_time": 1, "avg_tool_calls": 2}}
        b = {"quality": {"primary_score": 0.7, "accuracy": 0.9, "valid_answer_rate": 1},
             "cost": {"avg_tokens": 100, "avg_elapsed_time": 1, "avg_tool_calls": 2}}
        args = selection.parse_args(["--output", "unused.json"])
        self.assertTrue(selection.dominates(a, b, ["primary_score"], ["avg_tokens", "avg_elapsed_time"]))
        self.assertFalse(selection.dominates(a, b, args.quality_metric, args.cost_metric))
        b["quality"]["accuracy"] = a["quality"]["accuracy"]
        a["cost"]["avg_tool_calls"] = 3
        self.assertFalse(selection.dominates(a, b, args.quality_metric, args.cost_metric))
        for candidate in (a, b):
            candidate["cost"]["avg_tool_calls"] *= 0.01
        self.assertFalse(selection.dominates(a, b, args.quality_metric, args.cost_metric))


if __name__ == "__main__":
    unittest.main()
