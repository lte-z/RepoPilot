"""LLM-backed intent router for RepoPilot chat."""

from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path
from typing import Any, cast

from openai import AsyncOpenAI
from pydantic import ValidationError

from .config import load_config
from .intent import IntentDecision, IntentMode, classify_intent_by_rules, decision_from_rule


def _load_intent_prompt() -> str:
    path = Path(__file__).resolve().parent / "prompts" / "intent_prompt.md"
    return path.read_text(encoding="utf-8")


def _fallback_decision(message: str, has_context: bool, reason: str) -> IntentDecision:
    decision = decision_from_rule(classify_intent_by_rules(message, has_context), message)
    decision.source = "fallback"
    decision.reason = f"{decision.reason}；{reason}"
    return decision


def _extract_json(text: str) -> dict[str, Any]:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?\s*", "", stripped)
        stripped = re.sub(r"\s*```$", "", stripped)
    try:
        data = json.loads(stripped)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", stripped, re.S)
        if not match:
            raise
        data = json.loads(match.group(0))
    if not isinstance(data, dict):
        raise ValueError("Intent router 返回的 JSON 必须是对象。")
    return data


def _normalize_decision(decision: IntentDecision, message: str) -> IntentDecision:
    mode_by_intent = {
        "repo_overview": "overview",
        "repo_runbook": "runbook",
        "repo_module_map": "module-map",
        "repo_task_brief": "task-brief",
        "repo_deep_scan": "deep-scan",
    }
    expected_mode = mode_by_intent.get(decision.intent)
    if expected_mode:
        decision.needs_tools = True
        decision.mode = cast(IntentMode, expected_mode)
        if expected_mode == "task-brief" and not decision.task:
            decision.task = message
    else:
        decision.needs_tools = False
        decision.mode = None
        decision.task = None
    if decision.intent == "ambiguous" and not decision.clarifying_question:
        decision.clarifying_question = "我不确定你是想聊天、配置，还是分析仓库。可以说得更具体一点吗？"
    return decision


async def decide_intent(
    message: str,
    *,
    repo_path: str,
    context: str = "",
    has_context: bool = False,
    config_path: str | Path | None = None,
    offline: bool = False,
) -> IntentDecision:
    """Classify a natural-language turn before any MCP tool is exposed."""

    config = load_config(config_path)
    if offline:
        return _fallback_decision(message, has_context, "offline 模式使用规则回退")
    if not config.intent.use_llm_router:
        return _fallback_decision(message, has_context, "intent.use_llm_router=false")
    if not config.llm.api_key or not config.llm.base_url or not config.llm.model:
        if config.intent.fallback_to_rules:
            return _fallback_decision(message, has_context, "LLM 配置不完整")
        return IntentDecision(
            intent="ambiguous",
            confidence=0,
            needs_tools=False,
            clarifying_question="缺少 LLM 配置，无法进行意图识别。请配置 API Key，或开启 intent.fallback_to_rules。",
            reason="LLM 配置不完整且规则回退已关闭",
            source="fallback",
        )

    context = context[: max(0, config.intent.max_prompt_context_chars)]
    client = AsyncOpenAI(api_key=config.llm.api_key, base_url=config.llm.base_url, timeout=config.limits.intent_timeout_seconds)
    user_payload = {
        "message": message,
        "repo_path": repo_path,
        "has_context": has_context,
        "context": context,
        "available_modes": ["overview", "runbook", "module-map", "task-brief", "deep-scan"],
    }
    try:
        response = await asyncio.wait_for(
            client.chat.completions.create(
                model=config.llm.model,
                messages=[
                    {"role": "system", "content": _load_intent_prompt()},
                    {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
                ],
            ),
            timeout=config.limits.intent_timeout_seconds,
        )
        raw = response.choices[0].message.content or ""
        data = _extract_json(raw)
        decision = _normalize_decision(IntentDecision.model_validate({**data, "source": "llm"}), message)
    except (Exception, ValidationError) as exc:
        if config.intent.fallback_to_rules:
            return _fallback_decision(message, has_context, f"Intent router 失败：{exc}")
        return IntentDecision(
            intent="ambiguous",
            confidence=0,
            needs_tools=False,
            clarifying_question="意图识别失败。请换一种更明确的说法，或使用 /overview、/runbook、/task-brief。",
            reason=f"Intent router 失败且规则回退已关闭：{exc}",
            source="fallback",
        )
    finally:
        await client.close()

    if decision.confidence < config.intent.min_confidence:
        if config.intent.fallback_to_rules:
            return _fallback_decision(message, has_context, f"LLM 置信度低：{decision.confidence:.2f}")
        return IntentDecision(
            intent="ambiguous",
            confidence=decision.confidence,
            needs_tools=False,
            clarifying_question=decision.clarifying_question or "我不确定你是想聊天、配置，还是分析仓库。可以说得更具体一点吗？",
            reason=f"LLM 置信度低：{decision.reason}",
            source="llm",
        )

    return decision


def run_intent_router(*args: Any, **kwargs: Any) -> IntentDecision:
    return asyncio.run(decide_intent(*args, **kwargs))
