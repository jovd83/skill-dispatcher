#!/usr/bin/env python3
"""Enrich Metadata Heuristics - Scans SKILL.md and README.md to fill blank dispatcher tags.
Uses pattern matching and keyword extraction to infer capabilities, stack, and artifacts.
"""

import os
import re
import argparse
from pathlib import Path

# Common keywords for tech stacks
STACK_KEYWORDS = {
    "python": ["python", "pip install"],
    "javascript": ["javascript", "js", "npm install", "node"],
    "typescript": ["typescript", "ts"],
    "react": ["react", "jsx", "tsx"],
    "angular": ["angular", "@angular"],
    "tailwind": ["tailwind", "tailwindcss"],
    "pdf": ["pypdf", "pdfplumber", "reportlab", "qpdf", "pdf"],
    "excel": ["pandas", "xlsx", "openpyxl", "excel", "csv"],
    "security": ["owasp", "security", "audit", "vulnerability"],
    "testing": ["cypress", "playwright", "jest", "vitest", "mocha", "chai", "junit"],
    "api": ["openapi", "swagger", "rest", "grpc", "protobuf", "json-schema"],
    "mermaid": ["mermaid", "diagram", "graphviz", "mmd"]
}

# Common keywords for capabilities (verbs)
ACTION_KEYWORDS = ["merge", "split", "extract", "audit", "verify", "generate", "create", "analyze", "convert", "transform", "scan", "test"]

def extract_tags(content):
    tags = {
        "capabilities": set(),
        "stack": set(),
        "input": set(),
        "output": set()
    }
    
    # 1. Infer Stack from keywords and code blocks
    content_lower = content.lower()
    for stack, keywords in STACK_KEYWORDS.items():
        if any(kw in content_lower for kw in keywords):
            tags["stack"].add(stack)
            
    # 2. Infer Capabilities from Action Verbs and Section Headings
    # Look for bullet points starting with verbs
    verbs = re.findall(r"(?:-|\*)\s+([a-zA-Z]+)", content)
    for v in verbs:
        v_low = v.lower()
        if v_low in ACTION_KEYWORDS:
            # Try to grab the next word too (e.g., "Extract text")
            match = re.search(rf"(?:-|\*)\s+{v}\s+([a-zA-Z]+)", content)
            if match:
                tags["capabilities"].add(f"{v_low}-{match.group(1).lower()}")
            else:
                tags["capabilities"].add(v_low)
                
    # 3. Infer Artifacts (File extensions)
    exts = re.findall(r"\.([a-zA-Z0-9]{2,4})\b", content)
    for e in exts:
        e_low = e.lower()
        if e_low in ["pdf", "docx", "xlsx", "csv", "json", "yaml", "md", "png", "jpg", "svg", "html", "js", "ts", "py"]:
            tags["input"].add(e_low)
            tags["output"].add(e_low)

    return {k: list(v) for k, v in tags.items()}

def enrich_skill(skill_file, dry_run=True):
    content = skill_file.read_text(encoding="utf-8")
    readme_file = skill_file.parent / "README.md"
    scan_text = content
    if readme_file.exists():
        scan_text += "\n" + readme_file.read_text(encoding="utf-8")
        
    extracted = extract_tags(scan_text)
    
    # We only update if the tags are currently empty
    match = re.search(r"metadata:\s*\n(.*?)\n---\s*\n", content, re.DOTALL)
    if not match:
        return False
        
    frontmatter = match.group(1)
    new_frontmatter = frontmatter
    
    # Mappings from our extracted keys to dispatcher tags
    mappings = {
        "capabilities": "dispatcher-capabilities",
        "stack": "dispatcher-stack-tags",
        "input": "dispatcher-input-artifacts",
        "output": "dispatcher-output-artifacts"
    }
    
    modified = False
    for ext_key, yaml_key in mappings.items():
        # Only enrich if the field is empty (ends with : followed by space and newline/end)
        pattern = rf"  {yaml_key}: \s*(\n|$)"
        if re.search(pattern, new_frontmatter):
            vals = extracted[ext_key]
            if vals:
                csv_vals = ", ".join(vals)
                new_frontmatter = re.sub(pattern, f"  {yaml_key}: {csv_vals}\n", new_frontmatter)
                modified = True
                
    if modified:
        if not dry_run:
            new_content = content.replace(frontmatter, new_frontmatter)
            skill_file.write_text(new_content, encoding="utf-8")
        return True
    return False

def main():
    parser = argparse.ArgumentParser(description="Enrich blank dispatcher tags using source analysis.")
    parser.add_argument("--root", help="Skills root")
    parser.add_argument("--no-dry-run", action="store_true")
    args = parser.parse_args()
    
    root = Path(args.root).resolve() if args.root else Path("C:/Users/jochi/.agents/skills")
    print(f"[*] Scanning skills in {root} for enrichment...")
    
    skill_files = list(root.rglob("SKILL.md"))
    count = 0
    for sf in skill_files:
        if enrich_skill(sf, dry_run=not args.no_dry_run):
            print(f"[+] {sf.parent.name}: Enriched")
            count += 1
            
    print(f"\n[*] Total skills enriched: {count}")

if __name__ == "__main__":
    main()
