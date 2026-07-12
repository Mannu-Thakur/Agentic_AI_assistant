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

  def _convert_messages(self, messages: List[Dict[str, str]]) -> tuple[List[Dict[str, Any]], Optional[Dict[str, Any]]]:
    """
    Convert messages to Gemini format: roles are 'user' or 'model'.
    Separate system instruction.
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
      model: str = "gemini-1.5-flash",
      temperature: float = 0.7,
      max_tokens: int = 2048,
      tools: Optional[List[Dict[str, Any]]] = None,
  ) -> Dict[str, Any]:
    if self.is_mock:
      await asyncio.sleep(0.5)
      simulated_calls = self._check_mock_tool_call(messages)
      
      if simulated_calls:
          return {
              "text": "",
              "input_tokens": 15,
              "output_tokens": 15,
              "model": model,
              "tool_calls": simulated_calls
          }

      mock_text = f"[Mock Gemini Response for model {model}]: Completed computation. Output matches expectation."
      return {
          "text": mock_text,
          "input_tokens": 15,
          "output_tokens": 20,
          "model": model,
          "tool_calls": []
      }

    contents, system_instruction = self._convert_messages(messages)
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

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={self.api_key}"
    
    async with httpx.AsyncClient(timeout=30.0) as client:
      response = await client.post(url, json=payload)
      if response.status_code != 200:
        raise Exception(f"Gemini API returned error {response.status_code}: {response.text}")
      
      data = response.json()
      
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
      except (KeyError, IndexError):
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
      model: str = "gemini-1.5-flash",
      temperature: float = 0.7,
      max_tokens: int = 2048,
      tools: Optional[List[Dict[str, Any]]] = None,
  ) -> AsyncGenerator[Dict[str, Any], None]:
    if self.is_mock:
      simulated_calls = self._check_mock_tool_call(messages)

      if simulated_calls:
        # Yield tool calls and exit
        yield {
            "event": "tool_calls",
            "tool_calls": simulated_calls
        }
        yield {
            "event": "metrics",
            "metrics": {
                "model_used": model,
                "latency_ms": 100,
                "tokens_input": 15,
                "tokens_output": 15,
                "cost_estimate": 0.0,
                "confidence_score": 0.98,
                "memory_hits": 0
            }
        }
        return

      mock_text = f"Hello from Omni Agent Workspace! This is a real-time streamed response from the **Gemini Mock Adapter**. You selected the model **{model}**.\n\nHere is a code snippet demonstration:\n```python\ndef greet(name): \n    print(f'Hello, {{name}}!')\n```"
      words = mock_text.split(" ")
      input_tokens = len(str(messages)) // 4
      output_tokens = 0
      
      start_time = time.time()
      for i, word in enumerate(words):
        await asyncio.sleep(0.05)
        text_chunk = word + (" " if i < len(words) - 1 else "")
        output_tokens += len(text_chunk) // 4
        yield {
            "event": "chunk",
            "text": text_chunk
        }
      
      latency_ms = int((time.time() - start_time) * 1000)
      yield {
          "event": "metrics",
          "metrics": {
              "model_used": model,
              "latency_ms": latency_ms,
              "tokens_input": input_tokens,
              "tokens_output": output_tokens + 5,
              "cost_estimate": (input_tokens * 0.000075 + output_tokens * 0.0003) / 1000,
              "confidence_score": 0.95,
              "memory_hits": 1
          }
      }
      return

    contents, system_instruction = self._convert_messages(messages)
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

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:streamGenerateContent?alt=sse&key={self.api_key}"
    input_tokens = len(str(messages)) // 4
    output_text = ""
    start_time = time.time()
    tool_calls = []

    async with httpx.AsyncClient(timeout=30.0) as client:
      async with client.stream("POST", url, json=payload) as response:
        if response.status_code != 200:
          raise Exception(f"Gemini streaming API returned error {response.status_code}")
          
        async for line in response.aiter_lines():
          line = line.strip()
          if not line or not line.startswith("data: "):
            continue
            
          raw_data = line[6:]
          try:
            parsed = json.loads(raw_data)
            parts = parsed["candidates"][0]["content"]["parts"]
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
          except (KeyError, IndexError, json.JSONDecodeError):
            continue
            
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
            "memory_hits": 0
        }
    }
