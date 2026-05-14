"""Concrete AiDaProxyTransport — OAuth2 client-credentials → API Gateway → Bedrock.

Mirrors the pattern in docs/week_7/05_11_2026/test 1.py (Sehaj's dev variant).
Secrets are pulled lazily from AWS Secrets Manager on first use; the OAuth
token is cached in-process and cleared on 401 to trigger a fresh fetch.

Usage (in main.py startup)::

    from tools.aida_oauth_transport import AiDaOAuthTransport
    app.state.aida_proxy_transport = AiDaOAuthTransport()

Environment variables consumed (all optional):
    CAA_AIDA_SECRET_NAME  — override the Secrets Manager secret path
    CAA_AIDA_AWS_REGION   — override the AWS region (default: us-east-1)
    AWS_PROFILE           — which SSO/IAM profile boto3 should use
"""
from __future__ import annotations

import json
import logging
import time
from typing import Any

import boto3
import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logger = logging.getLogger(__name__)

# The secret was registered in Secrets Manager with the doubled path.
_DEFAULT_SECRET_NAME = "/application/aid/dev//application/aid/dev/aida-app-secret"
_DEFAULT_REGION = "us-east-1"
_OAUTH_SCOPE = "api://54638f69-6be4-4d65-942b-a0a6f19785e0/.default"


class AiDaOAuthTransport:
    """
    Satisfies the ``AiDaProxyTransport`` Protocol defined in
    ``tools/aida_proxy_client.py``.

    Thread safety: token and secrets are cached on the instance.  If the app
    is served with multiple workers each worker gets its own instance and own
    token cache, which is fine.
    """

    def __init__(
        self,
        *,
        secret_name: str | None = None,
        region: str | None = None,
        retries: int = 3,
    ) -> None:
        import os

        self._secret_name = secret_name or os.environ.get("CAA_AIDA_SECRET_NAME", _DEFAULT_SECRET_NAME)
        self._region = region or os.environ.get("CAA_AIDA_AWS_REGION", _DEFAULT_REGION)
        self._retries = retries
        self._secrets: dict[str, Any] | None = None
        self._oauth_token: str | None = None

    # ------------------------------------------------------------------
    # AiDaProxyTransport Protocol
    # ------------------------------------------------------------------

    def generate(self, request: dict[str, Any]) -> dict[str, Any]:
        """
        Execute a Bedrock call via the API Gateway proxy.

        ``request`` is the dict produced by ``AiDaProxyClient.build_request()``:
        {
            "proxy": "aida_oauth_api_gateway_bedrock",
            "model_path": ...,
            "headers": {"Content-Type": ..., "x-apigw-api-id": ...},
            "payload": { <full Bedrock invoke payload> }
        }
        """
        secrets = self._load_secrets()
        payload = request["payload"]
        extra_headers: dict[str, str] = request.get("headers", {})

        for attempt in range(1, self._retries + 1):
            token = self._get_oauth_token(secrets)
            headers = {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
                **extra_headers,
            }
            try:
                resp = requests.post(
                    secrets["api_endpoint"],
                    headers=headers,
                    json=payload,
                    verify=False,
                    timeout=30,
                )
                if resp.status_code == 401:
                    # Token expired mid-session — clear and retry immediately.
                    logger.info("event=aida_oauth_token_expired attempt=%d", attempt)
                    self._oauth_token = None
                    continue
                if resp.status_code == 502 and attempt < self._retries:
                    wait = attempt * 2
                    logger.info("event=aida_apigw_502 attempt=%d wait_s=%d", attempt, wait)
                    time.sleep(wait)
                    continue
                resp.raise_for_status()
                logger.info("event=aida_bedrock_ok attempt=%d", attempt)
                return resp.json()

            except requests.exceptions.Timeout:
                if attempt < self._retries:
                    logger.info("event=aida_bedrock_timeout attempt=%d", attempt)
                    time.sleep(2)
                    continue
                raise

        raise RuntimeError("AiDaOAuthTransport: all retries exhausted")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _load_secrets(self) -> dict[str, Any]:
        if self._secrets is None:
            sm = boto3.client("secretsmanager", region_name=self._region, verify=False)
            raw = sm.get_secret_value(SecretId=self._secret_name)["SecretString"]
            self._secrets = json.loads(raw)
            logger.info(
                "event=aida_oauth_secrets_loaded secret=%s region=%s",
                self._secret_name,
                self._region,
            )
        return self._secrets

    def _get_oauth_token(self, secrets: dict[str, Any]) -> str:
        if self._oauth_token:
            return self._oauth_token

        token_url = (
            f"https://login.microsoftonline.com/{secrets['tenant_id']}"
            "/oauth2/v2.0/token"
        )
        payload = {
            "grant_type": "client_credentials",
            "client_id": secrets["client_id"],
            "client_secret": secrets["client_secret"],
            "scope": _OAUTH_SCOPE,
        }
        resp = requests.post(token_url, data=payload, verify=False, timeout=15)
        resp.raise_for_status()
        self._oauth_token = resp.json()["access_token"]
        logger.info("event=aida_oauth_token_acquired")
        return self._oauth_token
