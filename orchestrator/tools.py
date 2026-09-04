import json
import traceback
import sys
import os

# Add the RAG folder DIRECTLY to the Python path
# This allows rag.py's internal imports (like `from config import...`) to work normally
root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
rag_dir = os.path.join(root_dir, "RAG")
sys.path.append(rag_dir)

try:
    # Now we can import rag directly because its parent folder is in the path
    from rag import query_rag
except ImportError as e:
    print(f"Warning: Could not import query_rag. Exact error: {e}")
    query_rag = None

def execute_tool(tool_name: str, tool_args: dict) -> str:
    """Dispatcher for all agent tools."""
    
    if tool_name == "search_rag":
        query = tool_args.get("query", "")
        
        if not query:
            return "Error: No query provided to search_rag tool."
            
        if not query_rag:
            return f"[MOCK FALLBACK] RAG results for: {query}"
            
        try:
            # 1. Call your existing RAG function
            result = query_rag(query, top_k=5)
            
            contexts = result.get("context", [])
            
            if not contexts:
                return f"No relevant documents found in the database for query: '{query}'"
                
            # 2. Format the output string for the Agent
            formatted_context = [f"Found {len(contexts)} relevant document excerpts:\n"]
            
            for i, chunk in enumerate(contexts):
                text = chunk.get("text", "")
                source = chunk.get("source", "Unknown Document")
                page = chunk.get("page", "Unknown Page")
                
                formatted_context.append(
                    f"--- Excerpt {i+1} ---\n"
                    f"Source: {source} (Page: {page})\n"
                    f"Content: {text.strip()}\n"
                )
                
            return "\n".join(formatted_context)
            
        except Exception as e:
            return f"Error executing RAG search: {str(e)}\n{traceback.format_exc()}"
            
    elif tool_name == "read_file":
        filepath = tool_args.get("filepath", "")
        # Implement safe directory-restricted file reading here
        return f"[MOCK] Contents of {filepath}"
        
    elif tool_name == "python_sandbox":
        code = tool_args.get("code", "")
        # Implement docker/subprocess execution here
        return f"[MOCK] Execution success. Output: 42"
        
    elif tool_name == "write_docx":
        # Implement python-docx logic
        return f"[MOCK] Successfully saved to {tool_args.get('filename')}"

    elif tool_name == "direct_chat":
        # Just answer the prompt directly without heavy tools
        prompt = tool_args.get("prompt", "")
        
        # We can do a quick blocking HTTP request here to Ollama
        import requests
        try:
            res = requests.post(
                "http://localhost:11434/api/generate",
                json={"model": "llama3.2:1b", "prompt": prompt, "stream": False},
                timeout=30
            )
            return res.json().get("response", "No response generated.")
        except Exception as e:
            return f"Error connecting to Ollama: {str(e)}"
    
    else:
        raise ValueError(f"Unknown tool: {tool_name}")