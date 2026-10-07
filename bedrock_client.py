"""
Bedrock Client — Amazon Bedrock Runtime Converse API for Amazon Nova.
https://docs.aws.amazon.com/bedrock/latest/APIReference/API_runtime_Converse.html

The default model is the US Amazon Nova Lite inference profile. Anthropic Claude
ids are rejected: Claude on Bedrock is billed through AWS Marketplace and is
not covered by AWS promo credits.
"""
from __future__ import annotations
import logging, os, time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
import boto3
from botocore.exceptions import ClientError
logger = logging.getLogger(__name__)

DEFAULT_BEDROCK_MODEL_ID = "us.amazon.nova-lite-v1:0"
DEFAULT_BEDROCK_REGION = "us-east-1"


class AnthropicModelError(ValueError):
    """Raised when a model id selects Anthropic Claude on Amazon Bedrock."""


def is_anthropic_model_id(model_id: str) -> bool:
    """True for on-demand ``anthropic.*`` ids and ``*.anthropic.*`` inference profiles."""
    normalized = model_id.strip().lower()
    if not normalized:
        return False
    if normalized.startswith("anthropic."):
        return True
    return "anthropic" in normalized.split(".")


def resolve_bedrock_model_id(model_id: Optional[str] = None) -> str:
    """Return a Bedrock model id, or raise if it selects Anthropic.

    ``None`` reads ``BEDROCK_MODEL_ID``. A blank value falls back to Amazon
    Nova Lite. Rejection happens before any Converse call.
    """
    if model_id is None:
        model_id = os.environ.get("BEDROCK_MODEL_ID", "")
    resolved = (model_id or "").strip() or DEFAULT_BEDROCK_MODEL_ID
    if is_anthropic_model_id(resolved):
        raise AnthropicModelError(
            f"Refusing Anthropic model id {resolved!r}. "
            "Claude on Amazon Bedrock is billed through AWS Marketplace and is not covered "
            "by AWS promo credits (the account is IAM-denied for Anthropic models). "
            f"Set BEDROCK_MODEL_ID to an Amazon Nova model such as {DEFAULT_BEDROCK_MODEL_ID}."
        )
    return resolved


@dataclass
class BedrockClient:
    """Thin wrapper around boto3 Bedrock Runtime Converse API."""
    model_id: str = field(default_factory=lambda: os.environ.get("BEDROCK_MODEL_ID", "") or DEFAULT_BEDROCK_MODEL_ID)
    region: str = field(default_factory=lambda: os.environ.get("AWS_REGION", DEFAULT_BEDROCK_REGION))
    max_tokens: int = 1500
    temperature: float = 0.3
    max_retries: int = 3
    base_delay: float = 1.0
    _client: Any = field(default=None, repr=False)

    def __post_init__(self) -> None:
        self.model_id = resolve_bedrock_model_id(self.model_id)
        if self._client is None:
            self._client = boto3.client("bedrock-runtime", region_name=self.region)

    def converse(self, messages: List[Dict[str, Any]], system: Optional[str] = None,
                 temperature: Optional[float] = None, max_tokens: Optional[int] = None) -> Dict[str, Any]:
        model_id = resolve_bedrock_model_id(self.model_id)
        inference_config = {"maxTokens": max_tokens or self.max_tokens,
                            "temperature": temperature if temperature is not None else self.temperature}
        for attempt in range(self.max_retries):
            try:
                kwargs: Dict[str, Any] = {"modelId": model_id, "messages": messages, "inferenceConfig": inference_config}
                if system:
                    kwargs["system"] = [{"text": system}]
                response = self._client.converse(**kwargs)
                output = response.get("output", {})
                message = output.get("message", {})
                text = "".join(cb.get("text", "") for cb in message.get("content", []))
                usage = response.get("usage", {})
                return {"content": text, "input_tokens": usage.get("inputTokens", 0),
                        "output_tokens": usage.get("outputTokens", 0), "model": model_id,
                        "stop_reason": response.get("stopReason", message.get("stopReason"))}
            except ClientError as e:
                if e.response.get("Error", {}).get("Code", "") in ("ThrottlingException", "ServiceUnavailable") and attempt < self.max_retries - 1:
                    time.sleep(self.base_delay * (2 ** attempt)); continue
                raise
        raise RuntimeError(f"Bedrock converse failed after {self.max_retries} retries")

    def chat(self, prompt: str, system: Optional[str] = None, **kw) -> str:
        return self.converse(messages=[{"role": "user", "content": [{"text": prompt}]}], system=system, **kw)["content"]

    def multi_turn(self, messages: List[Dict[str, str]], system: Optional[str] = None, **kw) -> str:
        return self.converse(messages=[{"role": m["role"], "content": [{"text": m["content"]}]} for m in messages], system=system, **kw)["content"]
