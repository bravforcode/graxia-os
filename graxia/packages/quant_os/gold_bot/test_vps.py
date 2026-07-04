import sys
sys.path.insert(0, '/opt/goldbot')
from gold_bot.core.engine import GoldBotEngine
from gold_bot.core.config import BotConfig

config = BotConfig()
engine = GoldBotEngine(config)
print(f"Strategies loaded: {len(engine.strategies)}")
for s in engine.strategies:
    print(f"  - {s}")
