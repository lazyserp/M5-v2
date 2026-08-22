import os
import re
import json
from typing import Optional
from google import genai

from src.config import GEMINI_API_KEY
from src.agents.prompts import SYSTEM_PROMPT
from src.tools.line_reader import read_file_lines
from src.tools.dependency_graph import PersistentDependencyGraph
from src.tools.vector_search import VectorStore
from src.tools.hybrid_search import HybridRetriever

# Default Global Singletons
retriever = HybridRetriever(org_id="default_org", dept_id="default_dept", repo_id="default_repo")
vector_store = retriever.vector_store
dep_graph = PersistentDependencyGraph(org_id="default_org", dept_id="default_dept", repo_id="default_repo")

def get_tenant_tools(
    org_id: str = "default_org",
    dept_id: str = "default_dept",
    repo_id: str = "default_repo"
):
    """
    Returns tenant-isolated tools mapped strictly to the target org/dept/repo.
    """
    h_retriever = HybridRetriever(org_id=org_id, dept_id=dept_id, repo_id=repo_id)
    d_graph = PersistentDependencyGraph(org_id=org_id, dept_id=dept_id, repo_id=repo_id)
    
    registry = {
        "read_file_lines": read_file_lines,
        "search_code": h_retriever.search_code,
        "get_dependencies": d_graph.get_dependencies,
        "get_dependents": d_graph.get_dependents,
        "find_symbol_references": d_graph.find_symbol_references,
    }
    return registry, h_retriever, d_graph

TOOL_REGISTRY = {
    "read_file_lines": read_file_lines,
    "search_code": retriever.search_code,
    "get_dependencies": dep_graph.get_dependencies,
    "get_dependents": dep_graph.get_dependents,
    "find_symbol_references": dep_graph.find_symbol_references,
}

from src.llm.factory import get_llm_provider

llm_provider = get_llm_provider()

def parse_action(text: str):
    """
    Parses 'Action: <tool_name>' and 'Action Input: <json_str>' from model response.
    """
    action_match = re.search(r"Action:\s*(\w+)", text)
    input_match = re.search(r"Action Input:\s*(\{.*?\})", text, re.DOTALL)

    if action_match and input_match:
        tool_name = action_match.group(1).strip()
        try:
            tool_args = json.loads(input_match.group(1).strip())
            return tool_name, tool_args
        except json.JSONDecodeError:
            return None, None
    return None, None

def run_agent_loop(
    query: str,
    max_turns: int = 5,
    org_id: str = "default_org",
    dept_id: str = "default_dept",
    repo_id: str = "default_repo"
) -> str:
    """
    Runs the ReAct reasoning loop scoped to the specified tenant/department/repository.
    """
    tool_registry, _, _ = get_tenant_tools(org_id=org_id, dept_id=dept_id, repo_id=repo_id)
    
    tenant_context = f"[Session Scope: Organization='{org_id}' | Department='{dept_id}' | Repository='{repo_id}']\n"
    context = f"{SYSTEM_PROMPT}\n\n{tenant_context}\nUser Question: {query}"
    tools_executed = 0

    for turn in range(max_turns):
        print(f"\n--- [Turn {turn + 1}] Calling LLM [{dept_id}/{repo_id}] ---")
        
        try:
            response_text = llm_provider.generate_content(context)
        except Exception as e:
            return f"[ERROR] LLM Provider Generation Failed: {str(e)}"

        print(f"LLM Response:\n{response_text}\n")

        # 1. Check if LLM requested a tool execution
        tool_name, tool_args = parse_action(response_text)

        if tool_name in tool_registry and isinstance(tool_args, dict):
            print(f"--> Executing Tool: '{tool_name}' with args {tool_args}")
            observation = tool_registry[tool_name](**tool_args)
            tools_executed += 1

            context += f"\n{response_text}\nObservation:\n{observation}\n"
            continue

        # 2. Check for Final Answer
        final_match = re.search(r"Final Answer:\s*(.*)", response_text, re.DOTALL)
        if final_match:
            # Guard: Reject hallucinated answers if 0 tools were executed
            if tools_executed == 0:
                context += f"\n{response_text}\nObservation: [GUARD REJECTION] You must first invoke 'search_code' or 'read_file_lines' to ground your response in the actual codebase before delivering a Final Answer.\n"
                continue
            return final_match.group(1).strip()

        # 3. Handle unformatted responses
        context += f"\n{response_text}\nObservation: Invalid format. Please use 'Action: <tool_name>' and 'Action Input: <json>' or 'Final Answer: <text>'.\n"

    return "[ERROR] Maximum Loop Retries reached without finding a Final Answer."