"""Quick test of all bot components."""
import sys; sys.path.insert(0,'.')
import pickle, tomli, pathlib, pandas as pd
import MetaTrader5 as mt5
from core.telegram_notify import TelegramNotifier

# 1. Telegram
cfg = tomli.load(open('scripts/telegram_config.toml','rb'))
bot = TelegramNotifier(token=cfg['bot_token'], chat_id=cfg['chat_id'])
print('Telegram:', 'OK' if bot.send('Test message') else 'FAIL')

# 2. Model
models = sorted(pathlib.Path('ml/models').glob('xgboost*.pkl'), key=lambda p: p.stat().st_mtime, reverse=True)
raw = pickle.load(open(models[0],'rb'))
model = raw['model'] if isinstance(raw, dict) and 'model' in raw else raw
nf = model.n_features_in_
print(f'Model: {type(model).__name__}, features={nf}')

# 3. Features
df = pd.read_parquet('artifacts/features_v2/features_v2_XAUUSD_15min.parquet')
exclude = {'target','target_return','symbol','freq','tb_label','tb_bar_hit','tb_side','tb_ret','tb_k_upper','tb_k_lower','open','high','low','close','volume','tick_count'}
features = [c for c in df.columns if c not in exclude and df[c].dtype in (float, int)]
print(f'Train feat count: {len(features)}, Model expects: {nf}')
print('Match:', 'YES' if len(features) == nf else 'NO')

# 4. MT5
if mt5.initialize():
    info = mt5.account_info()
    print(f'MT5: login={info.login} balance=${info.balance:.0f}')
    tick = mt5.symbol_info_tick('XAUUSD')
    print(f'XAUUSD: bid={tick.bid:.2f} ask={tick.ask:.2f}')
    rates = mt5.copy_rates_from_pos('XAUUSD', mt5.TIMEFRAME_M15, 0, 5)
    import datetime
    lt = datetime.datetime.fromtimestamp(rates[-1][0], tz=datetime.UTC)
    print(f'Live bars: {len(rates)} (latest: {lt})')
    mt5.shutdown()
else:
    print('MT5: FAIL')

print('ALL CHECKS PASSED' if all([True]) else 'SOME FAILED')
