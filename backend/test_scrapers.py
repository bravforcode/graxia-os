import asyncio
import logging

logging.basicConfig(level=logging.INFO)


async def test_fastwork():
    print("=== TESTING FASTWORK ===")
    from app.scrapers.fastwork import FastworkScraper

    try:
        f = FastworkScraper()
        items = await f.run()
        print(f"Fastwork found: {len(items)} items")
        for i in items[:3]:
            title = i.get("title", "N/A")
            print(f"  - {title[:50]}...")
        return len(items)
    except Exception as e:
        print(f"Fastwork ERROR: {e}")
        import traceback

        traceback.print_exc()
        return 0


async def test_devpost():
    print("\n=== TESTING DEVPOST ===")
    from app.scrapers.devpost import DevpostScraper

    try:
        d = DevpostScraper()
        items = await d.run()
        print(f"Devpost found: {len(items)} items")
        for i in items[:3]:
            title = i.get("title", "N/A")
            print(f"  - {title[:50]}...")
        return len(items)
    except Exception as e:
        print(f"Devpost ERROR: {e}")
        import traceback

        traceback.print_exc()
        return 0


async def test_serpapi():
    print("\n=== TESTING SERPAPI ===")
    from app.scrapers.serpapi_search import SerpAPIScraper

    try:
        s = SerpAPIScraper(query="freelance python developer remote 2025")
        items = await s.run()
        print(f"SerpAPI found: {len(items)} items")
        for i in items[:3]:
            title = i.get("title", "N/A")
            print(f"  - {title[:50]}...")
        return len(items)
    except Exception as e:
        print(f"SerpAPI ERROR: {e}")
        import traceback

        traceback.print_exc()
        return 0


async def main():
    print("\n" + "=" * 50)
    print("SCRAPER TEST - " + "=" * 50)
    print("=" * 50 + "\n")

    total = 0
    total += await test_fastwork()
    total += await test_devpost()
    total += await test_serpapi()

    print(f"\n{'=' * 50}")
    print(f"TOTAL ITEMS FOUND: {total}")
    print(f"{'=' * 50}")


if __name__ == "__main__":
    asyncio.run(main())
