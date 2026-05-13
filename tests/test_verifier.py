"""Verifier MVP — three-layer audit, registry, BYO LLM, schema/regex domain layers.

These tests are the contract for the Phase 1 Verifier: a stdlib-only,
trajectory-aware audit framework with composable verifier layers and a
clean BYO-LLM boundary.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

# ──────────────────────────────────────────────────────────────────────────
# Verdict + VerdictStatus
# ──────────────────────────────────────────────────────────────────────────


def test_verdict_constructs_with_required_fields() -> None:
    """``Verdict`` exposes the documented public fields."""
    from primal_ai import Verdict, VerdictStatus

    v = Verdict(
        verifier_name="rule_based",
        status=VerdictStatus.PASS,
        confidence=1.0,
        reasons=["all rules passed"],
        details={"rule_count": 3},
    )
    assert v.verifier_name == "rule_based"
    assert v.status == VerdictStatus.PASS
    assert v.confidence == pytest.approx(1.0)
    assert v.reasons == ["all rules passed"]
    assert v.details == {"rule_count": 3}
    assert v.cost is None
    assert v.latency_ms is None


def test_verdict_to_dict_is_json_serializable() -> None:
    """``Verdict.to_dict()`` round-trips through ``json.dumps``."""
    from primal_ai import Verdict, VerdictStatus

    v = Verdict(
        verifier_name="x",
        status=VerdictStatus.UNCERTAIN,
        confidence=0.3,
        reasons=["?"],
        details={},
        cost=0.001,
    )
    blob = json.dumps(v.to_dict())
    parsed = json.loads(blob)
    assert parsed["verifier_name"] == "x"
    assert parsed["status"] == "UNCERTAIN"


def test_verdict_from_dict_round_trips() -> None:
    """``Verdict.from_dict`` rebuilds a verdict identical to ``to_dict``'s output."""
    from primal_ai import Verdict, VerdictStatus

    v = Verdict(
        verifier_name="r",
        status=VerdictStatus.FAIL,
        confidence=0.9,
        reasons=["bad output"],
        details={"got": 42},
        cost=0.01,
        latency_ms=12.0,
    )
    restored = Verdict.from_dict(v.to_dict())
    assert restored.verifier_name == v.verifier_name
    assert restored.status == v.status
    assert restored.confidence == pytest.approx(v.confidence)
    assert restored.reasons == v.reasons
    assert restored.details == v.details
    assert restored.cost == pytest.approx(v.cost)
    assert restored.latency_ms == pytest.approx(v.latency_ms)


def test_verdict_status_is_strenum_and_serializes_natively() -> None:
    """``VerdictStatus`` is a StrEnum, so json.dumps treats it as a string."""
    from primal_ai import VerdictStatus

    payload = json.dumps({"status": VerdictStatus.PASS})
    assert json.loads(payload) == {"status": "PASS"}


# ──────────────────────────────────────────────────────────────────────────
# Verifier.audit — facade behavior
# ──────────────────────────────────────────────────────────────────────────


def test_audit_with_no_layers_returns_uncertain() -> None:
    """An empty layer chain has nothing to judge — overall verdict is UNCERTAIN."""
    from primal_ai import Verifier

    result = Verifier.audit("anything")
    assert result["status"] == "UNCERTAIN"
    assert result["verdicts"] == []
    assert result["layer_count"] == 0


def test_audit_returns_pass_when_all_rules_pass() -> None:
    """If every layer returns PASS, the overall verdict is PASS."""
    from primal_ai import RuleBasedVerifier, Verifier

    rule = lambda out: ("pass", "looks good")  # noqa: E731
    layer = RuleBasedVerifier(rules=[rule])
    result = Verifier.audit({"answer": 1}, layers=[layer])
    assert result["status"] == "PASS"
    assert result["layer_count"] == 1


def test_audit_returns_fail_when_any_rule_fails() -> None:
    """A single FAIL anywhere in the chain → overall FAIL."""
    from primal_ai import RuleBasedVerifier, Verifier

    rule_pass = lambda out: ("pass", "ok")  # noqa: E731
    rule_fail = lambda out: ("fail", "nope")  # noqa: E731
    layer = RuleBasedVerifier(rules=[rule_pass, rule_fail])
    result = Verifier.audit("x", layers=[layer])
    assert result["status"] == "FAIL"


def test_audit_returns_uncertain_when_mixed_pass_and_uncertain() -> None:
    """Mixed PASS + UNCERTAIN with no FAIL → overall UNCERTAIN."""
    from primal_ai import RuleBasedVerifier, Verifier

    rule_pass = lambda out: ("pass", "ok")  # noqa: E731
    rule_unc = lambda out: ("uncertain", "dunno")  # noqa: E731
    layer = RuleBasedVerifier(rules=[rule_pass, rule_unc])
    result = Verifier.audit("x", layers=[layer])
    assert result["status"] == "UNCERTAIN"


def test_audit_accepts_trajectory_and_routes_trajectory_aware_layers() -> None:
    """A trajectory-aware layer sees the Trajectory; an output-only layer sees the OUTPUT data."""
    from primal_ai import RuleBasedVerifier, Trajectory, Verifier

    seen: list[Any] = []

    def trajectory_rule(target: Any) -> tuple[str, str]:
        seen.append(("trajectory", target))
        return "pass", "trajectory inspected"

    def output_rule(target: Any) -> tuple[str, str]:
        seen.append(("output", target))
        return "pass", "output inspected"

    traj_layer = RuleBasedVerifier(rules=[trajectory_rule], accepts_trajectory=True)
    out_layer = RuleBasedVerifier(rules=[output_rule], accepts_trajectory=False)

    with Trajectory.record() as tr:
        tr.record_output({"answer": "tokyo"})

    Verifier.audit(tr, layers=[traj_layer, out_layer])
    kinds = [k for k, _ in seen]
    assert kinds == ["trajectory", "output"]
    # The trajectory layer got the actual Trajectory.
    assert seen[0][1] is tr
    # The output layer got the OUTPUT step's data.
    assert seen[1][1] == {"answer": "tokyo"}


def test_audit_accepts_raw_output_and_routes_non_trajectory_layers() -> None:
    """A raw output passes straight to non-trajectory layers."""
    from primal_ai import RuleBasedVerifier, Verifier

    seen: list[Any] = []

    def rule(out: Any) -> tuple[str, str]:
        seen.append(out)
        return "pass", "ok"

    Verifier.audit({"answer": 42}, layers=[RuleBasedVerifier(rules=[rule])])
    assert seen == [{"answer": 42}]


def test_audit_continues_when_a_layer_raises() -> None:
    """A layer that raises becomes UNCERTAIN for that layer; subsequent layers still run."""
    from primal_ai import RuleBasedVerifier, Verifier, VerifierLayer

    class Exploder:
        name = "exploder"
        accepts_trajectory = False

        def verify(self, target: Any) -> Any:
            raise RuntimeError("boom")

    rule_pass = lambda out: ("pass", "ok")  # noqa: E731
    safe_layer = RuleBasedVerifier(rules=[rule_pass])

    bad_layer: VerifierLayer = Exploder()
    result = Verifier.audit("x", layers=[bad_layer, safe_layer])

    assert result["layer_count"] == 2
    statuses = [v["status"] for v in result["verdicts"]]
    assert "UNCERTAIN" in statuses
    # A raised layer + a PASS layer → overall UNCERTAIN (one UNCERTAIN, no FAIL).
    assert result["status"] == "UNCERTAIN"


# ──────────────────────────────────────────────────────────────────────────
# Registry
# ──────────────────────────────────────────────────────────────────────────


def test_register_verifier_makes_a_name_resolvable() -> None:
    """``register_verifier`` adds a name to the registry."""
    from primal_ai import RuleBasedVerifier, register_verifier
    from primal_ai.verifier import resolve_layer

    register_verifier("__test_custom", lambda: RuleBasedVerifier(rules=[]))
    try:
        resolved = resolve_layer("__test_custom")
        assert isinstance(resolved, RuleBasedVerifier)
    finally:
        # Restore registry — we don't want to leak test state across tests.
        from primal_ai.verifier import _core as core_mod

        core_mod._REGISTRY.pop("__test_custom", None)


def test_audit_resolves_string_layer_via_registry() -> None:
    """``Verifier.audit(..., layers=['name'])`` looks the name up in the registry."""
    from primal_ai import RuleBasedVerifier, Verifier, register_verifier

    rule_pass = lambda out: ("pass", "ok")  # noqa: E731
    register_verifier(
        "__test_passes",
        lambda: RuleBasedVerifier(rules=[rule_pass], name="__test_passes"),
    )
    try:
        result = Verifier.audit("x", layers=["__test_passes"])
        assert result["status"] == "PASS"
    finally:
        from primal_ai.verifier import _core as core_mod

        core_mod._REGISTRY.pop("__test_passes", None)


def test_unknown_layer_name_raises_value_error_listing_registry() -> None:
    """An unknown DSL name raises ``ValueError`` listing the registered names."""
    from primal_ai import Verifier

    with pytest.raises(ValueError) as exc:
        Verifier.audit("x", layers=["__definitely_not_registered"])
    msg = str(exc.value)
    assert "__definitely_not_registered" in msg
    assert "rule_based" in msg or "json_schema" in msg


def test_set_default_layers_is_used_when_layers_is_none() -> None:
    """When ``layers=None``, the default chain (configurable) is used."""
    from primal_ai import RuleBasedVerifier, Verifier

    rule_pass = lambda out: ("pass", "ok")  # noqa: E731
    Verifier.set_default_layers([RuleBasedVerifier(rules=[rule_pass])])
    try:
        result = Verifier.audit("anything")
        assert result["status"] == "PASS"
    finally:
        Verifier.set_default_layers([])


# ──────────────────────────────────────────────────────────────────────────
# RuleBasedVerifier
# ──────────────────────────────────────────────────────────────────────────


def test_rule_based_aggregates_any_fail_to_fail() -> None:
    """Within one ``RuleBasedVerifier``, any FAIL among the rules → layer FAILs."""
    from primal_ai import RuleBasedVerifier, VerdictStatus

    layer = RuleBasedVerifier(
        rules=[
            lambda out: ("pass", "1"),
            lambda out: ("fail", "2"),
            lambda out: ("pass", "3"),
        ],
    )
    verdict = layer.verify("x")
    assert verdict.status == VerdictStatus.FAIL


def test_rule_based_aggregates_all_pass_to_pass() -> None:
    """All rules PASS → layer PASS."""
    from primal_ai import RuleBasedVerifier, VerdictStatus

    layer = RuleBasedVerifier(
        rules=[lambda out: ("pass", "1"), lambda out: ("pass", "2")],
    )
    assert layer.verify("x").status == VerdictStatus.PASS


def test_rule_based_aggregates_mixed_to_uncertain() -> None:
    """PASS + UNCERTAIN with no FAIL → layer UNCERTAIN."""
    from primal_ai import RuleBasedVerifier, VerdictStatus

    layer = RuleBasedVerifier(
        rules=[lambda out: ("pass", "1"), lambda out: ("uncertain", "?")],
    )
    assert layer.verify("x").status == VerdictStatus.UNCERTAIN


def test_rule_based_coerces_string_status_to_enum() -> None:
    """A rule returning the string ``"pass"`` is coerced to ``VerdictStatus.PASS``."""
    from primal_ai import RuleBasedVerifier, VerdictStatus

    layer = RuleBasedVerifier(rules=[lambda out: ("pass", "ok")])
    assert layer.verify("x").status == VerdictStatus.PASS


def test_rule_based_with_accepts_trajectory_can_walk_steps() -> None:
    """A trajectory-aware ``RuleBasedVerifier`` rule may call ``.find_steps``."""
    from primal_ai import RuleBasedVerifier, StepKind, Trajectory, VerdictStatus

    def has_an_output(target: Any) -> tuple[str, str]:
        outputs = target.find_steps(kind=StepKind.OUTPUT)
        return ("pass", "found output") if outputs else ("fail", "no output step")

    layer = RuleBasedVerifier(rules=[has_an_output], accepts_trajectory=True)

    with Trajectory.record() as tr:
        tr.record_output({"answer": 1})

    assert layer.verify(tr).status == VerdictStatus.PASS


# ──────────────────────────────────────────────────────────────────────────
# BYOLLMJudge
# ──────────────────────────────────────────────────────────────────────────


def test_byo_llm_judge_calls_user_callable_with_prompt() -> None:
    """The user's ``call_llm`` is invoked with a fully-formatted prompt."""
    from primal_ai import BYOLLMJudge

    seen: list[str] = []

    def fake_llm(prompt: str) -> str:
        seen.append(prompt)
        return "PASS\nlooks correct"

    judge = BYOLLMJudge(call_llm=fake_llm)
    judge.verify("the agent answered 42")
    assert len(seen) == 1
    assert "42" in seen[0]


def test_byo_llm_judge_parses_pass() -> None:
    """A response starting with ``PASS`` becomes ``VerdictStatus.PASS``."""
    from primal_ai import BYOLLMJudge, VerdictStatus

    judge = BYOLLMJudge(call_llm=lambda _prompt: "PASS\nreason here")
    assert judge.verify("x").status == VerdictStatus.PASS


def test_byo_llm_judge_parses_fail() -> None:
    """A response starting with ``FAIL`` becomes ``VerdictStatus.FAIL``."""
    from primal_ai import BYOLLMJudge, VerdictStatus

    judge = BYOLLMJudge(call_llm=lambda _prompt: "FAIL\nbecause X")
    assert judge.verify("x").status == VerdictStatus.FAIL


def test_byo_llm_judge_falls_back_to_uncertain_on_unparseable_response() -> None:
    """A response that doesn't start with PASS/FAIL/UNCERTAIN → UNCERTAIN."""
    from primal_ai import BYOLLMJudge, VerdictStatus

    judge = BYOLLMJudge(call_llm=lambda _prompt: "i have no opinion")
    assert judge.verify("x").status == VerdictStatus.UNCERTAIN


def test_byo_llm_judge_records_raw_response_in_details() -> None:
    """The raw model response is preserved under ``Verdict.details``."""
    from primal_ai import BYOLLMJudge

    judge = BYOLLMJudge(call_llm=lambda _prompt: "PASS\nbecause it answers the question")
    verdict = judge.verify("x")
    assert "because it answers the question" in verdict.details.get("response", "")


# ──────────────────────────────────────────────────────────────────────────
# JSONSchemaVerifier
# ──────────────────────────────────────────────────────────────────────────


def test_json_schema_verifier_passes_on_matching_output() -> None:
    """A matching output passes the schema verifier."""
    from primal_ai import JSONSchemaVerifier, VerdictStatus

    schema = {
        "type": "object",
        "required": ["answer"],
        "properties": {"answer": {"type": "string"}},
    }
    layer = JSONSchemaVerifier(schema=schema)
    assert layer.verify({"answer": "tokyo"}).status == VerdictStatus.PASS


def test_json_schema_verifier_fails_with_reason_on_type_mismatch() -> None:
    """A type mismatch yields FAIL with the offending path in the reason."""
    from primal_ai import JSONSchemaVerifier, VerdictStatus

    schema = {"type": "object", "properties": {"answer": {"type": "string"}}}
    layer = JSONSchemaVerifier(schema=schema)
    verdict = layer.verify({"answer": 42})
    assert verdict.status == VerdictStatus.FAIL
    assert any("answer" in r for r in verdict.reasons)


def test_json_schema_verifier_fails_when_required_field_missing() -> None:
    """A missing required field yields FAIL with a missing-field reason."""
    from primal_ai import JSONSchemaVerifier, VerdictStatus

    schema = {"type": "object", "required": ["answer"]}
    layer = JSONSchemaVerifier(schema=schema)
    verdict = layer.verify({})
    assert verdict.status == VerdictStatus.FAIL
    assert any("answer" in r for r in verdict.reasons)


# ──────────────────────────────────────────────────────────────────────────
# RegexMatchVerifier
# ──────────────────────────────────────────────────────────────────────────


def test_regex_match_verifier_passes_when_all_required_hit_and_none_forbidden() -> None:
    """All ``must_match`` patterns hit AND no ``must_not_match`` hit → PASS."""
    from primal_ai import RegexMatchVerifier, VerdictStatus

    layer = RegexMatchVerifier(must_match=[r"\bOK\b"], must_not_match=[r"ERROR"])
    assert layer.verify("status: OK").status == VerdictStatus.PASS


def test_regex_match_verifier_fails_with_reasons_listing_misses() -> None:
    """Each missed required pattern (or forbidden hit) shows up in the reasons."""
    from primal_ai import RegexMatchVerifier, VerdictStatus

    layer = RegexMatchVerifier(must_match=[r"\bSUCCESS\b"], must_not_match=[r"\bERROR\b"])
    verdict = layer.verify("status: ERROR")
    assert verdict.status == VerdictStatus.FAIL
    joined = " | ".join(verdict.reasons)
    assert "SUCCESS" in joined
    assert "ERROR" in joined


# ──────────────────────────────────────────────────────────────────────────
# Aggregation: confidence + cost
# ──────────────────────────────────────────────────────────────────────────


def test_aggregate_confidence_is_mean_of_layer_confidences() -> None:
    """``aggregate_confidence`` is the simple mean of every layer's confidence."""
    from primal_ai import RuleBasedVerifier, Verifier

    # Two rules, both pass, each yields confidence 1.0 → mean is 1.0.
    layers = [
        RuleBasedVerifier(rules=[lambda out: ("pass", "a")]),
        RuleBasedVerifier(rules=[lambda out: ("pass", "b")]),
    ]
    result = Verifier.audit("x", layers=layers)
    assert result["aggregate_confidence"] == pytest.approx(1.0)


def test_total_cost_sums_layer_costs_and_is_none_when_all_none() -> None:
    """``total_cost`` sums non-None costs; remains ``None`` if every layer has no cost."""
    from primal_ai import BYOLLMJudge, RuleBasedVerifier, Verifier

    # All None → total None.
    result_a = Verifier.audit(
        "x",
        layers=[RuleBasedVerifier(rules=[lambda out: ("pass", "a")])],
    )
    assert result_a["total_cost"] is None

    # One LLM judge with cost via a stub call_llm → total non-None.
    judge = BYOLLMJudge(
        call_llm=lambda _p: "PASS\nok",
        per_call_cost=0.002,
    )
    result_b = Verifier.audit("x", layers=[judge])
    assert result_b["total_cost"] == pytest.approx(0.002)


# ──────────────────────────────────────────────────────────────────────────
# Shared _jsonschema lift
# ──────────────────────────────────────────────────────────────────────────


def test_shared_jsonschema_validate_raises_valueerror_on_mismatch() -> None:
    """The shared ``_jsonschema.validate`` raises ``ValueError`` on bad data."""
    from primal_ai._jsonschema import validate

    validate({"type": "object", "required": ["k"]}, {"k": 1})  # passes silently
    with pytest.raises(ValueError):
        validate({"type": "object", "required": ["k"]}, {})
