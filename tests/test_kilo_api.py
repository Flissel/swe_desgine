"""Test OpenRouter API connection."""
import asyncio
import os
import httpx

async def test_kilo():
    api_key = os.environ.get('OPENROUTER_API_KEY')
    print(f'API Key available: {bool(api_key)}')
    if not api_key:
        print('ERROR: OPENROUTER_API_KEY not set!')
        return

    url = 'https://openrouter.ai/api/v1/chat/completions'
    headers = {
        'Authorization': f'Bearer {api_key}',
        'Content-Type': 'application/json',
    }
    payload = {
        'model': 'openai/gpt-4o-mini',
        'messages': [{'role': 'user', 'content': 'Say hello in one word'}],
        'max_tokens': 10
    }

    print('Calling OpenRouter API...')
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(url, headers=headers, json=payload)
            print(f'Status: {response.status_code}')
            if response.status_code == 200:
                data = response.json()
                print(f'Response: {data["choices"][0]["message"]["content"]}')
                print('SUCCESS: OpenRouter API works!')
            else:
                print(f'Error: {response.text}')
    except Exception as e:
        print(f'Exception: {e}')

if __name__ == "__main__":
    asyncio.run(test_kilo())
