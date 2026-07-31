import time
import json
import httpx
import asyncio
from typing import AsyncGenerator, Dict, Any, List, Optional
from app.providers.base import BaseLLMProvider
from app.core.config import settings

def _trim_messages_for_token_budget(messages: List[Dict[str, str]], max_chars: int = 16000) -> List[Dict[str, str]]:
    """
    Ensures total message payload stays within Groq's payload & token limit (~16k chars).
    Preserves system instruction at [0] and the latest user turn at [-1].
    Trims middle messages if payload exceeds max_chars.

    System prompt is capped at 60% of max_chars to guarantee room for conversation
    history — this prevents RAG chunks embedded in the system prompt from eating
    the entire budget and triggering HTTP 413 errors.
    """
    if not messages:
        return []
    total_len = sum(len(m.get("content", "")) for m in messages)
    if total_len <= max_chars:
        return messages

    sys_msg = [m for m in messages if m.get("role") == "system"]
    non_sys = [m for m in messages if m.get("role") != "system"]

    # ── Cap the system prompt at 60% of max_chars ─────────────────────────────
    # The system prompt embeds RAG chunks which can be very large. We cap it so
    # that conversation history always has room — preventing HTTP 413 errors.
    sys_budget = int(max_chars * 0.60)
    if sys_msg:
        sys_content = sys_msg[0].get("content", "")
        if len(sys_content) > sys_budget:
            sys_msg = [{
                **sys_msg[0],
                "content": sys_content[:sys_budget] + "\n[System Context Truncated to fit token budget]"
            }]

    if not non_sys:
        return sys_msg

    last_user_msg = non_sys[-1]
    middle_msgs = non_sys[:-1]

    # Budget remaining for conversation history after system prompt + last user message
    sys_used = sum(len(m.get("content", "")) for m in sys_msg)
    last_user_len = len(last_user_msg.get("content", ""))
    budget = max_chars - sys_used - last_user_len

    # Keep adding middle messages from right (newest first) until budget is full
    kept_middle = []
    current_size = 0
    for m in reversed(middle_msgs):
        m_len = len(m.get("content", ""))
        # Never use a negative or zero budget floor
        if budget > 0 and current_size + m_len <= budget:
            kept_middle.insert(0, m)
            current_size += m_len
        else:
            break

    res = sys_msg + kept_middle + [last_user_msg]
    return res


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
    if not key_to_use or str(key_to_use).startswith("mock_"):
        raise Exception(
            "Groq API key is missing or invalid. Please configure a valid Groq API key in Settings to run real-time requests."
        )

    trimmed_messages = _trim_messages_for_token_budget(messages, max_chars=16000)

    payload = {
        "model": model,
        "messages": trimmed_messages,
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

    max_retries = 3
    initial_delay = 1.0
    data = None

    for attempt in range(max_retries + 1):
      async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(url, json=payload, headers=headers)
        if response.status_code == 200:
          data = response.json()
          break
        elif response.status_code == 413:
          # Payload too large — perform emergency budget trim and retry with progressively smaller budgets
          if attempt < max_retries:
            emergency_budget = 6000 - (attempt * 1000)  # 6000 → 5000 → 4000 chars
            payload["messages"] = _trim_messages_for_token_budget(trimmed_messages, max_chars=max(emergency_budget, 3000))
            await asyncio.sleep(0.5)
            continue
          else:
            raise Exception("Request payload size exceeded Groq context limit (HTTP 413). Please start a new chat session.")
        elif response.status_code in (429, 500, 502, 503, 504) and attempt < max_retries:
          delay = initial_delay * (2 ** attempt)
          await asyncio.sleep(delay)
          continue
        elif response.status_code == 429:
          raise Exception(
              "Groq rate limit exceeded (HTTP 429). "
              "You have reached the API request limit. Please wait a moment before trying again or switch to another model."
          )
        else:
          raise Exception(f"Groq API returned error {response.status_code}: {response.text}")
      
    if not data:
      raise Exception("Groq API returned empty response data.")

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
    if not key_to_use or str(key_to_use).startswith("mock_"):
      raise Exception(
          "Groq API key missing or invalid. Please configure your Groq API key in Settings to stream real-time responses."
      )

    trimmed_messages = _trim_messages_for_token_budget(messages, max_chars=16000)

    payload = {
        "model": model,
        "messages": trimmed_messages,
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

    input_tokens = len(str(trimmed_messages)) // 4
    output_text = ""
    start_time = time.time()
    accumulated_tool_calls = {}

    max_retries = 3
    initial_delay = 1.0

    for attempt in range(max_retries + 1):
      async with httpx.AsyncClient(timeout=30.0) as client:
        async with client.stream("POST", url, json=payload, headers=headers) as response:
          if response.status_code == 413:
            if attempt < max_retries:
              emergency_budget = 6000 - (attempt * 1000)  # 6000 → 5000 → 4000 chars
              payload["messages"] = _trim_messages_for_token_budget(trimmed_messages, max_chars=max(emergency_budget, 3000))
              await asyncio.sleep(0.5)
              continue
            else:
              raise Exception("Request payload size exceeded Groq context limit (HTTP 413). Please start a new chat session.")
          elif response.status_code in (429, 500, 502, 503, 504):
            if attempt < max_retries:
              delay = initial_delay * (2 ** attempt)
              await asyncio.sleep(delay)
              continue
            else:
              raise Exception(
                  "Groq streaming API rate limit exceeded (HTTP 429). "
                  "You have reached the API request limit. Please wait a moment before trying again or switch to another model."
              )
          elif response.status_code != 200:
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
          
          break
              
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
            # memory_hits and chunks_used are placeholders; nodes.py overwrites these
            # with the real values derived from retrieved_items after all nodes execute.
            "memory_hits": 0,
            "chunks_used": 0,
        }
    }
