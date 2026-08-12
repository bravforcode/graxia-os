"""
PixelRAG Serve Launcher — handles model download with retry and proper logging.

Usage:
    python scripts/start_pixelrag.py [--port 30002] [--model Qwen/Qwen3-VL-Embedding-2B]
    
Environment variables:
    HF_TOKEN — HuggingFace token for faster downloads (recommended)
    HF_HOME  — HuggingFace cache directory
"""
import argparse
import os
import sys
import time
import logging

# Setup logging that won't crash on missing 'req' field
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("data/service_logs/pixelrag_startup.log", mode="w"),
    ],
)
logger = logging.getLogger("pixelrag_launcher")

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INDEX_DIR = os.path.join(PROJECT_ROOT, "data", "visual_index")
TILES_DIR = os.path.join(PROJECT_ROOT, "data", "visual_tiles")
LOG_DIR = os.path.join(PROJECT_ROOT, "data", "service_logs")

os.makedirs(LOG_DIR, exist_ok=True)
os.makedirs(INDEX_DIR, exist_ok=True)
os.makedirs(TILES_DIR, exist_ok=True)


def check_index_ready() -> bool:
    """Check if the FAISS index is ready to serve."""
    required = ["index.faiss", "metadata.npz", "articles.json"]
    for f in required:
        path = os.path.join(INDEX_DIR, f)
        if not os.path.exists(path):
            logger.error("Missing index file: %s", path)
            return False
    return True


def download_model(model_name: str, max_retries: int = 3) -> bool:
    """Download the Qwen model from HuggingFace with retry."""
    logger.info("Checking model: %s", model_name)
    
    for attempt in range(1, max_retries + 1):
        try:
            from huggingface_hub import snapshot_download
            
            logger.info("Download attempt %d/%d...", attempt, max_retries)
            path = snapshot_download(
                model_name,
                resume_download=True,
            )
            logger.info("Model downloaded to: %s", path)
            return True
        except Exception as e:
            logger.warning("Download attempt %d failed: %s", attempt, type(e).__name__)
            if attempt < max_retries:
                wait = 30 * attempt
                logger.info("Retrying in %ds...", wait)
                time.sleep(wait)
    
    return False


def check_model_cached(model_name: str) -> bool:
    """Check if the model is already fully cached."""
    try:
        from huggingface_hub import try_to_load_from_cache
        # Check for model weights
        result = try_to_load_from_cache(model_name, "model.safetensors")
        if result is not None and not isinstance(result, type(None)):
            logger.info("Model weights found in cache")
            return True
    except Exception:
        pass
    return False


def main():
    parser = argparse.ArgumentParser(description="PixelRAG Serve Launcher")
    parser.add_argument("--port", type=int, default=30002, help="Port to serve on")
    parser.add_argument("--host", default="127.0.0.1", help="Host to bind to")
    parser.add_argument("--model", default="Qwen/Qwen3-VL-Embedding-2B", help="HF model name")
    parser.add_argument("--device", default="cpu", choices=["cpu", "cuda"], help="Device")
    parser.add_argument("--skip-download", action="store_true", help="Skip model download")
    parser.add_argument("--no-download", action="store_true", help="Skip model download (alias)")
    args = parser.parse_args()

    logger.info("=" * 60)
    logger.info("PixelRAG Serve Launcher")
    logger.info("=" * 60)
    logger.info("Project root: %s", PROJECT_ROOT)
    logger.info("Index dir: %s", INDEX_DIR)
    logger.info("Tiles dir: %s", TILES_DIR)
    logger.info("Port: %d", args.port)
    logger.info("Model: %s", args.model)
    logger.info("Device: %s", args.device)

    # Step 1: Check index
    if not check_index_ready():
        logger.error("FAISS index not ready. Run bootstrap first.")
        sys.exit(1)
    logger.info("FAISS index: READY")

    # Step 2: Download model (unless skipped)
    skip = args.skip_download or args.no_download
    if not skip:
        if check_model_cached(args.model):
            logger.info("Model already cached, skipping download")
        else:
            logger.info("Model not cached. Starting download...")
            logger.info("TIP: Set HF_TOKEN env var for 5x faster downloads")
            if not download_model(args.model):
                logger.error(
                    "Model download failed. Options:\n"
                    "  1. Set HF_TOKEN: $env:HF_TOKEN='hf_xxx'\n"
                    "  2. Download manually: huggingface-cli download %s\n"
                    "  3. Start with --skip-download (searches won't work without model)",
                    args.model,
                )
                sys.exit(1)
    else:
        logger.info("Skipping model download (--skip-download)")

    # Step 3: Start serve
    logger.info("Starting PixelRAG serve on %s:%d...", args.host, args.port)

    # Patch the logging format to avoid the 'req' KeyError
    import pixelrag_serve.api as api_module
    
    # Override the default logging format that requires 'req' field
    for handler in logging.root.handlers[:]:
        if isinstance(handler, logging.StreamHandler) and not isinstance(handler, logging.FileHandler):
            handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    
    # Set up args for the load function
    class ServeArgs:
        index_dir = INDEX_DIR
        tiles_dir = TILES_DIR
        articles_json = os.path.join(INDEX_DIR, "articles.json")
        model = args.model
        device = args.device
        peft_adapter = None
        host = args.host
        port = args.port
        render_on_demand = False
        kiwix_url = "http://localhost:30900"
        zim_book = None
    
    serve_args = ServeArgs()
    
    try:
        api_module.load(serve_args)
        logger.info("Model and index loaded successfully")
        
        import uvicorn
        uvicorn.run(
            api_module.app,
            host=args.host,
            port=args.port,
            log_level="info",
        )
    except Exception as e:
        logger.error("Failed to start serve: %s", e, exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
