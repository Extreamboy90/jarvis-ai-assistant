"""
Manual test script for memory system without embeddings
Tests the logic of contradiction detection and memory management
"""

import asyncio
import asyncpg
import json
import requests
import os

# Configuration
POSTGRES_HOST = "localhost"
POSTGRES_PORT = 5432
POSTGRES_DB = "jarvis"
POSTGRES_USER = "jarvis"
POSTGRES_PASSWORD = "jarvis_password"
OLLAMA_URL = "http://localhost:11434"
OLLAMA_MODEL = "llama3.1:8b"

async def test_memory_system():
    print("🧪 Testing Memory System\n")
    print("=" * 60)

    # Connect to database
    conn = await asyncpg.connect(
        host=POSTGRES_HOST,
        port=POSTGRES_PORT,
        database=POSTGRES_DB,
        user=POSTGRES_USER,
        password=POSTGRES_PASSWORD
    )

    test_user = "test_memory_user"

    # Clean up previous tests
    await conn.execute("DELETE FROM memory_snippets WHERE user_id = $1", test_user)
    print(f"✓ Cleaned up previous test data for user: {test_user}\n")

    # Test 1: Save initial memory
    print("TEST 1: Save initial memory")
    print("-" * 60)
    await conn.execute(
        """
        INSERT INTO memory_snippets
        (user_id, snippet, category, importance, created_at, last_accessed, access_count)
        VALUES ($1, $2, $3, $4, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, 0)
        """,
        test_user, "Marco ama la pizza", "preferenza", 7
    )
    print("✓ Saved: 'Marco ama la pizza' (preferenza, importance: 7)\n")

    # Test 2: Add another memory
    print("TEST 2: Add another memory")
    print("-" * 60)
    await conn.execute(
        """
        INSERT INTO memory_snippets
        (user_id, snippet, category, importance, created_at, last_accessed, access_count)
        VALUES ($1, $2, $3, $4, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, 0)
        """,
        test_user, "Marco vive a Roma", "fatto", 8
    )
    print("✓ Saved: 'Marco vive a Roma' (fatto, importance: 8)\n")

    # Test 3: Check contradictions using LLM
    print("TEST 3: Test contradiction detection")
    print("-" * 60)

    # Get existing memories
    rows = await conn.fetch(
        "SELECT snippet FROM memory_snippets WHERE user_id = $1 AND category = $2",
        test_user, "preferenza"
    )
    existing_snippets = [row['snippet'] for row in rows]

    # Test with contradictory fact
    new_snippet = "Marco odia la pizza"

    prompt = f"""Analizza questo nuovo fatto: "{new_snippet}"

Memorie esistenti:
{json.dumps(existing_snippets, ensure_ascii=False)}

Rispondi SOLO con un JSON array contenente gli indici (0-based) delle memorie che CONTRADDICONO il nuovo fatto.

Esempi:
- Nuovo: "Marco odia la pizza" vs Esistente: "Marco ama la pizza" → contraddizione (rispondi [0])
- Nuovo: "Marco ama la pizza margherita" vs Esistente: "Marco ama la pizza" → NON contraddizione (rispondi [])

JSON (solo array di numeri):"""

    print(f"Testing contradiction: '{new_snippet}' vs '{existing_snippets[0]}'")

    try:
        response = requests.post(
            f"{OLLAMA_URL}/api/generate",
            json={
                "model": OLLAMA_MODEL,
                "prompt": prompt,
                "stream": False
            },
            timeout=30
        )

        if response.status_code == 200:
            result = response.json()
            response_text = result.get("response", "")
            print(f"LLM Response: {response_text}")

            # Parse response
            if "[" in response_text and "]" in response_text:
                start = response_text.find("[")
                end = response_text.rfind("]") + 1
                indices = json.loads(response_text[start:end])

                if indices:
                    print(f"✓ Contradiction detected! Indices: {indices}")
                    print(f"  Would mark as obsolete: '{existing_snippets[indices[0]]}'")
                else:
                    print("✗ No contradiction detected (expected [0])")
        else:
            print(f"✗ LLM request failed: {response.status_code}")

    except Exception as e:
        print(f"✗ Error testing contradiction: {e}")

    print()

    # Test 4: View all memories
    print("TEST 4: View all memories")
    print("-" * 60)
    rows = await conn.fetch(
        """
        SELECT snippet, category, importance, created_at
        FROM memory_snippets
        WHERE user_id = $1
        ORDER BY importance DESC
        """,
        test_user
    )

    for i, row in enumerate(rows, 1):
        print(f"{i}. [{row['category']}] {row['snippet']} (importance: {row['importance']})")

    print()

    # Test 5: Cleanup
    print("TEST 5: Cleanup test data")
    print("-" * 60)
    deleted = await conn.execute(
        "DELETE FROM memory_snippets WHERE user_id = $1",
        test_user
    )
    print(f"✓ Deleted all test memories for user: {test_user}\n")

    await conn.close()

    print("=" * 60)
    print("✅ Memory system tests completed!")
    print("\nNote: Full embedding-based semantic search will be available")
    print("after sentence-transformers installation is complete.")

if __name__ == "__main__":
    asyncio.run(test_memory_system())
