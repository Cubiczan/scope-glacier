"""Amazon Nova Lite is the Bedrock model; Anthropic overrides are rejected."""
from __future__ import annotations

import importlib
import importlib.util
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from bedrock_client import (
    DEFAULT_BEDROCK_MODEL_ID,
    AnthropicModelError,
    BedrockClient,
    resolve_bedrock_model_id,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
CLAUDE_ON_DEMAND = "anthropic." + "claude-3-haiku-20240307-v1:0"
CLAUDE_US_PROFILE = "us.anthropic." + "claude-3-haiku-20240307-v1:0"


def _load_verify():
    path = REPO_ROOT / "scripts" / "verify_bedrock_model.py"
    spec = importlib.util.spec_from_file_location("verify_bedrock_model", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_default_model_is_nova_lite(monkeypatch):
    monkeypatch.delenv("BEDROCK_MODEL_ID", raising=False)
    assert resolve_bedrock_model_id() == "us.amazon.nova-lite-v1:0"
    assert DEFAULT_BEDROCK_MODEL_ID == "us.amazon.nova-lite-v1:0"


def test_blank_model_id_falls_back_to_nova_lite(monkeypatch):
    monkeypatch.setenv("BEDROCK_MODEL_ID", "   ")
    assert resolve_bedrock_model_id() == DEFAULT_BEDROCK_MODEL_ID
    assert resolve_bedrock_model_id("  ") == DEFAULT_BEDROCK_MODEL_ID


def test_nova_override_is_forwarded(monkeypatch):
    monkeypatch.setenv("BEDROCK_MODEL_ID", "us.amazon.nova-micro-v1:0")
    assert resolve_bedrock_model_id() == "us.amazon.nova-micro-v1:0"


@pytest.mark.parametrize("model_id", [CLAUDE_ON_DEMAND, CLAUDE_US_PROFILE, "ANTHROPIC.claude-3-5-sonnet-v1:0"])
def test_anthropic_override_is_rejected(model_id):
    with pytest.raises(AnthropicModelError, match="us.amazon.nova-lite-v1:0"):
        resolve_bedrock_model_id(model_id)


def test_converse_uses_nova_lite_and_reads_converse_text(monkeypatch):
    monkeypatch.delenv("BEDROCK_MODEL_ID", raising=False)
    runtime = MagicMock()
    runtime.converse.return_value = {
        "output": {"message": {"content": [{"text": "Tight "}, {"text": "supply."}]}},
        "usage": {"inputTokens": 12, "outputTokens": 4},
        "stopReason": "end_turn",
    }
    client = BedrockClient(_client=runtime)
    result = client.converse(
        messages=[{"role": "user", "content": [{"text": "Analyze WTI"}]}],
        system="Be concise.",
    )
    kwargs = runtime.converse.call_args.kwargs
    assert kwargs["modelId"] == DEFAULT_BEDROCK_MODEL_ID
    assert kwargs["messages"] == [{"role": "user", "content": [{"text": "Analyze WTI"}]}]
    assert kwargs["system"] == [{"text": "Be concise."}]
    assert "anthropic_version" not in kwargs
    assert result["content"] == "Tight supply."
    assert result["model"] == DEFAULT_BEDROCK_MODEL_ID


def test_converse_rejects_anthropic_before_the_api_call():
    runtime = MagicMock()
    client = BedrockClient(model_id="amazon.nova-lite-v1:0", _client=runtime)
    client.model_id = CLAUDE_ON_DEMAND
    with pytest.raises(AnthropicModelError):
        client.converse(messages=[{"role": "user", "content": [{"text": "hi"}]}])
    runtime.converse.assert_not_called()


def _analysis_handler():
    """Load the handler file directly.

    ``src/lambda/__init__.py`` is a non-importable placeholder, and ``lambda``
    is a Python keyword, so a normal import of the package fails.
    """
    path = REPO_ROOT / "src" / "lambda" / "glacier_analysis_handler.py"
    spec = importlib.util.spec_from_file_location("glacier_analysis_handler_under_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_lambda_defaults_to_nova_lite(monkeypatch):
    monkeypatch.delenv("BEDROCK_MODEL_ID", raising=False)
    invoke_bedrock_analysis = _analysis_handler().invoke_bedrock_analysis

    runtime = MagicMock()
    runtime.converse.return_value = {
        "output": {"message": {"content": [{"text": "Outlook."}]}},
    }
    with patch.object(invoke_bedrock_analysis.__globals__["boto3"], "client", return_value=runtime):
        text = invoke_bedrock_analysis("WTI", {"glacier_score": 70, "signal_rating": "Buy"})
    assert text == "Outlook."
    assert runtime.converse.call_args.kwargs["modelId"] == DEFAULT_BEDROCK_MODEL_ID


def test_lambda_rejects_anthropic_before_bedrock(monkeypatch):
    monkeypatch.setenv("BEDROCK_MODEL_ID", CLAUDE_US_PROFILE)
    invoke_bedrock_analysis = _analysis_handler().invoke_bedrock_analysis

    with patch.object(invoke_bedrock_analysis.__globals__["boto3"], "client") as boto_client:
        with pytest.raises(AnthropicModelError, match="Nova"):
            invoke_bedrock_analysis("WTI", {})
    boto_client.assert_not_called()


def test_lambda_reports_analysis_unavailable(monkeypatch):
    monkeypatch.delenv("BEDROCK_MODEL_ID", raising=False)
    invoke_bedrock_analysis = _analysis_handler().invoke_bedrock_analysis

    runtime = MagicMock()
    runtime.converse.side_effect = RuntimeError("service down")
    with patch.object(invoke_bedrock_analysis.__globals__["boto3"], "client", return_value=runtime):
        text = invoke_bedrock_analysis("HH", {"glacier_score": 40})
    assert text.startswith("Analysis unavailable:")
    assert "service down" in text


def test_verify_script_passes():
    verify = _load_verify()
    assert verify.collect_errors(REPO_ROOT) == []
    assert verify.main() == 0
