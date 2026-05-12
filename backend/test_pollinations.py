import asyncio
import json
import requests
import sys

def test_pollinations_api():
    markdown = """
    # Books to Scrape
    - A Light in the Attic. Price: £51.77. Rating: Three. In stock.
    - Tipping the Velvet. Price: £53.74. Rating: One. In stock.
    - Soumission. Price: £50.10. Rating: One. Out of stock.
    """
    
    prompt = f"Extract the following fields from this text:\nbook_title (string), price (currency), rating (string), availability (string).\nText: {markdown}"
    
    try:
        response = requests.post(
            "https://text.pollinations.ai/openai",
            json={
                "messages": [
                    {"role": "system", "content": "You are a precise data extraction assistant. Output ONLY valid JSON array and nothing else."},
                    {"role": "user", "content": prompt}
                ],
                "model": "openai",
                "temperature": 0.1,
                "response_format": {"type": "json_object"}
            },
            timeout=30
        )
        print("Status code:", response.status_code)
        
        # Depending on the model, response_format might not be supported. Let's see.
        raw_text = response.json()
        content = raw_text["choices"][0]["message"]["content"]
        
        # simple parse
        import re
        match = re.search(r'\[.*\]', content, re.DOTALL)
        if match:
            parsed = json.loads(match.group(0))
        else:
            parsed = json.loads(content)
        print(f"Extracted json:\n{json.dumps(parsed, indent=2)}")
        
    except Exception as e:
        print("Error:", e)

test_pollinations_api()
