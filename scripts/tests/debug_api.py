import sys
sys.path.insert(0, 'backend')
import asyncio
import httpx
from app.config import settings

async def main():
    url = f"{settings.SKILLSMP_BASE_URL}/skills/search?q=python&limit=2"
    headers = {"Authorization": f"Bearer {settings.SKILLSMP_API_KEY}"}
    
    print(f"URL: {url}")
    async with httpx.AsyncClient() as client:
        resp = await client.get(url, headers=headers)
        print(f"Status: {resp.status_code}")
        data = resp.json()
        print(f"\nKeys: {list(data.keys())}")
        if "data" in data:
            print(f"data keys: {list(data['data'].keys())}")
            if "items" in data["data"]:
                print(f"Items count: {len(data['data']['items'])}")
                if data['data']['items']:
                    print(f"First item keys: {list(data['data']['items'][0].keys())}")

if __name__ == "__main__":
    asyncio.run(main())
