import os
import re
from typing import Dict, Any, List, Optional

class CustomizationManager:
    """
    Discovers, parses, and injects dynamic Rules (.agents/AGENTS.md, rules/*.md)
    and Skills (.agents/skills/<name>/SKILL.md) into the M5 v2 engine.
    """
    def __init__(self, workspace_root: str = "."):
        self.workspace_root = os.path.abspath(workspace_root)
        self.agents_dir = os.path.join(self.workspace_root, ".agents")
        self.rules_dir = os.path.join(self.agents_dir, "rules")
        self.skills_dir = os.path.join(self.agents_dir, "skills")

    def load_rules(self) -> str:
        """
        Loads all markdown rules from .agents/AGENTS.md and .agents/rules/*.md.
        Returns a compiled rules string formatted for prompt injection.
        """
        rules_text = []

        # 1. Check main AGENTS.md (in .agents/ or workspace root)
        main_agents_md = os.path.join(self.agents_dir, "AGENTS.md")
        if not os.path.exists(main_agents_md):
            main_agents_md = os.path.join(self.workspace_root, "AGENTS.md")
        if os.path.exists(main_agents_md):
            try:
                with open(main_agents_md, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read().strip()
                rules_text.append(f"<user_rules source='.agents/AGENTS.md'>\n{content}\n</user_rules>")
            except Exception as e:
                print(f"[!] Warning reading AGENTS.md: {e}")

        # 2. Check rules/ directory
        if os.path.exists(self.rules_dir):
            for fname in sorted(os.listdir(self.rules_dir)):
                if fname.endswith(".md"):
                    fpath = os.path.join(self.rules_dir, fname)
                    try:
                        with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                            content = f.read().strip()
                        rules_text.append(f"<user_rules source='.agents/rules/{fname}'>\n{content}\n</user_rules>")
                    except Exception as e:
                        print(f"[!] Warning reading {fname}: {e}")

        if not rules_text:
            return ""

        return "\n\n".join(rules_text)

    def list_skills(self) -> List[Dict[str, Any]]:
        """
        Discovers all available skills in .agents/skills/ and parses their YAML frontmatter.
        """
        skills = []
        if not os.path.exists(self.skills_dir):
            return skills

        for item in sorted(os.listdir(self.skills_dir)):
            skill_folder = os.path.join(self.skills_dir, item)
            if os.path.isdir(skill_folder):
                skill_md = os.path.join(skill_folder, "SKILL.md")
                if os.path.exists(skill_md):
                    metadata = self._parse_skill_metadata(skill_md, default_name=item)
                    skills.append(metadata)

        return skills

    def load_skill(self, skill_name: str) -> Dict[str, Any]:
        """
        Loads full skill instructions and metadata for a specific skill.
        """
        skill_folder = os.path.join(self.skills_dir, skill_name)
        skill_md = os.path.join(skill_folder, "SKILL.md")
        
        if not os.path.exists(skill_md):
            return {
                "status": "ERROR",
                "error": f"Skill '{skill_name}' not found at {skill_md}",
                "name": skill_name,
                "instructions": ""
            }

        metadata = self._parse_skill_metadata(skill_md, default_name=skill_name)
        try:
            with open(skill_md, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
            # Strip YAML frontmatter from raw instructions if present
            body = re.sub(r"^---\n.*?\n---\n", "", content, flags=re.DOTALL).strip()
            metadata["instructions"] = body
            metadata["status"] = "SUCCESS"
            return metadata
        except Exception as e:
            return {
                "status": "ERROR",
                "error": f"Failed reading skill {skill_name}: {str(e)}",
                "name": skill_name,
                "instructions": ""
            }

    def _parse_skill_metadata(self, file_path: str, default_name: str) -> Dict[str, Any]:
        """
        Parses YAML frontmatter (name, description) from SKILL.md.
        """
        name = default_name
        description = "No description provided."
        
        try:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()

            fm_match = re.match(r"^---\n(.*?)\n---", content, re.DOTALL)
            if fm_match:
                fm_text = fm_match.group(1)
                name_match = re.search(r"^name:\s*(.+)$", fm_text, re.MULTILINE)
                desc_match = re.search(r"^description:\s*(.+)$", fm_text, re.MULTILINE)
                if name_match:
                    name = name_match.group(1).strip()
                if desc_match:
                    description = desc_match.group(1).strip()
        except Exception:
            pass

        return {
            "name": name,
            "description": description,
            "path": os.path.abspath(file_path)
        }

customization_manager = CustomizationManager()
