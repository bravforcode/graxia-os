"""
Global Data Sources — 50+ RSS Feeds from Every Major Market
============================================================
Covers: US, Europe, Asia, Emerging Markets, Crypto, Commodities, FX, Central Banks
"""

import sys

sys.stdout.reconfigure(encoding="utf-8")

# === US MARKETS ===
US_FEEDS = {
    "cnbc_finance": "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=100003114",
    "cnbc_world": "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=100727362",
    "cnbc_top_news": "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=100003114",
    "yahoo_finance": "https://finance.yahoo.com/news/rssindex",
    "marketwatch": "https://feeds.marketwatch.com/marketwatch/topstories/",
    "wsj_markets": "https://feeds.a.dj.com/rss/RSSMarketsMain.xml",
    "wsj_world": "https://feeds.a.dj.com/rss/RSSWorldNews.xml",
    "bloomberg_markets": "https://feeds.bloomberg.com/markets/news.rss",
    "bloomberg_politics": "https://feeds.bloomberg.com/politics/news.rss",
    "reuters_business": "https://www.reutersagency.com/feed/?taxonomy=best-sectors&post_type=best",
    "investing_com": "https://www.investing.com/rss/news.rss",
    "seeking_alpha": "https://seekingalpha.com/market_currents.xml",
    "fool_market": "https://www.fool.com/rss/market-news/",
}

# === EUROPE ===
EUROPE_FEEDS = {
    "ft_markets": "https://www.ft.com/markets?format=rss",
    "ft_world": "https://www.ft.com/world?format=rss",
    "ft_companies": "https://www.ft.com/companies?format=rss",
    "guardian_business": "https://www.theguardian.com/business/rss",
    "guardian_world": "https://www.theguardian.com/world/rss",
    "bbc_business": "http://feeds.bbci.co.uk/news/business/rss.xml",
    "bbc_world": "http://feeds.bbci.co.uk/news/world/rss.xml",
    "dw_business": "https://rss.dw.com/rdf/rss-en-bus",
    "euronews_business": "https://www.euronews.com/rss?level=theme&name=business",
}

# === ASIA-PACIFIC ===
ASIA_FEEDS = {
    "nikkei_asia": "https://asia.nikkei.com/rss",
    "scmp_business": "https://www.scmp.com/rss/5/feed",
    "scmp_markets": "https://www.scmp.com/rss/4/feed",
    "channel_newsasia": "https://www.channelnewsasia.com/api/v1/rss-outbound-feed?_format=xml",
    "bangkok_post_business": "https://www.bangkokpost.com/rss/data/business.xml",
    "straits_times": "https://www.straitstimes.com/news/business/rss.xml",
    "korea_herald": "http://www.koreaherald.com/rss/020200000000.xml",
    "global_times": "https://www.globaltimes.cn/rss/outbrain.xml",
    "xinhua": "http://www.news.cn/english/rss/business.xml",
    "economic_times": "https://economictimes.indiatimes.com/rssfeedstopstories.cms",
    "times_india": "https://timesofindia.indiatimes.com/rssfeedstopstories.cms",
}

# === EMERGING MARKETS ===
EMERGING_FEEDS = {
    "brazil_jornal": "https://www.jornalnegocios.com.br/feed/",
    "mexico_eluniversal": "https://www.eluniversal.com.mx/rss.xml",
    "russia_tass": "https://tass.com/rss/v2.xml",
    "saudi_arabnews": "https://www.arabnews.com/cat/1/rss.xml",
    "uae_khaleejtimes": "https://www.khaleejtimes.com/rss",
    "turkey_dailysabah": "https://www.dailysabah.com/rssFeed/market",
    "nigeria_premiumtimes": "https://www.premiumtimesng.com/feed",
    "south_africa_bizlive": "https://www.bizlive.co.za/rss",
}

# === CRYPTO / DEFI ===
CRYPTO_FEEDS = {
    "coindesk": "https://www.coindesk.com/arc/outboundfeeds/rss/",
    "cointelegraph": "https://cointelegraph.com/rss",
    "decrypt": "https://decrypt.co/feed",
    "the_block": "https://www.theblock.co/rss.xml",
    "bitcoin_magazine": "https://bitcoinmagazine.com/feed",
}

# === COMMODITIES ===
COMMODITY_FEEDS = {
    "oilprice": "https://oilprice.com/rss/main",
    "kitco_gold": "https://www.kitco.com/feed/rss/news.xml",
    "agriculture_farm": "https://www.agriculture.com/rss",
    "metals_market": "https://www.metalsmarket.com/feed",
}

# === FX / FIXED INCOME ===
FX_FEEDS = {
    "forexlive": "https://www.forexlive.com/feed",
    "fx_street": "https://www.fxstreet.com/rss/news",
    "dailyfx": "https://www.dailyfx.com/feeds/market-news",
    "bonds_online": "https://www.bondsonline.com/rss.xml",
}

# === CENTRAL BANKS / ECONOMIC DATA ===
CENTRAL_FEEDS = {
    "fed_reserve": "https://www.federalreserve.gov/feeds/press_all.xml",
    "ecb_news": "https://www.ecb.europa.eu/rss/press.html",
    "boj_news": "https://www.boj.or.jp/en/rss/whatsnew.xml",
    "imf_blog": "https://www.imf.org/en/News/Rss",
    "world_bank": "https://blogs.worldbank.org/feed",
    "oecd_news": "https://www.oecd.org/newsroom/index.xml",
    "fed_calendar": "https://www.federalreserve.gov/feeds/meetingdates.xml",
}

# === ECONOMIC CALENDAR ===
ECONOMY_FEEDS = {
    "forex_factory": "https://www.forexfactory.com/rss.php",
    "trading_econ": "https://tradingeconomics.com/feed",
    "investing_calendar": "https://www.investing.com/rss/news_14.rss",
}

# === ALL FEEDS COMBINED ===
ALL_FEEDS = {}
ALL_FEEDS.update(US_FEEDS)
ALL_FEEDS.update(EUROPE_FEEDS)
ALL_FEEDS.update(ASIA_FEEDS)
ALL_FEEDS.update(EMERGING_FEEDS)
ALL_FEEDS.update(CRYPTO_FEEDS)
ALL_FEEDS.update(COMMODITY_FEEDS)
ALL_FEEDS.update(FX_FEEDS)
ALL_FEEDS.update(CENTRAL_FEEDS)
ALL_FEEDS.update(ECONOMY_FEEDS)

# === CATEGORY MAP ===
FEED_CATEGORIES = {}
for name in US_FEEDS:
    FEED_CATEGORIES[name] = "us"
for name in EUROPE_FEEDS:
    FEED_CATEGORIES[name] = "europe"
for name in ASIA_FEEDS:
    FEED_CATEGORIES[name] = "asia"
for name in EMERGING_FEEDS:
    FEED_CATEGORIES[name] = "emerging"
for name in CRYPTO_FEEDS:
    FEED_CATEGORIES[name] = "crypto"
for name in COMMODITY_FEEDS:
    FEED_CATEGORIES[name] = "commodity"
for name in FX_FEEDS:
    FEED_CATEGORIES[name] = "fx"
for name in CENTRAL_FEEDS:
    FEED_CATEGORIES[name] = "central_bank"
for name in ECONOMY_FEEDS:
    FEED_CATEGORIES[name] = "economy"

# === PRIORITY TIERS ===
TIER_1 = [  # High priority — always fetch
    "cnbc_finance",
    "cnbc_world",
    "bloomberg_markets",
    "wsj_markets",
    "ft_markets",
    "bbc_business",
    "reuters_business",
    "coindesk",
    "oilprice",
    "forexlive",
    "fed_reserve",
    "nikkei_asia",
    "scmp_markets",
    "economic_times",
]
TIER_2 = [  # Medium priority — fetch every 2nd cycle
    "yahoo_finance",
    "marketwatch",
    "wsj_world",
    "ft_world",
    "guardian_business",
    "bbc_world",
    "dw_business",
    "scmp_business",
    "channel_newsasia",
    "bangkok_post_business",
    "cointelegraph",
    "kitco_gold",
    "fx_street",
    "ecb_news",
    "imf_blog",
    "trading_econ",
]
TIER_3 = [  # Low priority — fetch every 4th cycle
    "investing_com",
    "seeking_alpha",
    "fool_market",
    "ft_companies",
    "euronews_business",
    "straits_times",
    "korea_herald",
    "global_times",
    "xinhua",
    "times_india",
    "brazil_jornal",
    "mexico_eluniversal",
    "russia_tass",
    "saudi_arabnews",
    "uae_khaleejtimes",
    "turkey_dailysabah",
    "decrypt",
    "the_block",
    "bitcoin_magazine",
    "agriculture_farm",
    "metals_market",
    "dailyfx",
    "bonds_online",
    "boj_news",
    "world_bank",
    "oecd_news",
    "fed_calendar",
    "forex_factory",
    "investing_calendar",
]


def get_feeds(tier: int = 0) -> dict:
    """Get feeds by tier. tier=0 means all."""
    if tier == 0:
        return ALL_FEEDS
    elif tier == 1:
        return {k: v for k, v in ALL_FEEDS.items() if k in TIER_1}
    elif tier == 2:
        return {k: v for k, v in ALL_FEEDS.items() if k in TIER_1 + TIER_2}
    else:
        return {k: v for k, v in ALL_FEEDS.items() if k in TIER_1 + TIER_2 + TIER_3}


def print_summary():
    """Print feed summary."""
    print(f"Total feeds: {len(ALL_FEEDS)}")
    print(f"  US: {len(US_FEEDS)}")
    print(f"  Europe: {len(EUROPE_FEEDS)}")
    print(f"  Asia: {len(ASIA_FEEDS)}")
    print(f"  Emerging: {len(EMERGING_FEEDS)}")
    print(f"  Crypto: {len(CRYPTO_FEEDS)}")
    print(f"  Commodities: {len(COMMODITY_FEEDS)}")
    print(f"  FX: {len(FX_FEEDS)}")
    print(f"  Central Banks: {len(CENTRAL_FEEDS)}")
    print(f"  Economy: {len(ECONOMY_FEEDS)}")
    print(f"\nTier 1 (high): {len(TIER_1)} feeds")
    print(f"Tier 2 (med):  {len(TIER_2)} feeds")
    print(f"Tier 3 (low):  {len(TIER_3)} feeds")


if __name__ == "__main__":
    print_summary()
