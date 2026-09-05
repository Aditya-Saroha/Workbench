import httpx
import asyncio
import time

async def test_boot():
    print(">>> 1. Python script started.")
    print(">>> 2. Sending request to Ollama (waiting for VRAM transfer)...")
    start_time = time.time()
    
    try:
        async with httpx.AsyncClient(timeout=None) as client:
            response = await client.post(
                "http://127.0.0.1:11434/api/generate",
                json={
                    "model": "llama3.2:1b", 
                    "prompt": "Say the word 'awake'.", 
                    "stream": False
                }
            )
            
        elapsed = time.time() - start_time
        print(f">>> 3. SUCCESS! Ollama replied in {elapsed:.1f} seconds.")
        print(f">>> 4. Ollama said: {response.json().get('response')}")
        
    except Exception as e:
        print(f">>> 3. FAILED! Python hit a wall: {e}")

asyncio.run(test_boot())