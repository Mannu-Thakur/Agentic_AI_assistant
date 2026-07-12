from typing import List, Dict, Any

def compile_system_prompt(retrieved_items: List[Dict[str, Any]]) -> str:
  system_base = (
      "You are a production-grade AI Coding and Reasoning Assistant powered by the Omni Agentic Platform.\n"
      "Generate clean, detailed, and highly accurate responses.\n"
      "Always format code snippets using markdown code blocks with the correct language identifier.\n"
  )
  
  # Separate memories and document chunks
  memories = [item for item in retrieved_items if item.get("type") == "memory" or "category" in item]
  doc_chunks = [item for item in retrieved_items if item.get("type") == "chunk"]
  
  if memories:
    system_base += "\n### Long-Term Episodic Memories & User Preferences:\n"
    for mem in memories:
      category = mem.get("category", "fact").upper()
      content = mem.get("content", "")
      system_base += f"- [{category}] {content}\n"
      
  if doc_chunks:
    system_base += "\n### Relevant Document Context (RAG):\n"
    system_base += "Use the following context from the user's uploaded documents to answer their query if relevant:\n"
    for chunk in doc_chunks:
      filename = chunk.get("filename", "Unknown File")
      content = chunk.get("content", "")
      system_base += f"--- START OF CHUNK (File: {filename}) ---\n{content}\n--- END OF CHUNK ---\n"
      
  return system_base
