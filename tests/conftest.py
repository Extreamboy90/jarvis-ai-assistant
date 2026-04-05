"""
Pytest configuration and shared fixtures
"""
import os
import sys
import pytest
from unittest.mock import AsyncMock, MagicMock

# Add services/orchestrator to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'services', 'orchestrator'))


@pytest.fixture
def mock_gemini_client():
    """Mock Gemini client for testing"""
    client = MagicMock()

    # Mock memory extraction response
    client.generate_content = AsyncMock(return_value={
        "message": {
            "content": '[{"snippet": "L\'utente si chiama Mario", "category": "nome", "importance": 10}]'
        }
    })

    return client


@pytest.fixture
def mock_ollama_response():
    """Mock Ollama API response"""
    return {
        "model": "gemma3:1b",
        "message": {
            "role": "assistant",
            "content": "Ciao! Come posso aiutarti?"
        }
    }


@pytest.fixture
def sample_messages():
    """Sample conversation messages"""
    return [
        {"role": "user", "content": "Ciao, mi chiamo Alessandro"},
        {"role": "assistant", "content": "Ciao Alessandro! Piacere di conoscerti."},
        {"role": "user", "content": "Abito a Roma"}
    ]


@pytest.fixture
def sample_memory_snippets():
    """Sample memory snippets for testing"""
    return [
        {
            "id": 1,
            "user_id": "test_user",
            "snippet": "L'utente si chiama Alessandro",
            "category": "nome",
            "importance": 10,
            "metadata": {},
            "similarity": 0.95
        },
        {
            "id": 2,
            "user_id": "test_user",
            "snippet": "Abita a Roma",
            "category": "fatto",
            "importance": 8,
            "metadata": {},
            "similarity": 0.87
        }
    ]


@pytest.fixture
def mock_pg_pool():
    """Mock PostgreSQL connection pool"""
    pool = AsyncMock()

    # Mock connection context manager
    conn = AsyncMock()
    conn.fetchval = AsyncMock(return_value=1)
    conn.fetch = AsyncMock(return_value=[])
    conn.execute = AsyncMock()

    pool.acquire = AsyncMock(return_value=conn)
    pool.acquire().__aenter__ = AsyncMock(return_value=conn)
    pool.acquire().__aexit__ = AsyncMock(return_value=None)

    return pool
