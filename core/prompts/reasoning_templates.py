"""
Prompts and templates for advanced reasoning and intelligence layers.
"""

REASONING_TEMPLATE = """
### TASK ANALYSIS
**RESTATE**: {query_restate}
**CONSTRAINTS**: {constraints}

### STRATEGY
**APPROACH**: {approach_plan}
**RISKS**: {identified_risks}

### EXECUTION
**REASONING**:
<thought>
{chain_of_thought}
</thought>

**ANSWER**:
{final_answer}
""".strip()

# Specialized prompts for compression and structured transformation
COMPRESSION_PROMPT = """
Compress the following context while preserving all key facts, entities, and relationships.
Use a dense key-value format where possible.
Context: {context}
""".strip()
