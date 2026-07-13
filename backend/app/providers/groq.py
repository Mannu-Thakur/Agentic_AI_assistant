import time
import json
import httpx
import asyncio
from typing import AsyncGenerator, Dict, Any, List, Optional
from app.providers.base import BaseLLMProvider
from app.core.config import settings

class GroqProvider(BaseLLMProvider):
  def __init__(self):
    self.api_key = settings.GROQ_API_KEY
    self.is_mock = not self.api_key or self.api_key.startswith("mock_")

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
      model: str = "llama-3.1-8b-instant",
      temperature: float = 0.7,
      max_tokens: int = 2048,
      tools: Optional[List[Dict[str, Any]]] = None,
      api_key: Optional[str] = None,
  ) -> Dict[str, Any]:
    key_to_use = api_key or self.api_key
    is_mock_run = not key_to_use or key_to_use.startswith("mock_")

    if is_mock_run:
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

      mock_text = f"[Mock Groq Response for model {model}]: Completed computation. Output matches expectation."
      return {
          "text": mock_text,
          "input_tokens": 15,
          "output_tokens": 20,
          "model": model,
          "tool_calls": []
      }

    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": False
    }

    if tools:
      formatted_tools = []
      for t in tools:
          formatted_tools.append({
              "type": "function",
              "function": {
                  "name": t["name"],
                  "description": t["description"],
                  "parameters": t["parameters"]
              }
          })
      payload["tools"] = formatted_tools

    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {key_to_use}",
        "Content-Type": "application/json"
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
      response = await client.post(url, json=payload, headers=headers)
      if response.status_code != 200:
        raise Exception(f"Groq API returned error {response.status_code}: {response.text}")
      
      data = response.json()
      
      choice = data["choices"][0]["message"]
      text = choice.get("content") or ""
      
      tool_calls = []
      raw_tool_calls = choice.get("tool_calls", [])
      for rtc in raw_tool_calls:
          if rtc.get("type") == "function":
              func = rtc.get("function", {})
              try:
                  args = json.loads(func.get("arguments", "{}"))
              except Exception:
                  args = {}
              tool_calls.append({
                  "name": func.get("name"),
                  "arguments": args
              })

      input_tokens = data.get("usage", {}).get("prompt_tokens", 0)
      output_tokens = data.get("usage", {}).get("completion_tokens", 0)
      
      return {
          "text": text,
          "input_tokens": input_tokens,
          "output_tokens": output_tokens,
          "model": model,
          "tool_calls": tool_calls
      }

  async def generate_stream(
      self,
      messages: List[Dict[str, str]],
      model: str = "llama-3.1-8b-instant",
      temperature: float = 0.7,
      max_tokens: int = 2048,
      tools: Optional[List[Dict[str, Any]]] = None,
      api_key: Optional[str] = None,
  ) -> AsyncGenerator[Dict[str, Any], None]:
    key_to_use = api_key or self.api_key
    is_mock_run = not key_to_use or key_to_use.startswith("mock_")

    if is_mock_run:
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

      mock_text = f"Hello from Omni Agent Workspace! This is a real-time streamed response from the **Groq Llama-3 Adapter**. You selected the model **{model}**.\n\nHere is a code snippet demonstration:\n```python\ndef run_sandbox():\n    print('Sandboxed computation complete!')\n```"
      words = mock_text.split(" ")
      input_tokens = len(str(messages)) // 4
      output_tokens = 0
      
      start_time = time.time()
      for i, word in enumerate(words):
        await asyncio.sleep(0.04)
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
              "cost_estimate": (input_tokens * 0.00005 + output_tokens * 0.00015) / 1000,
              "confidence_score": 0.88,
              "memory_hits": 1
          }
      }
      return

    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": True
    }

    if tools:
      formatted_tools = []
      for t in tools:
          formatted_tools.append({
              "type": "function",
              "function": {
                  "name": t["name"],
                  "description": t["description"],
                  "parameters": t["parameters"]
              }
          })
      payload["tools"] = formatted_tools

    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {key_to_use}",
        "Content-Type": "application/json"
    }

    input_tokens = len(str(messages)) // 4
    output_text = ""
    start_time = time.time()
    accumulated_tool_calls = {}

    async with httpx.AsyncClient(timeout=30.0) as client:
      async with client.stream("POST", url, json=payload, headers=headers) as response:
        if response.status_code != 200:
          raise Exception(f"Groq streaming API returned error {response.status_code}")
          
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
              delta = parsed["choices"][0]["delta"]
              
              chunk_text = delta.get("content", "")
              if chunk_text:
                output_text += chunk_text
                yield {
                    "event": "chunk",
                    "text": chunk_text
                }
              
              tool_calls_delta = delta.get("tool_calls", [])
              for tc in tool_calls_delta:
                  idx = tc.get("index", 0)
                  if idx not in accumulated_tool_calls:
                      accumulated_tool_calls[idx] = {
                          "name": "",
                          "arguments": ""
                      }
                  
                  func_delta = tc.get("function", {})
                  if "name" in func_delta:
                      accumulated_tool_calls[idx]["name"] = func_delta["name"]
                  if "arguments" in func_delta:
                      accumulated_tool_calls[idx]["arguments"] += func_delta["arguments"]
            except (KeyError, IndexError, json.JSONDecodeError):
              continue
              
    # Yield tool calls if any were parsed
    tool_calls = []
    for tc in accumulated_tool_calls.values():
        try:
            args = json.loads(tc["arguments"]) if tc["arguments"] else {}
        except Exception:
            args = {}
        tool_calls.append({
            "name": tc["name"],
            "arguments": args
        })
        
    if tool_calls:
        yield {
            "event": "tool_calls",
            "tool_calls": tool_calls
        }

    latency_ms = int((time.time() - start_time) * 1000)
    out_tokens = len(output_text) or len(tool_calls) * 5
    yield {
        "event": "metrics",
        "metrics": {
            "model_used": model,
            "latency_ms": latency_ms,
            "tokens_input": input_tokens,
            "tokens_output": out_tokens,
            "cost_estimate": (input_tokens * 0.00005 + out_tokens * 0.00015) / 1000,
            "confidence_score": 0.85,
            "memory_hits": 0
        }
    }
