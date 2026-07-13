from typing import Dict, Any, List
from langchain_core.messages import AIMessage, SystemMessage, HumanMessage
from langchain_core.runnables import RunnableConfig
from app.agent.state import AgentState
from app.agent.prompts import compile_system_prompt
from app.providers.gemini import GeminiProvider
from app.providers.groq import GroqProvider
from app.providers.openrouter import OpenRouterProvider

# Initialize LLM Providers
gemini_provider = GeminiProvider()
groq_provider = GroqProvider()
openrouter_provider = OpenRouterProvider()

def get_provider(model: str):
  if "gemini" in model:
    return gemini_provider
  elif "llama" in model or "mixtral" in model:
    return groq_provider
  else:
    return openrouter_provider

async def retrieve_context_node(state: AgentState, config: RunnableConfig = None) -> Dict[str, Any]:
  """
  Retrieve long-term facts and memories for the user, plus relevant document chunks.
  """
  config = config or {}
  # 1. Fetch memories from config (epistemic facts)
  memories = config.get("configurable", {}).get("memories", [])
  # Tag memories so system prompt compiler can tell them apart from chunks
  for mem in memories:
    mem["type"] = "memory"

  # 2. Retrieve document chunks from ChromaDB based on similarity search
  user_id = state.get("user_id")
  messages = state.get("messages", [])
  doc_chunks = []

  if user_id and messages:
    # Search for the last user/human query in history
    last_query = ""
    for msg in reversed(messages):
      if msg.type in ["human", "user"]:
        last_query = msg.content
        break

    if last_query:
      try:
        from app.retrieval.vector_store import VectorStore
        vector_store = VectorStore()
        # Query top 5 relevant document chunks
        doc_chunks = await vector_store.query_relevant_chunks(
            user_id=user_id,
            query=last_query,
            k=5
        )
      except Exception as e:
        import logging
        logger = logging.getLogger("agent.nodes")
        logger.error(f"Failed to query VectorStore: {str(e)}")

  # Merge both memories and documents
  retrieved_items = memories + doc_chunks
  steps = list(state.get("steps") or []) + ["retrieve_context"]
  return {"retrieved_documents": retrieved_items, "steps": steps}

async def generate_response_node(state: AgentState, config: RunnableConfig = None) -> Dict[str, Any]:
  """
  Send the prompt to the selected LLM provider and stream chunks via callback.
  """
  config = config or {}
  model = state.get("active_model", "gemini-1.5-flash")
  retrieved_items = state.get("retrieved_documents", [])
  messages = state.get("messages", [])
  
  # Extract on_token callback if any
  on_token = config.get("configurable", {}).get("on_token")
  on_metrics = config.get("configurable", {}).get("on_metrics")
  
  # Format messages for the raw LLM provider
  raw_messages = []
  
  # Inject dynamic system prompt first
  sys_prompt = compile_system_prompt(retrieved_items)
  raw_messages.append({"role": "system", "content": sys_prompt})
  
  # Add conversation history
  for msg in messages:
    # Handle LangChain message classes
    role = "user"
    if msg.type == "ai":
      role = "assistant"
    elif msg.type == "system":
      role = "system"
    raw_messages.append({"role": role, "content": msg.content})

  # Fetch tool declarations from registry
  from app.tools.registry import ToolRegistry
  registry = ToolRegistry()
  tool_schemas = registry.get_tool_schemas()

  # Extract keys from config
  gemini_api_key = config.get("configurable", {}).get("gemini_api_key")
  groq_api_key = config.get("configurable", {}).get("groq_api_key")
  openrouter_api_key = config.get("configurable", {}).get("openrouter_api_key")

  provider = get_provider(model)
  provider_api_key = None
  if "gemini" in model:
    provider_api_key = gemini_api_key
  elif "llama" in model or "mixtral" in model:
    provider_api_key = groq_api_key
  else:
    provider_api_key = openrouter_api_key

  full_response = ""
  tool_calls = []
  
  # Call provider streaming generator with tools
  async for chunk in provider.generate_stream(
      messages=raw_messages,
      model=model,
      tools=tool_schemas,
      api_key=provider_api_key
  ):
    if chunk["event"] == "chunk":
      text = chunk["text"]
      full_response += text
      if on_token:
        await on_token(text)
    elif chunk["event"] == "tool_calls":
      tool_calls.extend(chunk["tool_calls"])
    elif chunk["event"] == "metrics":
      metrics = chunk["metrics"]
      # Calculate hits
      mem_hits = len([x for x in retrieved_items if x.get("type") == "memory" or "category" in x])
      doc_hits = len([x for x in retrieved_items if x.get("type") == "chunk"])
      metrics["memory_hits"] = mem_hits
      metrics["chunks_used"] = doc_hits
      metrics["steps"] = list(state.get("steps") or []) + ["generate_response"]
      metrics["retrieved_context"] = [
          {
              "type": item.get("type", "memory" if "category" in item else "chunk"),
              "filename": item.get("filename", "Memory Fact"),
              "category": item.get("category", ""),
              "content": item.get("content", ""),
              "importance_score": item.get("importance_score"),
              "distance": item.get("distance")
          }
          for item in retrieved_items
      ]
      if on_metrics:
        await on_metrics(metrics)

  steps = list(state.get("steps") or []) + ["generate_response"]
  if tool_calls:
    msg_text = f"Calling tools: {', '.join(tc['name'] for tc in tool_calls)}..."
    ai_msg = AIMessage(content=msg_text)
    return {
        "response_text": msg_text,
        "tool_calls": tool_calls,
        "messages": messages + [ai_msg],
        "steps": steps
    }
  else:
    ai_msg = AIMessage(content=full_response)
    return {
        "response_text": full_response,
        "tool_calls": [],
        "messages": messages + [ai_msg],
        "steps": steps
    }

async def execute_tools_node(state: AgentState, config: RunnableConfig = None) -> Dict[str, Any]:
  """
  Iterates over active tool calls, runs them using ToolRegistry, and appends
  the results as system/user messages to the conversation history.
  """
  config = config or {}
  tool_calls = state.get("tool_calls", []) or []
  messages = list(state.get("messages", []))
  
  from app.tools.registry import ToolRegistry
  registry = ToolRegistry()
  
  new_messages = []
  for tc in tool_calls:
    name = tc["name"]
    arguments = tc["arguments"]
    
    # Run tool execution
    result_text = await registry.call_tool(name, arguments)
    
    # Append tool output to history formatted clearly
    tool_msg = HumanMessage(content=f"[Tool Output: {name}] {result_text}")
    new_messages.append(tool_msg)
    
  steps = list(state.get("steps") or []) + ["execute_tools"]
  return {
      "messages": messages + new_messages,
      "tool_calls": [],
      "steps": steps
  }
