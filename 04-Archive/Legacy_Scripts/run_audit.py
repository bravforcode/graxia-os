import argparse
import asyncio
import sys
import os
import logging

# Configure logging to see progress
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("run_audit")

# Ensure the root directory is in sys.path so we can import 'core'
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from core.execution.auditor_agent import PythonAuditor

async def main():
    parser = argparse.ArgumentParser(description="Graxia OS Python Auditor CLI")
    parser.add_argument("--path", type=str, required=True, help="Path to the Python file or directory to audit")
    parser.add_argument("--output", type=str, default="audit_report.md", help="Output file path (default: audit_report.md)")
    
    args = parser.parse_args()
    
    target_path = os.path.abspath(args.path)
    if not os.path.exists(target_path):
        logger.error(f"Path {target_path} does not exist.")
        sys.exit(1)
        
    logger.info(f"🚀 Starting audit for: {target_path}")
    auditor = PythonAuditor(target_path)
    
    try:
        report = await auditor.run_audit()
        output_path = os.path.abspath(args.output)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(report)
        logger.info(f"✅ Audit complete! Report saved to {output_path}")
    except Exception as e:
        logger.error(f"❌ Audit failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())
