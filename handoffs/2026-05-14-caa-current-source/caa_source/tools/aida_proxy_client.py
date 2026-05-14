from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


AIDA_V1_MODEL_PATH = "aida-bedrock-proxy:claude-haiku-4-5"
AIDA_INFERENCE_PROFILE_ID = "arn:aws:bedrock:us-east-1:003231568750:application-inference-profile/1lgjlvmziewi"
AIDA_GUARDRAIL_ID = "arn:aws:bedrock:us-east-1:003231568750:guardrail/vfscnyuxyy9a"
AIDA_GUARDRAIL_VERSION = "1"
AIDA_API_GATEWAY_ID = "cpvmmdvf08"


class AiDaProxyError(RuntimeError):
    def __init__(self, code: str, message: str, *, details: object | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"code": self.code, "message": self.message}
        if self.details is not None:
            payload["details"] = self.details
        return payload


class AiDaProxyTransport(Protocol):
    def generate(self, request: dict[str, Any]) -> dict[str, Any]:
        ...


@dataclass(frozen=True, slots=True)
class AiDaProxyConfig:
    model_path: str = AIDA_V1_MODEL_PATH
    inference_profile_id: str = AIDA_INFERENCE_PROFILE_ID
    guardrail_id: str = AIDA_GUARDRAIL_ID
    guardrail_version: str = AIDA_GUARDRAIL_VERSION
    api_gateway_id: str = AIDA_API_GATEWAY_ID
    max_tokens: int = 10000
    temperature: float = 0.2


class AiDaProxyClient:
    def __init__(self, transport: AiDaProxyTransport, config: AiDaProxyConfig | None = None) -> None:
        self.transport = transport
        self.config = config or AiDaProxyConfig()

    def build_request(self, prompt: str) -> dict[str, Any]:
        if not prompt.strip():
            raise AiDaProxyError("empty_prompt", "LLM prompt must not be empty.")
        return {
            "proxy": "aida_oauth_api_gateway_bedrock",
            "model_path": self.config.model_path,
            "headers": {
                "Content-Type": "application/json",
                "x-apigw-api-id": self.config.api_gateway_id,
            },
            "payload": {
                "inferenceProfileId": self.config.inference_profile_id,
                "guardrailIdentifier": self.config.guardrail_id,
                "guardrailVersion": self.config.guardrail_version,
                "contentType": "application/json",
                "accept": "application/json",
                "body": {
                    "anthropic_version": "bedrock-2023-05-31",
                    "max_tokens": self.config.max_tokens,
                    "temperature": self.config.temperature,
                    "messages": [{"role": "user", "content": prompt}],
                },
            },
        }

    def generate(self, prompt: str) -> dict[str, Any]:
        request = self.build_request(prompt)
        try:
            response = self.transport.generate(request)
        except AiDaProxyError:
            raise
        except Exception as exc:
            raise AiDaProxyError(
                "proxy_transport_failure",
                "AiDa proxy transport failed before returning a response.",
                details={"reason": exc.__class__.__name__},
            ) from exc

        text = _extract_text(response)
        if not text:
            raise AiDaProxyError("empty_proxy_response", "AiDa proxy returned no answer text.")
        return {
            "schema_version": "contract_analyzer_llm_proxy_response_v1",
            "model_path": self.config.model_path,
            "text": text,
            "raw_response": response,
        }


def _extract_text(response: dict[str, Any]) -> str:
    if isinstance(response.get("text"), str):
        return response["text"]

    nested = response.get("response")
    if isinstance(nested, dict):
        content = nested.get("content")
        if isinstance(content, list) and content:
            first = content[0]
            if isinstance(first, dict) and isinstance(first.get("text"), str):
                return first["text"]
    return ""
