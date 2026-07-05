import MetaTrader5 as mt5

PATH = r'C:\Program Files\Pepperstone MetaTrader 5\terminal64.exe'
mt5.initialize(PATH)

symbols = ['AUDUSD', 'EURUSD', 'GBPUSD', 'XAUUSD', 'XAGUSD', 'NAS100', 'US30']
for sym in symbols:
    info = mt5.symbol_info(sym)
    if info:
        mt5.symbol_select(sym, True)
        rates = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_M1, 0, 1000)
        if rates is not None and len(rates) > 0:
            print(sym + ': ' + str(len(rates)) + ' bars')
        else:
            print(sym + ': NO DATA - ' + str(mt5.last_error()))
    else:
        print(sym + ': NOT FOUND')

mt5.shutdown()
