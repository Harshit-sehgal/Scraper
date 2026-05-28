import logging
import json
from typing import List
from bs4 import BeautifulSoup
from markdownify import markdownify as md

from app.config import settings
from app.models import SchemaField
from app.llm_bridge import llm_json

logger = logging.getLogger(__name__)

def html_to_markdown(html: str) -> str:
    """Convert raw HTML to compact markdown, stripping noise."""
    try:
        soup = BeautifulSoup(html, "html.parser")
        
        # Remove noisy tags
        for tag in soup(["script", "style", "noscript", "meta", "head", "svg", "path", "nav", "footer", "iframe"]):
            tag.decompose()
            
        cleaned_html = str(soup)
        
        # Convert to markdown
        markdown_text = md(cleaned_html, heading_style="ATX", strip=["img", "a"])
        
        # Clean up excessive newlines and whitespace
        lines = [line.strip() for line in markdown_text.splitlines() if line.strip()]
        return "\n".join(lines)
    except Exception as e:
        logger.warning(f"Failed to convert HTML to markdown: {e}")
        return ""

async def extract_with_llm(html: str, schema_fields: List[SchemaField], url: str) -> List[dict]:
    """
    Extract structured data directly from HTML using LLM parsing of Markdown.
    Returns a list of extracted record dictionaries.
    """
    logger.info(f"[LLMExtractor] Extracting data directly via LLM for {url}")
    
    markdown_content = html_to_markdown(html)
    if not markdown_content:
        logger.warning("[LLMExtractor] Markdown content is empty. Aborting.")
        return []
        
    # Build schema definition for the prompt
    schema_def = {}
    for f in schema_fields:
        schema_def[f.name] = {
            "type": f.field_type.value,
            "description": f.description or "Extract this value",
            "required": f.required
        }

    system_prompt = (
        "You are a precise data extraction engine. You extract structured data from Markdown content into a JSON array of objects.\n"
        "Return ONLY valid JSON. The root of the JSON MUST be a single array `[...]` containing objects.\n"
        "If no data matches, return an empty array `[]`.\n"
        "Do not wrap the JSON in markdown codeblocks (e.g. ```json), just output the raw JSON string.\n"
    )
    
    user_prompt = (
        f"Source URL: {url}\n\n"
        f"Expected Schema per record:\n{json.dumps(schema_def, indent=2)}\n\n"
        "Extract all matching records from the following Markdown content. Ensure data types match the schema.\n\n"
        f"--- MARKDOWN CONTENT ---\n{markdown_content[:20000]}\n--- END MARKDOWN ---"
    )
    
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt}
    ]
    
    try:
        # We use a slightly higher timeout for direct extraction
        result = await llm_json(messages, temperature=0.0, timeout=max(settings.LLM_TIMEOUT, 30))
        
        if not result:
            return []
            
        # Handle cases where LLM returns an object wrapping the array (e.g., {"records": [...]})
        if isinstance(result, dict):
            # Look for the first list in the dictionary values
            for v in result.values():
                if isinstance(v, list):
                    return v
            # If no list found, perhaps the dict itself is a single record?
            return [result]
            
        if isinstance(result, list):
            return result
            
        return []
    except Exception as e:
        logger.error(f"[LLMExtractor] LLM extraction failed: {e}")
        return []
