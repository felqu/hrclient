import asyncio
import json
import os
import unittest
from unittest.mock import patch

import httpx2
from openai import DefaultHttpxClient, OpenAI

from app.llm_client.llm_client import LLMClient


class LLMClientTests(unittest.TestCase):
    def test_local_reads_llama_url_without_api_key(self):
        with patch.dict(os.environ, {
            "LLAMA_BASE_URL": " http://192.168.0.103:8080/v1 ",
        }, clear=True), patch("app.llm_client.llm_client.OpenAI") as constructor:
            LLMClient("local-model", "local")
        constructor.assert_called_once_with(
            base_url="http://192.168.0.103:8080/v1", api_key="local",
        )

    def test_local_requires_valid_llama_url(self):
        for value in (None, "", " ", "LLAMA_BASE_URL", "192.168.0.103:8080/v1",
                      "ftp://example.com/v1", "https://"):
            env = {} if value is None else {"LLAMA_BASE_URL": value}
            with self.subTest(url=value), patch.dict(os.environ, env, clear=True), \
                    patch("app.llm_client.llm_client.OpenAI") as constructor:
                with self.assertRaisesRegex(ValueError, "LLAMA_BASE_URL"):
                    LLMClient("local-model", "local")
                constructor.assert_not_called()

    def test_nvidia_reads_base_url_value_from_environment(self):
        with patch.dict(os.environ, {
            "NVIDIA_API_KEY": "test-key",
            "NVIDIA_BASE_URL": "https://custom.example.com/v1",
        }), patch("app.llm_client.llm_client.OpenAI") as constructor:
            LLMClient("custom-model", "nvidia")
        constructor.assert_called_once_with(
            base_url="https://custom.example.com/v1", api_key="test-key",
        )

    def test_nvidia_uses_default_endpoint_if_url_is_unset(self):
        with patch.dict(os.environ, {"NVIDIA_API_KEY": "test-key"}, clear=True), \
                patch("app.llm_client.llm_client.OpenAI") as constructor:
            LLMClient("custom-model", "nvidia")
        constructor.assert_called_once_with(
            base_url="https://integrate.api.nvidia.com/v1", api_key="test-key",
        )

    def test_invalid_url_is_rejected_before_creating_http_client(self):
        for value in ("NVIDIA_BASE_URL", "integrate.api.nvidia.com/v1", "ftp://example.com/v1", "https://"):
            with self.subTest(url=value), patch.dict(os.environ, {
                "NVIDIA_API_KEY": "test-key", "NVIDIA_BASE_URL": value,
            }), patch("app.llm_client.llm_client.OpenAI") as constructor:
                with self.assertRaisesRegex(ValueError, "NVIDIA_BASE_URL"):
                    LLMClient("custom-model", "nvidia")
                constructor.assert_not_called()

    def test_empty_model_has_clear_configuration_error(self):
        for value in (None, "", " "):
            with self.subTest(model=value), self.assertRaisesRegex(ValueError, "модель LLM"):
                LLMClient(value, "nvidia")

    def test_missing_api_key_has_clear_configuration_error(self):
        with patch.dict(os.environ, {}, clear=True), self.assertRaisesRegex(RuntimeError, "NVIDIA_API_KEY"):
            LLMClient("custom-model", "nvidia")

    def test_zai_initialization_still_uses_its_own_client(self):
        with patch.dict(os.environ, {"Z_AI_API_KEY": "test-zai-key"}), \
                patch("app.llm_client.llm_client.ZaiClient") as constructor:
            LLMClient("zai-model", "zai")
        constructor.assert_called_once_with(api_key="test-zai-key")

    def test_real_sdk_sends_to_configured_url_and_assembles_stream(self):
        self._check_stream("nvidia", {
            "NVIDIA_API_KEY": "test-key",
            "NVIDIA_BASE_URL": "https://integrate.api.nvidia.com/v1",
        }, "https://integrate.api.nvidia.com/v1/chat/completions")

    def test_local_sdk_sends_constructor_parameters_and_assembles_stream(self):
        self._check_stream("local", {
            "LLAMA_BASE_URL": "http://192.168.0.103:8080/v1",
        }, "http://192.168.0.103:8080/v1/chat/completions")

    def _check_stream(self, provider, env, expected_url):
        requests = []

        def handle(request):
            requests.append(request)
            chunks = [
                {"choices": [{"index": 0, "delta": {"content": part}, "finish_reason": None}]}
                for part in ('{"ok":', 'true}')
            ]
            body = "".join("data: " + json.dumps(chunk) + "\n\n" for chunk in chunks)
            return httpx2.Response(200, headers={"Content-Type": "text/event-stream"},
                                   text=body + "data: [DONE]\n\n")

        transport = DefaultHttpxClient(transport=httpx2.MockTransport(handle))
        self.addCleanup(transport.close)

        def client_factory(**kwargs):
            client = OpenAI(**kwargs, http_client=transport)
            self.addCleanup(client.close)
            return client

        with patch.dict(os.environ, env, clear=True), \
                patch("app.llm_client.llm_client.OpenAI", side_effect=client_factory):
            client = LLMClient("configured-model", provider, max_tokens=123, temperature=0.3)
            response = asyncio.run(client.complete(
                [{"role": "user", "content": "Return JSON"}],
                extra={"response_format": {"type": "json_object"}},
            ))
        self.assertEqual(json.loads(response), {"ok": True})
        self.assertEqual(len(requests), 1)
        self.assertEqual(str(requests[0].url), expected_url)
        payload = json.loads(requests[0].content)
        self.assertEqual(payload["model"], "configured-model")
        self.assertEqual(payload["max_tokens"], 123)
        self.assertEqual(payload["temperature"], 0.3)
        self.assertTrue(payload["stream"])
        self.assertEqual(payload["response_format"], {"type": "json_object"})
        self.assertNotIn("thinking", payload)
        if provider == "local":
            self.assertNotIn("top_p", payload)
            self.assertNotIn("seed", payload)


if __name__ == "__main__":
    unittest.main()
