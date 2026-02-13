#!/usr/bin/env python3
"""
################################################################################
#  EXTRACT CONVERSATION TOOL                                                    #
#  Parses raw trajectory_search output into structured JSON                     #
#                                                                               #
#  USAGE:                                                                       #
#    python extract_conversation.py <input.raw> <output.json>                   #
#    python extract_conversation.py <input.raw>  (writes to same dir as .json)  #
#                                                                               #
#  INPUT:  Raw trajectory_search XML output saved to a .raw file                #
#  OUTPUT: Clean JSON with all steps, diffs, inputs, outputs verbatim           #
#                                                                               #
#  PIPELINE (run by Cascade):                                                   #
#    1. Call trajectory_search(ID=<uuid>, Query="", SearchType="cascade")       #
#    2. Save raw output to: Conversation review/hooks/<title>.raw               #
#    3. Run: python extract_conversation.py <title>.raw                         #
#    4. Output: <title>.json                                                    #
################################################################################
"""
import re
import json
import sys
import os
from datetime import date


def parse_trajectory_raw(raw_text: str) -> dict:
    """Parse the raw trajectory_search XML-like output into structured data."""
    result = {
        "total_chunks": 0,
        "title": "",
        "steps": []
    }

    # Extract total chunks
    m = re.search(r'<CHUNKS_IN_TRAJECTORY>\s*(\d+)\s*</CHUNKS_IN_TRAJECTORY>', raw_text)
    if m:
        result["total_chunks"] = int(m.group(1))

    # Extract title
    m = re.search(r'<TRAJECTORY_DESCRIPTION>\s*(.*?)\s*</TRAJECTORY_DESCRIPTION>', raw_text, re.DOTALL)
    if m:
        result["title"] = m.group(1).strip()

    # Extract all chunks
    chunk_pattern = re.compile(
        r'<CHUNK\s+index="(\d+)"\s+score="([^"]+)">\s*(.*?)\s*</CHUNK>',
        re.DOTALL
    )

    seen_steps = {}  # step_number -> step_data (dedup by step number, keep highest score)

    for match in chunk_pattern.finditer(raw_text):
        chunk_index = int(match.group(1))
        score = float(match.group(2))
        content = match.group(3).strip()

        if not content:
            continue

        # Parse step header: "Step N (CORTEX_STEP_TYPE_XXX):"
        step_match = re.match(r'Step\s+(\d+)\s+\((\w+)\):', content)
        if not step_match:
            continue

        step_num = int(step_match.group(1))
        step_type = step_match.group(2)
        step_body = content[step_match.end():].strip()

        # Parse body into structured fields
        step_data = {
            "step": step_num,
            "type": step_type,
            "score": score,
        }

        # Check for Input/Output pattern
        input_match = re.match(r'Input:\s*(.*?)(?:\nOutput:\s*(.*))?$', step_body, re.DOTALL)
        if input_match:
            inp = input_match.group(1).strip()
            out = input_match.group(2)
            if inp:
                step_data["input"] = inp
            if out:
                step_data["output"] = out.strip()
        # Check for Instruction/Diff pattern
        elif 'Diff:' in step_body or 'Instruction:' in step_body:
            instr_match = re.match(r'Instruction:\s*(.*?)(?:\nDiff:\s*(.*))?$', step_body, re.DOTALL)
            if instr_match:
                instr = instr_match.group(1).strip()
                diff = instr_match.group(2)
                if instr:
                    step_data["instruction"] = instr
                if diff:
                    step_data["diff"] = diff.strip()
            else:
                step_data["content"] = step_body
        # Check for File view pattern
        elif step_body.startswith('File:'):
            step_data["content"] = step_body
        # Check for Error pattern
        elif 'Error:' in step_body:
            step_data["error"] = step_body
        # Plain content
        elif step_body:
            step_data["content"] = step_body
        else:
            step_data["content"] = ""

        # Dedup: keep highest-scoring version of each step
        if step_num not in seen_steps or score > seen_steps[step_num]["score"]:
            seen_steps[step_num] = step_data

    # Sort by step number
    result["steps"] = [seen_steps[k] for k in sorted(seen_steps.keys())]

    return result


def main():
    if len(sys.argv) < 2:
        print("Usage: python extract_conversation.py <input.raw> [output.json]")
        print("       Parses raw trajectory_search output into structured JSON.")
        sys.exit(1)

    input_path = sys.argv[1]
    
    if len(sys.argv) >= 3:
        output_path = sys.argv[2]
    else:
        # Default: same name with .json extension
        output_path = os.path.splitext(input_path)[0] + ".json"

    # Read raw input
    with open(input_path, "r", encoding="utf-8") as f:
        raw_text = f.read()

    # Parse
    parsed = parse_trajectory_raw(raw_text)

    # Build output
    output = {
        "id": "",  # Will be filled if available in filename
        "title": parsed["title"],
        "total_chunks": parsed["total_chunks"],
        "steps_extracted": len(parsed["steps"]),
        "extracted": str(date.today()),
        "method": "trajectory_search -> extract_conversation.py",
        "steps": parsed["steps"]
    }

    # Try to extract UUID from filename
    basename = os.path.basename(input_path)
    uuid_match = re.search(r'([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})', basename)
    if uuid_match:
        output["id"] = uuid_match.group(1)

    # Write output
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"Extracted {len(parsed['steps'])} steps from {parsed['total_chunks']} chunks")
    print(f"Title: {parsed['title']}")
    print(f"Output: {output_path}")


if __name__ == "__main__":
    main()
