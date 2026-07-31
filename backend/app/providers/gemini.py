import time
import json
import httpx
import asyncio
from typing import AsyncGenerator, Dict, Any, List, Optional
from app.providers.base import BaseLLMProvider
from app.core.config import settings

class GeminiProvider(BaseLLMProvider):
  def __init__(self):
    self.api_key = settings.GEMINI_API_KEY
    self.is_mock = not self.api_key or self.api_key.startswith("mock_")

  def _convert_schema_to_gemini(self, schema: Dict[str, Any]) -> Dict[str, Any]:
    """
    Recursively capitalize all schema types (e.g. string -> STRING) to match Gemini specification.
    """
    new_schema = {}
    for k, v in schema.items():
        if k == "type" and isinstance(v, str):
            new_schema[k] = v.upper()
        elif isinstance(v, dict):
            new_schema[k] = self._convert_schema_to_gemini(v)
        elif isinstance(v, list):
            new_list = []
            for item in v:
                if isinstance(item, dict):
                    new_list.append(self._convert_schema_to_gemini(item))
                else:
                    new_list.append(item)
            new_schema[k] = new_list
        else:
            new_schema[k] = v
    return new_schema

  def _convert_messages(
      self,
      messages: List[Dict[str, str]],
      images: Optional[List[Dict[str, str]]] = None,
  ) -> tuple[List[Dict[str, Any]], Optional[Dict[str, Any]]]:
    """
    Convert messages to Gemini format: roles are 'user' or 'model'.
    Separate system instruction.
    When `images` is provided, the base64 payloads are injected as
    inlineData parts into the LAST user message (multimodal vision).
    """
    contents = []
    system_instruction = None

    for msg in messages:
      role = msg["role"]
      content = msg["content"]

      if role == "system":
        system_instruction = {"parts": [{"text": content}]}
      else:
        # Map assistant -> model
        gemini_role = "model" if role == "assistant" else "user"
        contents.append({
            "role": gemini_role,
            "parts": [{"text": content}]
        })

    # Inject images into the last user turn if provided
    if images:
      # Find the last user content entry
      for entry in reversed(contents):
        if entry["role"] == "user":
          image_parts = [
              {
                  "inlineData": {
                      "mimeType": img["mimeType"],
                      "data": img["base64"],
                  }
              }
              for img in images
          ]
          # Prepend image parts before the text part
          entry["parts"] = image_parts + entry["parts"]
          break

    return contents, system_instruction

  def _check_mock_tool_call(self, messages: List[Dict[str, str]]) -> Optional[List[Dict[str, Any]]]:
    """
    Utility to match patterns in mock mode and return simulated tool calls.
    Ensures that it does not loop on tool execution outputs.
    """
    if not messages:
        return None
        
    last_msg = messages[-1]
    # Only trigger tool call if the last message is from the user and not a tool output
    if last_msg.get("role") != "user":
        return None
        
    content = last_msg.get("content", "")
    if "[Tool Output:" in content:
        return None

    content_lower = content.lower()
    if "calculate" in content_lower:
        expr = content_lower.split("calculate")[-1].strip()
        return [{"name": "calculate", "arguments": {"expression": expr or "2 + 2"}}]
    elif "search" in content_lower:
        query = content_lower.split("search")[-1].replace("for", "", 1).strip()
        return [{"name": "tavily_search", "arguments": {"query": query or "weather in Paris"}}]
    elif "run python" in content_lower or "execute python" in content_lower:
        code = content_lower.split("python")[-1].strip().strip(":").strip()
        return [{"name": "python_sandbox", "arguments": {"code": code or "print('mock output')"}}]
        
    return None

  async def generate(
      self,
      messages: List[Dict[str, str]],
      model: str = "gemini-2.5-flash",
      temperature: float = 0.7,
      max_tokens: int = 2048,
      tools: Optional[List[Dict[str, Any]]] = None,
      api_key: Optional[str] = None,
      images: Optional[List[Dict[str, str]]] = None,
  ) -> Dict[str, Any]:
    key_to_use = api_key or self.api_key
    if not key_to_use or str(key_to_use).startswith("mock_"):
        raise Exception(
            "Gemini API key is missing or invalid. Please configure a valid Gemini API key in Settings to run real-time requests."
        )

    contents, system_instruction = self._convert_messages(messages, images=images)
    payload: Dict[str, Any] = {
        "contents": contents,
        "generationConfig": {
            "temperature": temperature,
            "maxOutputTokens": max_tokens
        }
    }
    if system_instruction:
      payload["systemInstruction"] = system_instruction

    if tools:
      func_declarations = []
      for t in tools:
          func_declarations.append({
              "name": t["name"],
              "description": t["description"],
              "parameters": self._convert_schema_to_gemini(t["parameters"])
          })
      payload["tools"] = [{"functionDeclarations": func_declarations}]

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key_to_use}"
    
    max_retries = 3
    initial_delay = 1.0
    data = None

    for attempt in range(max_retries + 1):
      async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(url, json=payload)
        if response.status_code == 200:
          data = response.json()
          break
        elif response.status_code in (429, 500, 502, 503, 504) and attempt < max_retries:
          delay = initial_delay * (2 ** attempt)
          await asyncio.sleep(delay)
          continue
        elif response.status_code == 429:
          raise Exception(
              "Gemini rate limit exceeded (HTTP 429). "
              "You have reached the API request limit. Please wait a moment before trying again or switch to another model."
          )
        else:
          raise Exception(f"Gemini API returned error {response.status_code}: {response.text}")

    if not data:
      raise Exception("Gemini API returned empty response data.")

    text = ""
    tool_calls = []
    try:
      parts = data["candidates"][0]["content"]["parts"]
      for part in parts:
        if "text" in part:
          text += part["text"]
        if "functionCall" in part:
          fc = part["functionCall"]
          tool_calls.append({
              "name": fc["name"],
              "arguments": fc.get("args", {})
          })
    except (KeyError, IndexError, TypeError):
      text = "[No text generated]"
      
    input_tokens = data.get("usageMetadata", {}).get("promptTokenCount", 0)
    output_tokens = data.get("usageMetadata", {}).get("candidatesTokenCount", 0)
    
    return {
        "text": text,
        "input_tokens": input_tokens or len(str(messages)) // 4,
        "output_tokens": output_tokens or len(text) // 4,
        "model": model,
        "tool_calls": tool_calls
    }


  async def generate_stream(
      self,
      messages: List[Dict[str, str]],
      model: str = "gemini-2.5-flash",
      temperature: float = 0.7,
      max_tokens: int = 2048,
      tools: Optional[List[Dict[str, Any]]] = None,
      api_key: Optional[str] = None,
      images: Optional[List[Dict[str, str]]] = None,
  ) -> AsyncGenerator[Dict[str, Any], None]:
    key_to_use = api_key or self.api_key
    if not key_to_use or str(key_to_use).startswith("mock_"):
      raise Exception(
          "Gemini API key missing or invalid. Please configure your Gemini API key in Settings to stream real-time responses."
      )

    contents, system_instruction = self._convert_messages(messages, images=images)
    payload: Dict[str, Any] = {
        "contents": contents,
        "generationConfig": {
            "temperature": temperature,
            "maxOutputTokens": max_tokens
        }
    }
    if system_instruction:
      payload["systemInstruction"] = system_instruction

    if tools:
      func_declarations = []
      for t in tools:
          func_declarations.append({
              "name": t["name"],
              "description": t["description"],
              "parameters": self._convert_schema_to_gemini(t["parameters"])
          })
      payload["tools"] = [{"functionDeclarations": func_declarations}]

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:streamGenerateContent?alt=sse&key={key_to_use}"
    input_tokens = len(str(messages)) // 4
    output_text = ""
    start_time = time.time()
    tool_calls = []

    max_retries = 3
    initial_delay = 1.0

    for attempt in range(max_retries + 1):
      async with httpx.AsyncClient(timeout=30.0) as client:
        async with client.stream("POST", url, json=payload) as response:
          if response.status_code in (429, 500, 502, 503, 504):
            if attempt < max_retries:
              delay = initial_delay * (2 ** attempt)
              await asyncio.sleep(delay)
              continue
            else:
              raise Exception(
                  "Gemini streaming API rate limit exceeded (HTTP 429). "
                  "You have reached the API request limit. Please wait a moment before trying again or switch to another model."
              )
          elif response.status_code != 200:
            error_body = await response.aread()
            try:
              err_data = json.loads(error_body)
              err_msg = err_data.get("error", {}).get("message") or str(err_data)
            except Exception:
              err_msg = error_body.decode("utf-8", errors="ignore") or f"HTTP {response.status_code}"
            raise Exception(f"Gemini streaming API error ({response.status_code}): {err_msg}")
          
          async for line in response.aiter_lines():
            line = line.strip()
            if not line or not line.startswith("data: "):
              continue
              
            raw_data = line[6:]
            try:
              parsed = json.loads(raw_data)
            except json.JSONDecodeError:
              continue

            # Surface API-level errors embedded in the SSE stream
            if "error" in parsed:
              err_info = parsed["error"]
              err_msg = err_info.get("message") if isinstance(err_info, dict) else str(err_info)
              raise Exception(f"Gemini API error: {err_msg}")

            # Handle finish reasons that indicate no content (e.g. SAFETY, RECITATION)
            candidates = parsed.get("candidates", [])
            if not candidates:
              # Could be a promptFeedback-only chunk — skip silently
              continue

            candidate = candidates[0]
            finish_reason = candidate.get("finishReason", "")
            if finish_reason in ("SAFETY", "RECITATION", "OTHER", "BLOCKED"):
              block_msg = f"Response blocked by Gemini safety filters (reason: {finish_reason})."
              # Check for safety ratings detail
              ratings = candidate.get("safetyRatings", [])
              if ratings:
                blocked = [r["category"] for r in ratings if r.get("blocked")]
                if blocked:
                  block_msg += f" Blocked categories: {', '.join(blocked)}."
              raise Exception(block_msg)

            try:
              parts = candidate["content"]["parts"]
              for part in parts:
                if "text" in part:
                  chunk_text = part["text"]
                  output_text += chunk_text
                  yield {
                      "event": "chunk",
                      "text": chunk_text
                  }
                if "functionCall" in part:
                  fc = part["functionCall"]
                  tool_calls.append({
                      "name": fc["name"],
                      "arguments": fc.get("args", {})
                  })
            except (KeyError, IndexError):
              continue

          break
            
    # Yield tool calls if any were collected
    if tool_calls:
        yield {
            "event": "tool_calls",
            "tool_calls": tool_calls
        }

    latency_ms = int((time.time() - start_time) * 1000)
    out_tokens = len(output_text) // 4
    yield {
        "event": "metrics",
        "metrics": {
            "model_used": model,
            "latency_ms": latency_ms,
            "tokens_input": input_tokens,
            "tokens_output": out_tokens or len(tool_calls) * 5,
            "cost_estimate": (input_tokens * 0.000075 + (out_tokens or len(tool_calls) * 5) * 0.0003) / 1000,
            "confidence_score": 0.92,
            # memory_hits and chunks_used are placeholders; nodes.py overwrites these
            # with the real values derived from retrieved_items after all nodes execute.
            "memory_hits": 0,
            "chunks_used": 0,
        }
    }
