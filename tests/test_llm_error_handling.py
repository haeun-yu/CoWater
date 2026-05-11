"""
Test Suite: LLM Error Handling

이 테스트 모듈은 LLM 오류 처리 메커니즘을 검증합니다:

1. LLMErrorType 분류
2. LLMErrorContext 생성 및 직렬화
3. OllamaClient 재시도 로직
4. Decision Engine 오류 처리
5. Circuit breaker 패턴

Author: CoWater AI Agent
Version: v2.0 (Phase 2, Step 2)
"""

from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestLLMErrorType:
    """LLMErrorType 분류 테스트"""

    def test_error_type_enum_values(self):
        """Error type 상수 확인"""
        try:
            from agent.llm_client import LLMErrorType
            
            assert LLMErrorType.NETWORK_ERROR.value == "network_error"
            assert LLMErrorType.TIMEOUT_ERROR.value == "timeout_error"
            assert LLMErrorType.PARSE_ERROR.value == "parse_error"
            assert LLMErrorType.VALIDATION_ERROR.value == "validation_error"
            assert LLMErrorType.MODEL_ERROR.value == "model_error"
            assert LLMErrorType.CIRCUIT_BREAKER_OPEN.value == "circuit_open"
            assert LLMErrorType.UNKNOWN_ERROR.value == "unknown_error"
        except ImportError:
            pytest.skip("llm_client module not available")

    def test_error_classification_timeout(self):
        """Timeout 오류 분류"""
        try:
            from agent.llm_client import LLMClient, LLMErrorType
            
            timeout_exc = TimeoutError("Request timed out")
            error_type = LLMClient._classify_error(timeout_exc)
            
            assert error_type == LLMErrorType.TIMEOUT_ERROR
        except ImportError:
            pytest.skip("llm_client module not available")

    def test_error_classification_network(self):
        """Network 오류 분류"""
        try:
            from agent.llm_client import LLMClient, LLMErrorType
            
            network_exc = ConnectionError("Connection refused")
            error_type = LLMClient._classify_error(network_exc)
            
            assert error_type == LLMErrorType.NETWORK_ERROR
        except ImportError:
            pytest.skip("llm_client module not available")

    def test_error_classification_parse(self):
        """Parse 오류 분류"""
        try:
            from agent.llm_client import LLMClient, LLMErrorType
            
            parse_exc = ValueError("JSON decode error")
            error_type = LLMClient._classify_error(parse_exc)
            
            assert error_type == LLMErrorType.PARSE_ERROR
        except ImportError:
            pytest.skip("llm_client module not available")

    def test_error_classification_unknown(self):
        """Unknown 오류 분류"""
        try:
            from agent.llm_client import LLMClient, LLMErrorType
            
            unknown_exc = RuntimeError("Some random error")
            error_type = LLMClient._classify_error(unknown_exc)
            
            assert error_type == LLMErrorType.UNKNOWN_ERROR
        except ImportError:
            pytest.skip("llm_client module not available")


class TestLLMErrorContext:
    """LLMErrorContext 테스트"""

    def test_error_context_creation(self):
        """LLMErrorContext 생성"""
        try:
            from agent.llm_client import LLMErrorContext, LLMErrorType
            
            ctx = LLMErrorContext(
                error_type=LLMErrorType.TIMEOUT_ERROR,
                message="Request timed out after 30s",
                attempt_number=2,
                max_attempts=3,
                recovery_strategy="retry",
            )
            
            assert ctx.error_type == LLMErrorType.TIMEOUT_ERROR
            assert ctx.message == "Request timed out after 30s"
            assert ctx.attempt_number == 2
            assert ctx.max_attempts == 3
            assert ctx.is_retryable() is True
        except ImportError:
            pytest.skip("llm_client module not available")

    def test_error_context_is_retryable_network(self):
        """Network 오류는 재시도 가능"""
        try:
            from agent.llm_client import LLMErrorContext, LLMErrorType
            
            ctx = LLMErrorContext(
                error_type=LLMErrorType.NETWORK_ERROR,
                message="Connection refused",
                attempt_number=1,
                max_attempts=3,
            )
            
            assert ctx.is_retryable() is True
        except ImportError:
            pytest.skip("llm_client module not available")

    def test_error_context_is_not_retryable_parse(self):
        """Parse 오류는 재시도 불가능"""
        try:
            from agent.llm_client import LLMErrorContext, LLMErrorType
            
            ctx = LLMErrorContext(
                error_type=LLMErrorType.PARSE_ERROR,
                message="JSON parse error",
                attempt_number=1,
                max_attempts=3,
            )
            
            assert ctx.is_retryable() is False
        except ImportError:
            pytest.skip("llm_client module not available")

    def test_error_context_is_not_retryable_max_attempts(self):
        """최대 시도 도달 시 재시도 불가능"""
        try:
            from agent.llm_client import LLMErrorContext, LLMErrorType
            
            ctx = LLMErrorContext(
                error_type=LLMErrorType.TIMEOUT_ERROR,
                message="Timeout",
                attempt_number=3,
                max_attempts=3,
            )
            
            assert ctx.is_retryable() is False
        except ImportError:
            pytest.skip("llm_client module not available")

    def test_error_context_to_dict(self):
        """LLMErrorContext dict 직렬화"""
        try:
            from agent.llm_client import LLMErrorContext, LLMErrorType
            
            ctx = LLMErrorContext(
                error_type=LLMErrorType.TIMEOUT_ERROR,
                message="Timeout after 30s",
                attempt_number=2,
                max_attempts=3,
                recovery_strategy="retry",
            )
            
            ctx_dict = ctx.to_dict()
            
            assert ctx_dict["error_type"] == "timeout_error"
            assert ctx_dict["message"] == "Timeout after 30s"
            assert ctx_dict["attempt_number"] == 2
            assert ctx_dict["max_attempts"] == 3
            assert ctx_dict["is_retryable"] is True
        except ImportError:
            pytest.skip("llm_client module not available")


class TestOllamaClientRetry:
    """OllamaClient 재시도 로직 테스트"""

    @pytest.mark.asyncio
    async def test_ollama_success_on_first_attempt(self):
        """첫 시도에 성공"""
        try:
            from agent.llm_client import OllamaClient
            
            client = OllamaClient(endpoint="http://localhost:11434", model="test-model", max_retries=3)
            
            # Mock successful response
            mock_response = MagicMock()
            mock_response.json.return_value = {"response": "Test response"}
            mock_response.raise_for_status.return_value = None
            
            with patch.object(client.client, 'post', new_callable=AsyncMock) as mock_post:
                mock_post.return_value = mock_response
                
                response, error_ctx = await client.generate(prompt="Test prompt", timeout=30)
                
                assert response == "Test response"
                assert error_ctx is None
                assert mock_post.call_count == 1
        except ImportError:
            pytest.skip("llm_client module not available")

    @pytest.mark.asyncio
    async def test_ollama_retry_on_network_error(self):
        """Network 오류 시 재시도"""
        try:
            from agent.llm_client import OllamaClient
            
            client = OllamaClient(endpoint="http://localhost:11434", model="test-model", max_retries=3)
            
            # Mock failed then successful response
            mock_response = MagicMock()
            mock_response.json.return_value = {"response": "Test response"}
            mock_response.raise_for_status.return_value = None
            
            with patch.object(client.client, 'post', new_callable=AsyncMock) as mock_post:
                # First call fails with network error, second succeeds
                mock_post.side_effect = [
                    ConnectionError("Connection refused"),
                    mock_response,
                ]
                
                response, error_ctx = await client.generate(prompt="Test prompt", timeout=30)
                
                assert response == "Test response"
                assert error_ctx is None
                assert mock_post.call_count == 2  # Retry occurred
        except ImportError:
            pytest.skip("llm_client module not available")

    @pytest.mark.asyncio
    async def test_ollama_exhausts_retries(self):
        """모든 재시도 소진"""
        try:
            from agent.llm_client import OllamaClient
            
            client = OllamaClient(endpoint="http://localhost:11434", model="test-model", max_retries=3)
            
            with patch.object(client.client, 'post', new_callable=AsyncMock) as mock_post:
                # All calls fail with timeout
                mock_post.side_effect = TimeoutError("Request timed out")
                
                response, error_ctx = await client.generate(prompt="Test prompt", timeout=30)
                
                assert response is None
                assert error_ctx is not None
                assert error_ctx.error_type.value == "timeout_error"
                assert mock_post.call_count == 3  # All retries exhausted
        except ImportError:
            pytest.skip("llm_client module not available")

    @pytest.mark.asyncio
    async def test_ollama_circuit_breaker_opens(self):
        """Circuit breaker가 열림"""
        try:
            from agent.llm_client import OllamaClient
            
            client = OllamaClient(endpoint="http://localhost:11434", model="test-model", max_retries=3)
            
            with patch.object(client.client, 'post', new_callable=AsyncMock) as mock_post:
                # Multiple failures to open circuit
                mock_post.side_effect = ConnectionError("Connection refused")
                
                # First request - fails and opens circuit
                response1, error_ctx1 = await client.generate(prompt="Test 1", timeout=30)
                
                # Second request - should hit circuit breaker
                response2, error_ctx2 = await client.generate(prompt="Test 2", timeout=30)
                
                assert response2 is None
                assert error_ctx2 is not None
                assert error_ctx2.error_type.value == "circuit_open"
                assert client._circuit_open_until > time.monotonic()
        except ImportError:
            pytest.skip("llm_client module not available")


class TestDecisionEngineErrorHandling:
    """Decision Engine 오류 처리 테스트"""

    @pytest.mark.asyncio
    async def test_analyze_alert_with_llm_error(self):
        """Alert 분석 중 LLM 오류"""
        try:
            from agent.decision import DecisionEngine
            from skills.catalog import SkillCatalog
            from agent.state import AgentState
            
            catalog = SkillCatalog({})
            config = {"llm": {"provider": "ollama", "endpoint": "http://localhost:11434", "model": "test"}}

            class DummyResponse:
                def __enter__(self):
                    return self

                def __exit__(self, exc_type, exc, tb):
                    return False

            with patch("urllib.request.urlopen", return_value=DummyResponse()):
                engine = DecisionEngine(config, catalog)
            
            # Mock LLM client to return error
            mock_client = AsyncMock()
            mock_client.generate = AsyncMock(return_value=(
                None,
                {
                    "error_type": "timeout_error",
                    "message": "LLM timeout",
                    "attempt_number": 3,
                    "max_attempts": 3,
                    "recovery_strategy": "fallback",
                }
            ))
            engine.llm_client = mock_client
            
            state = AgentState(
                agent_id="test-agent",
                role="device_agent",
                layer="lower",
                instance_id="test-instance",
                name="Test Agent",
            )
            alert = {
                "alert_type": "mine_detection",
                "severity": "HIGH",
                "metadata": {},
            }
            devices = []
            
            result, error = await engine.analyze_alert(alert, devices, state)
            
            assert result is None
            assert error is not None
            assert error["error_type"] == "timeout_error"
        except ImportError:
            pytest.skip("decision or state modules not available")

    @pytest.mark.asyncio
    async def test_analyze_command_with_llm_error(self):
        """Command 분석 중 LLM 오류"""
        try:
            from agent.decision import DecisionEngine
            from skills.catalog import SkillCatalog
            from agent.state import AgentState
            
            catalog = SkillCatalog({})
            config = {"llm": {"provider": "ollama", "endpoint": "http://localhost:11434", "model": "test"}}

            class DummyResponse:
                def __enter__(self):
                    return self

                def __exit__(self, exc_type, exc, tb):
                    return False

            with patch("urllib.request.urlopen", return_value=DummyResponse()):
                engine = DecisionEngine(config, catalog)
            
            # Mock LLM client to return error
            mock_client = AsyncMock()
            mock_client.generate = AsyncMock(return_value=(
                None,
                {
                    "error_type": "network_error",
                    "message": "Connection refused",
                    "attempt_number": 3,
                    "max_attempts": 3,
                    "recovery_strategy": "fallback",
                }
            ))
            engine.llm_client = mock_client
            
            state = AgentState(
                agent_id="test-agent",
                role="device_agent",
                layer="lower",
                instance_id="test-instance",
                name="Test Agent",
            )
            command = {"action": "mission.assign"}
            devices = []
            
            result, error = await engine.analyze_command(command, devices, state)
            
            assert result is None
            assert error is not None
            assert error["error_type"] == "network_error"
        except ImportError:
            pytest.skip("decision or state modules not available")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
