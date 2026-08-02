import time
import json
import httpx
import asyncio
from typing import AsyncGenerator, Dict, Any, List, Optional
from app.providers.base import BaseLLMProvider
from app.core.config import settings

class OpenRouterProvider(BaseLLMProvider):
  def __init__(self):
    # Server-level key fallback; runtime per-request key takes priority via api_key param
    self.api_key = settings.OPENROUTER_API_KEY

  def _inject_images_into_messages(
      self,
      messages: List[Dict[str, Any]],
      images: Optional[List[Dict[str, str]]],
  ) -> List[Dict[str, Any]]:
    """
    Convert the last user message into an OpenAI-compatible multimodal content
    array so that vision-capable models on OpenRouter can see the images.

    Each image dict must have keys: ``base64`` (raw base64 string) and
    ``mimeType`` (e.g. ``"image/jpeg"``).

    Returns a **new** list; original messages are not mutated.
    """
    if not images:
        return messages

    messages = [dict(m) for m in messages]  # shallow copy each message

    # Find last user message and upgrade its content to a multimodal array
    for i in reversed(range(len(messages))):
        if messages[i].get("role") == "user":
            existing_text = messages[i].get("content", "") or ""
            parts: List[Dict[str, Any]] = [{"type": "text", "text": existing_text}]
            for img in images:
                mime = img.get("mimeType", "image/jpeg")
                b64  = img.get("base64", "")
                parts.append({
                    "type": "image_url",
                    "image_url": {"url": f"data:{mime};base64,{b64}"}
                })
            messages[i]["content"] = parts
            break

    return messages

  async def generate(
      self,
      messages: List[Dict[str, Any]],
      model: str,
      temperature: float = 0.7,
      max_tokens: int = 2048,
      tools: Optional[List[Dict[str, Any]]] = None,
      api_key: Optional[str] = None,
      images: Optional[List[Dict[str, str]]] = None,
  ) -> Dict[str, Any]:
    key_to_use = api_key or self.api_key
    if not key_to_use or str(key_to_use).startswith("mock_"):
        raise Exception(
            "OpenRouter API key is missing or invalid. Please configure a valid OpenRouter API key in Settings to run real-time requests."
        )

    # Inject images into the last user turn if provided
    messages = self._inject_images_into_messages(messages, images)

    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens
    }

    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {key_to_use}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://localhost:3000",  # Site URL for OpenRouter ranking
        "X-Title": "Omni Agentic Workspace"
    }

    max_retries = 3
    initial_delay = 1.0
    data = None

    for attempt in range(max_retries + 1):
      async with httpx.AsyncClient(timeout=45.0) as client:
        response = await client.post(url, json=payload, headers=headers)
        if response.status_code == 200:
          data = response.json()
          break
        elif response.status_code in (429, 500, 502, 503, 504) and attempt < max_retries:
          delay = initial_delay * (2 ** attempt)
          await asyncio.sleep(delay)
          continue
        elif response.status_code == 429:
          raise Exception(
              "OpenRouter rate limit exceeded (HTTP 429). "
              "You have reached the API request limit. Please wait a moment before trying again or switch to another model."
          )
        else:
          raise Exception(f"OpenRouter API returned error {response.status_code}: {response.text}")

    if not data:
      raise Exception("OpenRouter API returned empty response data.")

    text = data["choices"][0]["message"]["content"]
    input_tokens = data.get("usage", {}).get("prompt_tokens", 0)
    output_tokens = data.get("usage", {}).get("completion_tokens", 0)
    
    return {
        "text": text,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "model": model
    }


  async def generate_stream(
      self,
      messages: List[Dict[str, Any]],
      model: str,
      temperature: float = 0.7,
      max_tokens: int = 2048,
      tools: Optional[List[Dict[str, Any]]] = None,
      api_key: Optional[str] = None,
      images: Optional[List[Dict[str, str]]] = None,
  ) -> AsyncGenerator[Dict[str, Any], None]:
    key_to_use = api_key or self.api_key
    is_mock_run = not key_to_use or key_to_use.startswith("mock_")

    if is_mock_run:
      raise Exception(
          "OpenRouter API key missing or invalid. Please configure your OpenRouter API key in Settings to stream real-time responses."
      )

    # Inject images into the last user turn if provided
    messages = self._inject_images_into_messages(messages, images)

    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": True
    }

    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {key_to_use}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://localhost:3000",
        "X-Title": "Omni Agentic Workspace"
    }

    input_tokens = len(str(messages)) // 4
    output_text = ""
    start_time = time.time()

    max_retries = 3
    initial_delay = 1.0

    for attempt in range(max_retries + 1):
      async with httpx.AsyncClient(timeout=45.0) as client:
        async with client.stream("POST", url, json=payload, headers=headers) as response:
          if response.status_code in (429, 500, 502, 503, 504):
            if attempt < max_retries:
              delay = initial_delay * (2 ** attempt)
              await asyncio.sleep(delay)
              continue
            else:
              raise Exception(
                  "OpenRouter streaming API rate limit exceeded (HTTP 429). "
                  "You have reached the API request limit. Please wait a moment before trying again or switch to another model."
              )
          elif response.status_code != 200:
            raise Exception(f"OpenRouter streaming API returned error {response.status_code}")
          
          async for line in response.aiter_lines():
            line = line.strip()
            if not line:
              continue
              
            if line.startswith("data: "):
              raw_data = line[6:]
              if raw_data == "[DONE]":
                break
                
              try:
                parsed = json.loads(raw_data)
                chunk_text = parsed["choices"][0]["delta"].get("content", "")
                if chunk_text:
                  output_text += chunk_text
                  yield {
                      "event": "chunk",
                      "text": chunk_text
                  }
              except (KeyError, IndexError, json.JSONDecodeError):
                continue
          
          break
              
    latency_ms = int((time.time() - start_time) * 1000)
    out_tokens = len(output_text) // 4
    yield {
        "event": "metrics",
        "metrics": {
            "model_used": model,
            "latency_ms": latency_ms,
            "tokens_input": input_tokens,
            "tokens_output": out_tokens,
            "cost_estimate": (input_tokens * 0.00015 + out_tokens * 0.00045) / 1000,
            "confidence_score": 0.88,
            # memory_hits and chunks_used are placeholders; nodes.py overwrites these
            # with the real values derived from retrieved_items after all nodes execute.
            "memory_hits": 0,
            "chunks_used": 0,
        }
    }
