"""
app/resume/skill_categorizer.py — Automatic skill classification into 9 standard technical categories.

Mandated Categories:
  1. Languages
  2. Frontend
  3. Backend
  4. Databases
  5. DevOps
  6. AI/ML / GenAI
  7. Developer Tools
  8. Core CS
  9. Others
"""

from __future__ import annotations
import re
from typing import List, Dict, Union, Set
from app.resume.models import SkillGroup

# Taxonomy dictionary for rule-based skill categorization
SKILL_TAXONOMY: Dict[str, Set[str]] = {
    "Languages": {
        "python", "javascript", "typescript", "java", "c++", "c#", "c", "go", "golang",
        "rust", "ruby", "php", "swift", "kotlin", "scala", "r", "sql", "html", "css",
        "html5", "css3", "bash", "shell", "powershell", "perl", "haskell", "lua", "dart",
        "assembly", "vba", "matlab", "groovy", "elixir", "clojure", "f#"
    },
    "Frontend": {
        "react", "react.js", "reactjs", "next.js", "nextjs", "vue", "vue.js", "vuejs",
        "angular", "angularjs", "svelte", "sveltekit", "redux", "redux toolkit", "mobx",
        "zustand", "tailwind", "tailwind css", "tailwindcss", "bootstrap", "sass", "scss", "less",
        "material ui", "mui", "shadcn", "shadcn/ui", "chakra ui", "webpack", "vite",
        "babel", "gulp", "npm", "yarn", "pnpm", "webassembly", "wasm", "three.js",
        "d3.js", "chart.js", "responsive design", "flexbox", "css grid"
    },
    "Backend": {
        "node.js", "nodejs", "express", "express.js", "fastapi", "django", "flask",
        "spring", "spring boot", "ruby on rails", "rails", "laravel", "asp.net", ".net",
        "graphql", "rest api", "rest apis", "restful apis", "microservices", "grpc", "celery",
        "kafka", "rabbitmq", "activemq", "zeromq", "socket.io", "websockets",
        "nest.js", "nestjs", "gin", "echo", "actix", "axum", "phoenix"
    },
    "Databases": {
        "postgresql", "postgres", "mongodb", "mongo", "mysql", "redis", "sqlite",
        "sqlite3", "dynamodb", "cassandra", "elasticsearch", "opensearch", "pinecone",
        "qdrant", "chroma", "chromadb", "neo4j", "arangodb", "couchdb", "mariadb",
        "oracle", "sql server", "mssql", "cockroachdb", "faiss", "milvus", "vector db"
    },
    "DevOps": {
        "docker", "docker containerization", "kubernetes", "k8s", "aws", "amazon web services", "gcp",
        "google cloud", "google cloud platform", "azure", "ci/cd", "github actions",
        "gitlab ci", "jenkins", "terraform", "ansible", "helm", "nginx", "apache",
        "caddy", "prometheus", "grafana", "datadog", "new relic", "serverless",
        "lambda", "cloudformation", "pulumi", "linux", "ubuntu", "debian", "centos"
    },
    "AI/ML / GenAI": {
        "pytorch", "tensorflow", "keras", "scikit-learn", "sklearn", "opencv",
        "llm", "llms", "large language models", "genai", "genai & agents", "generative ai", "langgraph", "langchain",
        "llamaindex", "rag", "retrieval augmented generation", "hugging face",
        "huggingface", "transformers", "deep learning", "machine learning", "nlp",
        "natural language processing", "computer vision", "fine-tuning", "lora",
        "qlora", "ollama", "vllm", "tgi", "bert", "gpt", "whisper", "stable diffusion",
        "prompt engineering", "agentic ai", "semantic search", "embeddings"
    },
    "Developer Tools": {
        "git", "github", "gitlab", "bitbucket", "vs code", "vscode", "postman",
        "insomnia", "jira", "confluence", "trello", "docker desktop", "pytest",
        "jest", "cypress", "playwright", "selenium", "make", "makefile", "sentry",
        "gdb", "valgrind", "dbeaver", "pgadmin"
    },
    "Core CS": {
        "data structures", "data structures & algorithms", "algorithms", "system design", "object-oriented programming",
        "oop", "design patterns", "operating systems", "computer networks",
        "multithreading", "concurrency", "distributed systems", "database internals",
        "compilers", "agile", "scrum", "sdlc", "test-driven development", "tdd"
    }
}

VALID_CATEGORIES = [
    "Languages", "Frontend", "Backend", "Databases", "DevOps",
    "AI/ML / GenAI", "Developer Tools", "Core CS", "Others"
]


def classify_single_skill(skill_name: str) -> str:
    """Classify a single skill string into one of the 9 categories."""
    if not skill_name:
        return "Others"
    
    clean_skill = skill_name.strip().lower()
    clean_skill = re.sub(r"^[\s•·\-\~–—:,;.]+|[\s•·\-\~–—:,;.]+$", "", clean_skill)
    
    # 1. Exact match against taxonomy
    for cat, skills_set in SKILL_TAXONOMY.items():
        if clean_skill in skills_set:
            return cat
    
    # 2. Word boundary or sub-phrase matching
    for cat, skills_set in SKILL_TAXONOMY.items():
        for item in skills_set:
            if len(item) >= 2:
                # Match word boundary
                if re.search(r"\b" + re.escape(item) + r"\b", clean_skill):
                    return cat
                
    return "Others"


def categorize_skills(raw_skills: List[Union[SkillGroup, dict, str]]) -> List[SkillGroup]:
    """
    Categorize a list of raw skills or existing SkillGroup objects into the 9 canonical categories.
    Handles category-prefixed lines (e.g. 'Languages: C, C++', 'Frontend: React') cleanly.
    Guarantees no duplicate skills, splits comma/bullet lists, strips punctuation artifacts,
    and places every skill into a proper group.
    """
    category_map: Dict[str, List[str]] = {cat: [] for cat in VALID_CATEGORIES}
    seen_skills: Set[str] = set()

    def add_skill(sk: str, suggested_cat: str = ""):
        if not sk:
            return
        
        sk_clean = sk.strip()
        # Clean leading/trailing punctuation artifacts (. , - ~ : ; etc.)
        sk_clean = re.sub(r"^[\s•·\-\~–—:,;.]+|[\s•·\-\~–—:,;.]+$", "", sk_clean)
        
        if not sk_clean or sk_clean in (".", "-", "~", ":", ";", ",", "by", "updates"):
            return
        
        # Check if skill string contains a header prefix like "Languages: C, C++" or "Frontend: React.js"
        colon_match = re.match(r"^([A-Za-z0-9\s/&]+)[:\s]+(.+)$", sk_clean)
        if colon_match:
            hdr_cat = colon_match.group(1).strip()
            sk_rest = colon_match.group(2).strip()
            for sub_sk in re.split(r"[,|•·;\n–—]", sk_rest):
                add_skill(sub_sk, suggested_cat=hdr_cat)
            return

        # Always split comma/bullet-separated lists of skills
        if any(sep in sk_clean for sep in [",", "|", ";", "\n", "•", "·"]) and not colon_match:
            tokens = re.split(r"[,|;\n•·]", sk_clean)
            if len(tokens) > 1:
                for token in tokens:
                    add_skill(token, suggested_cat=suggested_cat)
                return

        # If a string is a descriptive phrase or bullet fragment (e.g. > 2 words) containing a taxonomy skill
        lower_sk = sk_clean.lower()
        exact_match = None
        for cat_k, skills_set in SKILL_TAXONOMY.items():
            for item in skills_set:
                if len(item) >= 2 and re.search(r"\b" + re.escape(item) + r"\b", lower_sk):
                    exact_match = (cat_k, item)
                    break
            if exact_match:
                break

        if exact_match and len(sk_clean.split()) > 2:
            # Replace wordy phrase like "multi-provider LLM selection" with clean skill name "LLMs" or "LLM"
            cat, matched_term = exact_match
            canonical_skill = matched_term.upper() if len(matched_term) <= 4 else matched_term.title()
            add_skill(canonical_skill, suggested_cat=cat)
            return

        if len(sk_clean.split()) > 4 or len(sk_clean) > 35:
            # Sentence/bullet text without matched taxonomy skill; drop
            return

        if lower_sk in seen_skills or len(lower_sk) < 1:
            return

        # Determine best category
        cat = classify_single_skill(sk_clean)
        if cat == "Others" and suggested_cat:
            s_lower = suggested_cat.lower()
            if "lang" in s_lower:
                cat = "Languages"
            elif "front" in s_lower or "web" in s_lower:
                cat = "Frontend"
            elif "back" in s_lower or "api" in s_lower or "server" in s_lower:
                cat = "Backend"
            elif "data" in s_lower or "db" in s_lower:
                cat = "Databases"
            elif "cloud" in s_lower or "devops" in s_lower or "infra" in s_lower:
                cat = "DevOps"
            elif "ai" in s_lower or "ml" in s_lower or "gen" in s_lower or "agent" in s_lower:
                cat = "AI/ML / GenAI"
            elif "tool" in s_lower or "ide" in s_lower:
                cat = "Developer Tools"
            elif "cs" in s_lower or "concept" in s_lower or "core" in s_lower:
                cat = "Core CS"

        seen_skills.add(lower_sk)
        category_map[cat].append(sk_clean)

    # Process raw skills input
    for item in raw_skills:
        if isinstance(item, SkillGroup):
            for sk in item.skills:
                add_skill(sk, item.category)
        elif isinstance(item, dict):
            cat = item.get("category", "")
            skills = item.get("skills", [])
            for sk in skills:
                add_skill(str(sk), cat)
        elif isinstance(item, str):
            lines = item.splitlines()
            for line in lines:
                add_skill(line)

    # Convert back to List[SkillGroup], keeping only non-empty categories
    result: List[SkillGroup] = []
    for cat in VALID_CATEGORIES:
        if category_map[cat]:
            result.append(SkillGroup(category=cat, skills=category_map[cat]))

    return result

