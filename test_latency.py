#!/usr/bin/env python3
"""
Test di latenza per Jarvis AI Assistant
Misura i tempi di risposta di tutti i componenti del sistema
"""

import time
import requests
import json
from typing import Dict, List
from statistics import mean, median, stdev

# Configurazione endpoint
ENDPOINTS = {
    "orchestrator": "http://localhost:8000",
    "stt": "http://localhost:8001",
    "tts": "http://localhost:8002",
    "tts_mms": "http://localhost:8003",
}

# Messaggi di test per il chat endpoint
TEST_MESSAGES = [
    "ciao",  # Risposta semplice
    "come stai?",  # Risposta breve
    "che ore sono?",  # Funzione (smart model)
    "dimmi qualcosa di interessante",  # Risposta media
]

# Testi per TTS
TEST_TTS_TEXTS = [
    "Ciao",
    "Ciao, come posso aiutarti?",
    "La temperatura attuale è di ventidue gradi celsius con cielo sereno.",
]


class LatencyTester:
    def __init__(self):
        self.results: Dict[str, List[float]] = {}

    def measure_request(self, name: str, method: str, url: str, **kwargs) -> float:
        """Misura il tempo di una singola richiesta HTTP"""
        start = time.time()
        try:
            if method.upper() == "GET":
                response = requests.get(url, timeout=120, **kwargs)
            else:
                response = requests.post(url, timeout=120, **kwargs)

            elapsed = time.time() - start

            if response.status_code == 200:
                print(f"✓ {name}: {elapsed:.3f}s")
                return elapsed
            else:
                print(f"✗ {name}: HTTP {response.status_code}")
                return -1
        except Exception as e:
            print(f"✗ {name}: {str(e)}")
            return -1

    def test_health_checks(self):
        """Test degli health endpoint"""
        print("\n=== HEALTH CHECKS ===")
        for service, base_url in ENDPOINTS.items():
            latency = self.measure_request(
                f"{service} health",
                "GET",
                f"{base_url}/health"
            )
            if latency > 0:
                self.results.setdefault(f"{service}_health", []).append(latency)

    def test_chat_simple(self, iterations: int = 5):
        """Test chat con messaggi semplici (fast model)"""
        print(f"\n=== CHAT ENDPOINT (FAST MODEL) - {iterations} iterazioni ===")

        for i in range(iterations):
            message = TEST_MESSAGES[i % len(TEST_MESSAGES)]
            if "che ore" in message:
                continue  # Salta messaggi che triggherano smart model

            print(f"\nIterazione {i+1}/{iterations}: '{message}'")
            latency = self.measure_request(
                f"chat",
                "POST",
                f"{ENDPOINTS['orchestrator']}/chat",
                json={"message": message, "user_id": "latency_test"}
            )

            if latency > 0:
                self.results.setdefault("chat_fast", []).append(latency)

            time.sleep(1)  # Pausa tra richieste

    def test_chat_smart(self, iterations: int = 3):
        """Test chat con function calling (smart model)"""
        print(f"\n=== CHAT ENDPOINT (SMART MODEL) - {iterations} iterazioni ===")

        smart_messages = ["che ore sono?", "dimmi la data di oggi", "info sistema"]

        for i in range(iterations):
            message = smart_messages[i % len(smart_messages)]
            print(f"\nIterazione {i+1}/{iterations}: '{message}'")

            latency = self.measure_request(
                f"chat smart",
                "POST",
                f"{ENDPOINTS['orchestrator']}/chat",
                json={"message": message, "user_id": "latency_test"}
            )

            if latency > 0:
                self.results.setdefault("chat_smart", []).append(latency)

            time.sleep(1)

    def test_tts(self, iterations: int = 3):
        """Test sintesi vocale"""
        print(f"\n=== TTS ENDPOINT - {iterations} iterazioni ===")

        for i in range(iterations):
            text = TEST_TTS_TEXTS[i % len(TEST_TTS_TEXTS)]
            print(f"\nIterazione {i+1}/{iterations}: '{text}'")

            latency = self.measure_request(
                f"tts",
                "POST",
                f"{ENDPOINTS['tts']}/speak",
                json={"text": text}
            )

            if latency > 0:
                self.results.setdefault("tts", []).append(latency)

    def test_memory_retrieval(self, iterations: int = 5):
        """Test recupero memorie"""
        print(f"\n=== MEMORY RETRIEVAL - {iterations} iterazioni ===")

        for i in range(iterations):
            print(f"\nIterazione {i+1}/{iterations}")

            latency = self.measure_request(
                f"memory retrieval",
                "GET",
                f"{ENDPOINTS['orchestrator']}/memories/latency_test?limit=10"
            )

            if latency > 0:
                self.results.setdefault("memory_retrieval", []).append(latency)

    def test_functions_list(self, iterations: int = 5):
        """Test lista funzioni disponibili"""
        print(f"\n=== FUNCTIONS LIST - {iterations} iterazioni ===")

        for i in range(iterations):
            latency = self.measure_request(
                f"functions list",
                "GET",
                f"{ENDPOINTS['orchestrator']}/functions"
            )

            if latency > 0:
                self.results.setdefault("functions_list", []).append(latency)

    def print_summary(self):
        """Stampa il riepilogo delle statistiche"""
        print("\n" + "="*70)
        print("RIEPILOGO LATENZE")
        print("="*70)

        if not self.results:
            print("Nessun risultato disponibile")
            return

        for test_name, latencies in sorted(self.results.items()):
            if not latencies:
                continue

            print(f"\n{test_name.upper().replace('_', ' ')}:")
            print(f"  Richieste: {len(latencies)}")
            print(f"  Media:     {mean(latencies):.3f}s")
            print(f"  Mediana:   {median(latencies):.3f}s")
            print(f"  Min:       {min(latencies):.3f}s")
            print(f"  Max:       {max(latencies):.3f}s")
            if len(latencies) > 1:
                print(f"  Std Dev:   {stdev(latencies):.3f}s")

        # Calcola latenza end-to-end stimata
        print("\n" + "-"*70)
        print("STIMA LATENZA END-TO-END (Telegram → Risposta):")
        print("-"*70)

        if "chat_fast" in self.results and self.results["chat_fast"]:
            fast_avg = mean(self.results["chat_fast"])
            print(f"  Fast model (conversazione):  ~{fast_avg:.2f}s")

        if "chat_smart" in self.results and self.results["chat_smart"]:
            smart_avg = mean(self.results["chat_smart"])
            print(f"  Smart model (function call): ~{smart_avg:.2f}s")

        if "tts" in self.results and self.results["tts"]:
            tts_avg = mean(self.results["tts"])
            print(f"  + TTS synthesis:             ~{tts_avg:.2f}s")

        print("\nNOTE:")
        print("  - STT non testato (richiede file audio)")
        print("  - Tempi reali possono variare in base a carico sistema e lunghezza input")
        print("  - Smart model più lento ma necessario per function calling")


def main():
    print("="*70)
    print("TEST DI LATENZA - JARVIS AI ASSISTANT")
    print("="*70)

    tester = LatencyTester()

    # Verifica che i servizi siano raggiungibili
    print("\nVerifica connessione ai servizi...")
    try:
        tester.test_health_checks()
    except Exception as e:
        print(f"\n✗ Errore nella connessione ai servizi: {e}")
        print("Assicurati che i container Docker siano attivi:")
        print("  docker-compose ps")
        return

    # Esegui i test
    try:
        tester.test_functions_list(iterations=3)
        tester.test_memory_retrieval(iterations=3)
        tester.test_tts(iterations=3)
        tester.test_chat_simple(iterations=5)
        tester.test_chat_smart(iterations=3)
    except KeyboardInterrupt:
        print("\n\nTest interrotto dall'utente")
    except Exception as e:
        print(f"\n✗ Errore durante i test: {e}")

    # Stampa il riepilogo
    tester.print_summary()


if __name__ == "__main__":
    main()
