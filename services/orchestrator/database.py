"""
Database connection and operations for Jarvis
"""

import asyncpg
import redis
import os
import logging
from typing import Optional, List, Dict, Any
from datetime import datetime
import json

logger = logging.getLogger(__name__)

# Database configuration
POSTGRES_HOST = os.getenv("POSTGRES_HOST", "postgres")
POSTGRES_PORT = int(os.getenv("POSTGRES_PORT", "5432"))
POSTGRES_DB = os.getenv("POSTGRES_DB", "jarvis")
POSTGRES_USER = os.getenv("POSTGRES_USER", "jarvis")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "jarvis_password")

REDIS_HOST = os.getenv("REDIS_HOST", "redis")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))

# Global connections
pg_pool: Optional[asyncpg.Pool] = None
redis_client: Optional[redis.Redis] = None


async def init_db():
    """Initialize database connections"""
    global pg_pool, redis_client

    try:
        # PostgreSQL connection pool
        pg_pool = await asyncpg.create_pool(
            host=POSTGRES_HOST,
            port=POSTGRES_PORT,
            database=POSTGRES_DB,
            user=POSTGRES_USER,
            password=POSTGRES_PASSWORD,
            min_size=2,
            max_size=10,
            command_timeout=60
        )
        logger.info("PostgreSQL connection pool created")

        # Redis connection
        redis_client = redis.Redis(
            host=REDIS_HOST,
            port=REDIS_PORT,
            decode_responses=True,
            socket_timeout=5,
            socket_connect_timeout=5
        )
        redis_client.ping()
        logger.info("Redis connection established")

    except Exception as e:
        logger.error(f"Database initialization error: {e}")
        raise


async def close_db():
    """Close database connections"""
    global pg_pool, redis_client

    if pg_pool:
        await pg_pool.close()
        logger.info("PostgreSQL connection pool closed")

    if redis_client:
        redis_client.close()
        logger.info("Redis connection closed")


async def ensure_user_exists(user_id: str, username: Optional[str] = None) -> int:
    """Ensure user exists in database, create if not"""
    async with pg_pool.acquire() as conn:
        # Try to get existing user
        row = await conn.fetchrow(
            "SELECT id FROM users WHERE user_id = $1",
            user_id
        )

        if row:
            # Update last_active
            await conn.execute(
                "UPDATE users SET last_active = CURRENT_TIMESTAMP WHERE user_id = $1",
                user_id
            )
            return row['id']

        # Create new user
        row = await conn.fetchrow(
            """
            INSERT INTO users (user_id, username, created_at, last_active)
            VALUES ($1, $2, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            RETURNING id
            """,
            user_id, username
        )
        logger.info(f"Created new user: {user_id}")
        return row['id']


async def get_or_create_conversation(user_id: str, session_id: Optional[str] = None) -> int:
    """Get active conversation or create new one"""
    async with pg_pool.acquire() as conn:
        # Ensure user exists
        await ensure_user_exists(user_id)

        # Try to get active conversation (within last 24 hours)
        if session_id:
            row = await conn.fetchrow(
                """
                SELECT id FROM conversations
                WHERE user_id = $1 AND session_id = $2
                ORDER BY updated_at DESC LIMIT 1
                """,
                user_id, session_id
            )
        else:
            row = await conn.fetchrow(
                """
                SELECT id FROM conversations
                WHERE user_id = $1 AND updated_at > NOW() - INTERVAL '24 hours'
                ORDER BY updated_at DESC LIMIT 1
                """,
                user_id
            )

        if row:
            return row['id']

        # Create new conversation
        row = await conn.fetchrow(
            """
            INSERT INTO conversations (user_id, session_id, created_at, updated_at)
            VALUES ($1, $2, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            RETURNING id
            """,
            user_id, session_id
        )
        logger.info(f"Created new conversation for user {user_id}")
        return row['id']


async def add_message(
    user_id: str,
    role: str,
    content: str,
    session_id: Optional[str] = None,
    metadata: Optional[Dict] = None
) -> int:
    """Add message to conversation"""
    async with pg_pool.acquire() as conn:
        # Get or create conversation
        conversation_id = await get_or_create_conversation(user_id, session_id)

        # Insert message
        row = await conn.fetchrow(
            """
            INSERT INTO messages (conversation_id, role, content, metadata, created_at)
            VALUES ($1, $2, $3, $4, CURRENT_TIMESTAMP)
            RETURNING id
            """,
            conversation_id, role, content, json.dumps(metadata or {})
        )

        # Update conversation timestamp
        await conn.execute(
            "UPDATE conversations SET updated_at = CURRENT_TIMESTAMP WHERE id = $1",
            conversation_id
        )

        return row['id']


async def get_conversation_history(
    user_id: str,
    max_messages: int = 10,
    session_id: Optional[str] = None
) -> List[Dict[str, str]]:
    """Get conversation history for user"""
    async with pg_pool.acquire() as conn:
        # Get conversation
        conversation_id = await get_or_create_conversation(user_id, session_id)

        # Get messages
        rows = await conn.fetch(
            """
            SELECT role, content, created_at
            FROM messages
            WHERE conversation_id = $1
            ORDER BY created_at DESC
            LIMIT $2
            """,
            conversation_id, max_messages
        )

        # Return in chronological order
        messages = [
            {"role": row['role'], "content": row['content']}
            for row in reversed(rows)
        ]

        return messages


async def log_function_call(
    message_id: int,
    function_name: str,
    parameters: Dict,
    result: Any,
    success: bool = True,
    execution_time_ms: Optional[int] = None
):
    """Log function call to database"""
    async with pg_pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO function_calls (message_id, function_name, parameters, result, success, execution_time_ms, created_at)
            VALUES ($1, $2, $3, $4, $5, $6, CURRENT_TIMESTAMP)
            """,
            message_id, function_name, json.dumps(parameters), json.dumps(result), success, execution_time_ms
        )


async def log_interaction(user_id: str, interaction_type: str, data: Dict):
    """Log user interaction"""
    async with pg_pool.acquire() as conn:
        await ensure_user_exists(user_id)
        await conn.execute(
            """
            INSERT INTO interactions (user_id, interaction_type, data, created_at)
            VALUES ($1, $2, $3, CURRENT_TIMESTAMP)
            """,
            user_id, interaction_type, json.dumps(data)
        )


async def clear_conversation(user_id: str, session_id: Optional[str] = None):
    """Clear conversation history for user"""
    async with pg_pool.acquire() as conn:
        if session_id:
            await conn.execute(
                "DELETE FROM conversations WHERE user_id = $1 AND session_id = $2",
                user_id, session_id
            )
        else:
            await conn.execute(
                "DELETE FROM conversations WHERE user_id = $1",
                user_id
            )
        logger.info(f"Cleared conversation for user {user_id}")


# Redis cache helpers
def get_cache_key(user_id: str, key: str) -> str:
    """Generate cache key"""
    return f"jarvis:{user_id}:{key}"


def cache_get(user_id: str, key: str) -> Optional[str]:
    """Get value from cache"""
    try:
        return redis_client.get(get_cache_key(user_id, key))
    except Exception as e:
        logger.error(f"Redis get error: {e}")
        return None


def cache_set(user_id: str, key: str, value: str, ttl: int = 3600):
    """Set value in cache with TTL in seconds"""
    try:
        redis_client.setex(get_cache_key(user_id, key), ttl, value)
    except Exception as e:
        logger.error(f"Redis set error: {e}")


def cache_delete(user_id: str, key: str):
    """Delete value from cache"""
    try:
        redis_client.delete(get_cache_key(user_id, key))
    except Exception as e:
        logger.error(f"Redis delete error: {e}")
