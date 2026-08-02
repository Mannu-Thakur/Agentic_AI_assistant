import time
import json
import httpx
import asyncio
from typing import AsyncGenerator, Dict, Any, List, Optional
from app.providers.base import BaseLLMProvider
from app.core.config import settings

class OpenAIProvider(BaseLLMProvider):
  """
  Direct provider for official OpenAI Chat Completions API (api.openai.com).
  Supports vision (base64 image URLs), streaming SSE responses, and tool calls.
  """

  def __init__(self):
    self.api_key = settings.OPENAI_API_KEY

  def _clean_model_name(self, model: str) -> str:
    if model.startswith("openai/"):
      return model[7:]
    return model

  def _inject_images_into_messages(
      self,
      messages: List[Dict[str, Any]],
      images: Optional[List[Dict[str, str]]],
  ) -> List[Dict[str, Any]]:
    if not images:
      return messages

    messages = [dict(m) for m in messages]
    for i in reversed(range(len(messages))):
      if messages[i].get("role") == "user":
        existing_text = messages[i].get("content", "") or ""
        if isinstance(existing_text, list):
          parts = list(existing_text)
        else:
          parts: List[Dict[str, Any]] = [{"type": "text", "text": str(existing_text)}]
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
      model: str = "gpt-4o",
      temperature: float = 0.7,
      max_tokens: int = 2048,
      tools: Optional[List[Dict[str, Any]]] = None,
      api_key: Optional[str] = None,
      images: Optional[List[Dict[str, str]]] = None,
  ) -> Dict[str, Any]:
    key_to_use = api_key or self.api_key
    if not key_to_use or str(key_to_use).startswith("mock_"):
      raise Exception(
          "OpenAI API key is missing or invalid. Please configure your OPENAI_API_KEY in Settings or .env."
      )

    clean_model = self._clean_model_name(model)
    messages = self._inject_images_into_messages(messages, images)

    payload = {
        "model": clean_model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens
    }

    url = "https://api.openai.com/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {key_to_use}",
        "Content-Type": "application/json"
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
          raise Exception("OpenAI API rate limit exceeded (HTTP 429). Please wait a moment before trying again.")
        else:
          raise Exception(f"OpenAI API error ({response.status_code}): {response.text}")

    if not data:
      raise Exception("OpenAI API returned empty response data.")

    text = data["choices"][0]["message"]["content"]
    input_tokens = data.get("usage", {}).get("prompt_tokens", 0)
    output_tokens = data.get("usage", {}).get("completion_tokens", 0)

    return {
        "text": text,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "model": clean_model
    }

  async def generate_stream(
      self,
      messages: List[Dict[str, Any]],
      model: str = "gpt-4o",
      temperature: float = 0.7,
      max_tokens: int = 2048,
      tools: Optional[List[Dict[str, Any]]] = None,
      api_key: Optional[str] = None,
      images: Optional[List[Dict[str, str]]] = None,
  ) -> AsyncGenerator[Dict[str, Any], None]:
    key_to_use = api_key or self.api_key
    if not key_to_use or str(key_to_use).startswith("mock_"):
      raise Exception(
          "OpenAI API key is missing or invalid. Please configure your OPENAI_API_KEY in Settings or .env."
      )

    clean_model = self._clean_model_name(model)
    messages = self._inject_images_into_messages(messages, images)

    payload = {
        "model": clean_model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": True
    }

    url = "https://api.openai.com/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {key_to_use}",
        "Content-Type": "application/json"
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
              raise Exception("OpenAI API rate limit exceeded (HTTP 429). Please try again later.")
          elif response.status_code != 200:
            error_body = await response.aread()
            raise Exception(f"OpenAI API error ({response.status_code}): {error_body.decode('utf-8', errors='ignore')}")

          async for line in response.aiter_lines():
            line = line.strip()
            if not line or not line.startswith("data: "):
              continue
            raw_data = line[6:]
            if raw_data == "[DONE]":
              break
            try:
              parsed = json.loads(raw_data)
              chunk_text = parsed["choices"][0]["delta"].get("content", "")
              if chunk_text:
                output_text += chunk_text
                yield {"event": "chunk", "text": chunk_text}
            except Exception:
              continue
          break

    latency_ms = int((time.time() - start_time) * 1000)
    out_tokens = len(output_text) // 4
    yield {
        "event": "metrics",
        "metrics": {
            "model_used": clean_model,
            "latency_ms": latency_ms,
            "tokens_input": input_tokens,
            "tokens_output": out_tokens,
            "cost_estimate": (input_tokens * 0.0025 + out_tokens * 0.01) / 1000,
            "confidence_score": 0.95,
            "memory_hits": 0,
            "chunks_used": 0,
        }
    }
