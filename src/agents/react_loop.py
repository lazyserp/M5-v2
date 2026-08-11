import re
import json
from google import genai
from google.genai._gaos.utils.eventstreaming import MAX_BOUNDARY_LEN

from src.config import GEMINI_API_KEY
from src.agents.prompts import SYSTEM_PROMPT
from src.tools.line_reader import read_file_lines

TOOL_REGISTRY = {
    "read_file_lines" : read_file_lines
}

client = genai.Client(api_key=GEMINI_API_KEY)
MODEL_ID = "gemini-3.6-flash"

def parse_action(text: str):
    """
    Parses 'Action: <tool_name>' and 'Action Input: <json_str>' from Gemini's response.
    """
    action_match = re.search(r"Action:\s*(\w+)", text)
    input_match = re.search(r"Action Input:\s*(\{.*?\})", text, re.DOTALL)

    if action_match and input_match:
         tool_name = action_match.group(1).strip()
         try:
             tool_args = json.loads(input_match.group(1).strip())
             return tool_name, tool_args
         except json.JSONDecodeError:
            return None,None
    return None,None

def run_agent_loop(query: str, max_turns: int = 5) -> str:
    context = f"{SYSTEM_PROMPT}\n\r User Question: {query}"

    for turn in range(max_turns):
        print(f"\n--- [Turn {turn + 1}] Calling LLM ---")
        
        response = client.models.generate_content(
            model=MODEL_ID,
            contents=context
        )

        response_text = response.text.strip()
        print(f"LLM Response:\n{response_text}\n")

        if "Final Answer" in response_text:
            return response_text

        tool_name , tool_args = parse_action(response_text)

        if tool_name in TOOL_REGISTRY and isinstance(tool_args, dict):
            print(f"--> Executing Tool: '{tool_name}' with args {tool_args}")
            observation = TOOL_REGISTRY[tool_name](**tool_args)

            context += f"\n{response_text}\nObservation:\n{observation}\n"
        else:
            context += f"\n{response_text}\nObservation: Invalid tool or format. Please use Action and Action Input JSON.\n"

    return "[ERROR] Maximum Loop Retreis reached without finding a Final Answer."