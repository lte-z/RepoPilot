from pathlib import Path

from repopilot.intent_agent import run_intent_router


def _write_config(tmp_path: Path, use_llm_router: bool = True) -> Path:
    outputs = tmp_path / "outputs"
    outputs.mkdir()
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        f"""
permissions:
  readable_roots:
    - {tmp_path.as_posix()}
  writable_roots:
    - {outputs.as_posix()}
  deny_patterns: []
intent:
  use_llm_router: {str(use_llm_router).lower()}
  fallback_to_rules: true
  min_confidence: 0.55
  max_prompt_context_chars: 2500
limits:
  intent_timeout_seconds: 1
""",
        encoding="utf-8",
    )
    return config_path


def test_intent_router_offline_uses_rule_fallback(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)

    decision = run_intent_router(
        "你还能做什么？",
        repo_path=str(tmp_path),
        config_path=config_path,
        offline=True,
    )

    assert decision.intent == "meta_help"
    assert decision.needs_tools is False
    assert decision.source == "fallback"


def test_intent_router_can_be_disabled_by_config(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path, use_llm_router=False)

    decision = run_intent_router(
        "怎么运行测试？",
        repo_path=str(tmp_path),
        config_path=config_path,
    )

    assert decision.intent == "repo_runbook"
    assert decision.needs_tools is True
    assert decision.mode == "runbook"
    assert decision.source == "fallback"
