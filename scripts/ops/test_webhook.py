import asyncio
import httpx
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def test_webhook_only():
    webhook_urls = {
        "site_a": "https://httpbin.org/post",
        "site_b": "https://httpbin.org/post"
    }
    
    site = "site_a"
    target_webhook = webhook_urls.get(site)
    
    print(f"Triggering webhook for {site} at {target_webhook}...")
    if target_webhook:
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    target_webhook, 
                    timeout=5.0,
                    json={"event": "rebuild", "site": site}
                )
                logger.info("Webhook triggered for %s: %s", site, resp.status_code)
                print("Response JSON:", resp.json())
        except Exception as e:
            logger.error("Failed to trigger webhook for %s: %s", site, e)

if __name__ == "__main__":
    asyncio.run(test_webhook_only())
