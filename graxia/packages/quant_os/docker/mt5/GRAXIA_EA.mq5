//+------------------------------------------------------------------+
//| GRAXIA EA — XAUUSD Paper Trading via Signal Service              |
//| Sends OHLCV bars to POST /api/signal, gets prediction            |
//| Executes trades with B2 stop ($3.00) at 0.01 lot                |
//| Only trades European session (08:00-17:00 UTC)                   |
//+------------------------------------------------------------------+
#property copyright "GRAXIA-OS"
#property version   "1.00"
#property strict

//--- Input parameters
input string   SignalServiceUrl = "http://localhost:8752";
input int      BarsToSend       = 200;
input int      PollIntervalSec  = 60;
input double   LotSize          = 0.01;
input double   B2StopDollars    = 3.00;
input double   MinConfidence    = 0.50;
input int      MagicNumber      = 123456;
input int      MaxSlippage      = 10;
input string   TradeComment     = "GRAXIA EA";

//--- Global variables
datetime lastPollTime = 0;
string   eaStatus = "INIT";
int      totalTrades = 0;
double   dailyPnL = 0.0;
datetime lastDay = 0;

//+------------------------------------------------------------------+
//| JSON value extractor                                              |
//+------------------------------------------------------------------+
string JsonGetString(string json, string key)
{
   string search = "\"" + key + "\":";
   int pos = StringFind(json, search);
   if(pos == -1) return "";

   pos += StringLen(search);
   while(pos < StringLen(json))
   {
      ushort ch = StringGetCharacter(json, pos);
      if(ch != ' ' && ch != '\t') break;
      pos++;
   }

   if(StringGetCharacter(json, pos) == '"')
   {
      pos++;
      int end = StringFind(json, "\"", pos);
      if(end == -1) return "";
      return StringSubstr(json, pos, end - pos);
   }

   int start = pos;
   while(pos < StringLen(json))
   {
      ushort ch = StringGetCharacter(json, pos);
      if(ch == ',' || ch == '}' || ch == ']' || ch == ' ') break;
      pos++;
   }
   return StringSubstr(json, start, pos - start);
}

double JsonGetDouble(string json, string key)
{
   string val = JsonGetString(json, key);
   if(val == "" || val == "null") return 0.0;
   return StringToDouble(val);
}

//+------------------------------------------------------------------+
//| HTTP POST with body                                               |
//+------------------------------------------------------------------+
string HttpPost(string url, string body)
{
   string headers = "Content-Type: application/json\r\n";
   char   postData[];
   char   result[];
   string resultHeaders;

   StringToCharArray(body, postData, 0, WHOLE_ARRAY, CP_UTF8);
   ArrayResize(postData, ArraySize(postData) - 1);

   int res = WebRequest("POST", url, headers, 5000, postData, result, resultHeaders);
   if(res == -1)
   {
      Print("WebRequest POST failed: ", GetLastError(), " URL: ", url);
      return "";
   }
   if(res != 200)
   {
      Print("WebRequest POST returned: ", res);
      return "";
   }
   return CharArrayToString(result, 0, WHOLE_ARRAY, CP_UTF8);
}

//+------------------------------------------------------------------+
//| HTTP GET                                                          |
//+------------------------------------------------------------------+
string HttpGet(string url)
{
   string headers = "Content-Type: application/json\r\n";
   char   result[];
   string resultHeaders;

   int res = WebRequest("GET", url, headers, 5000, result, resultHeaders);
   if(res == -1 || res != 200) return "";
   return CharArrayToString(result, 0, WHOLE_ARRAY, CP_UTF8);
}

//+------------------------------------------------------------------+
//| Build JSON array of last N M15 bars                               |
//+------------------------------------------------------------------+
string BuildBarsJson()
{
   string json = "[";
   MqlRates rates[];

   int copied = CopyRates(_Symbol, PERIOD_M15, 0, BarsToSend, rates);
   if(copied < BarsToSend)
   {
      Print("CopyRates failed: copied=", copied);
      return "[]";
   }

   for(int i = 0; i < copied; i++)
   {
      if(i > 0) json += ",";
      json += StringFormat(
         "{\"time\":%I64d,\"open\":%.5f,\"high\":%.5f,\"low\":%.5f,\"close\":%.5f,\"volume\":%.0f}",
         rates[i].time,
         rates[i].open,
         rates[i].high,
         rates[i].low,
         rates[i].close,
         rates[i].tick_volume
      );
   }
   json += "]";
   return json;
}

//+------------------------------------------------------------------+
//| Check if position exists with this magic number                   |
//+------------------------------------------------------------------+
bool HasOpenPosition()
{
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong ticket = PositionGetTicket(i);
      if(ticket > 0 &&
         PositionGetInteger(POSITION_MAGIC) == MagicNumber &&
         PositionGetString(POSITION_SYMBOL) == _Symbol)
         return true;
   }
   return false;
}

//+------------------------------------------------------------------+
//| Get current position info                                         |
//+------------------------------------------------------------------+
bool GetCurrentPosition(string &direction, double &openPrice, double &sl, double &tp, double &profit)
{
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong ticket = PositionGetTicket(i);
      if(ticket > 0 &&
         PositionGetInteger(POSITION_MAGIC) == MagicNumber &&
         PositionGetString(POSITION_SYMBOL) == _Symbol)
      {
         direction = (PositionGetInteger(POSITION_TYPE) == POSITION_TYPE_BUY) ? "long" : "short";
         openPrice = PositionGetDouble(POSITION_PRICE_OPEN);
         sl = PositionGetDouble(POSITION_SL);
         tp = PositionGetDouble(POSITION_TP);
         profit = PositionGetDouble(POSITION_PROFIT);
         return true;
      }
   }
   return false;
}

//+------------------------------------------------------------------+
//| Place market order                                                |
//+------------------------------------------------------------------+
bool PlaceOrder(string direction, double sl_distance, double confidence)
{
   MqlTradeRequest request = {};
   MqlTradeResult  result = {};

   request.action    = TRADE_ACTION_DEAL;
   request.symbol    = _Symbol;
   request.volume    = LotSize;
   request.deviation = MaxSlippage;
   request.magic     = MagicNumber;

   double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
   double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);

   if(direction == "long")
   {
      request.type  = ORDER_TYPE_BUY;
      request.price = ask;
      request.sl    = NormalizeDouble(ask - sl_distance, _Digits);
      request.comment = StringFormat("%s LONG conf=%.3f", TradeComment, confidence);
   }
   else if(direction == "short")
   {
      request.type  = ORDER_TYPE_SELL;
      request.price = bid;
      request.sl    = NormalizeDouble(bid + sl_distance, _Digits);
      request.comment = StringFormat("%s SHORT conf=%.3f", TradeComment, confidence);
   }
   else
      return false;

   if(!OrderSend(request, result))
   {
      Print("Order failed: ", result.retcode, " - ", result.comment);
      return false;
   }

   totalTrades++;
   Print("ORDER PLACED: ", direction, " @ ", request.price, " SL=", request.sl, " conf=", confidence);

   // Log to signal service
   string logBody = StringFormat(
      "{\"ticket\":%I64d,\"direction\":\"%s\",\"entry_price\":%.5f,\"sl\":%.5f,\"tp\":0.0,\"confidence\":%.4f,\"lot_size\":%.2f}",
      result.order, direction, request.price, request.sl, confidence, LotSize
   );
   HttpPost(SignalServiceUrl + "/api/trade", logBody);

   return true;
}

//+------------------------------------------------------------------+
//| Expert initialization function                                    |
//+------------------------------------------------------------------+
int OnInit()
{
   Print("GRAXIA EA initializing...");
   Print("Signal Service: ", SignalServiceUrl);
   Print("Symbol: ", _Symbol, " Lot: ", LotSize, " Stop: $", B2StopDollars);

   // Test signal service connection
   string health = HttpGet(SignalServiceUrl + "/api/health");
   if(health != "")
   {
      Print("Signal service connected");
      eaStatus = "ONLINE";
   }
   else
   {
      Print("WARNING: Cannot reach signal service");
      eaStatus = "NO_SERVICE";
   }

   lastPollTime = 0;
   lastDay = StringToTime(TimeToString(TimeCurrent(), TIME_DATE));

   EventSetTimer(PollIntervalSec);
   Print("GRAXIA EA started — polling every ", PollIntervalSec, "s");

   return INIT_SUCCEEDED;
}

//+------------------------------------------------------------------+
//| Expert deinitialization function                                  |
//+------------------------------------------------------------------+
void OnDeinit(const int reason)
{
   EventKillTimer();
   Print("GRAXIA EA stopped. Total trades: ", totalTrades);
}

//+------------------------------------------------------------------+
//| Timer function — main polling loop                                |
//+------------------------------------------------------------------+
void OnTimer()
{
   datetime now = TimeCurrent();
   MqlDateTime dt;
   TimeToStruct(now, dt);

   // Reset daily PnL at midnight
   datetime today = StringToTime(TimeToString(now, TIME_DATE));
   if(today != lastDay)
   {
      if(totalTrades > 0)
         Print("Day reset: trades=", totalTrades, " PnL=", dailyPnL);
      totalTrades = 0;
      dailyPnL = 0.0;
      lastDay = today;
   }

   // Session filter: only trade 08:00-17:00 UTC
   int hour = dt.hour;
   if(hour < 8 || hour >= 17)
   {
      eaStatus = StringFormat("IDLE (hour=%d)", hour);
      return;
   }

   // Check if we already have a position
   if(HasOpenPosition())
   {
      string posDir;
      double posPrice, posSL, posTP, posProfit;
      GetCurrentPosition(posDir, posPrice, posSL, posTP, posProfit);
      eaStatus = StringFormat("HOLDING %s PnL=$%.2f", posDir, posProfit);
      return;
   }

   // Build bars JSON and send to signal service
   string barsJson = BuildBarsJson();
   if(barsJson == "[]")
   {
      eaStatus = "NO_BARS";
      return;
   }

   double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
   double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);

   string requestBody = StringFormat(
      "{\"bars\":%s,\"bid\":%.5f,\"ask\":%.5f,\"hour_utc\":%d}",
      barsJson, bid, ask, hour
   );

   string response = HttpPost(SignalServiceUrl + "/api/signal", requestBody);
   if(response == "")
   {
      eaStatus = "NO_RESPONSE";
      return;
   }

   // Parse response
   string direction = JsonGetString(response, "direction");
   double confidence = JsonGetDouble(response, "confidence");
   double sl_distance = JsonGetDouble(response, "sl_distance");

   eaStatus = StringFormat("SIGNAL: %s conf=%.3f", direction, confidence);

   // Check signal
   if(direction == "flat" || direction == "")
   {
      eaStatus += " | NO_TRADE";
      return;
   }

   if(confidence < MinConfidence)
   {
      eaStatus += StringFormat(" | LOW_CONF (%.3f < %.3f)", confidence, MinConfidence);
      return;
   }

   // Place order
   Print("SIGNAL: ", direction, " conf=", confidence, " sl_dist=", sl_distance);
   bool placed = PlaceOrder(direction, sl_distance, confidence);
   if(placed)
      eaStatus += " | ORDER_PLACED";
   else
      eaStatus += " | ORDER_FAILED";
}

//+------------------------------------------------------------------+
//| Tick function — update chart comment                              |
//+------------------------------------------------------------------+
void OnTick()
{
   string posInfo = "";
   string posDir;
   double posPrice, posSL, posTP, posProfit;
   if(GetCurrentPosition(posDir, posPrice, posSL, posTP, posProfit))
      posInfo = StringFormat("\nPosition: %s @ %.2f SL=%.2f PnL=$%.2f", posDir, posPrice, posSL, posProfit);

   Comment(
      "=== GRAXIA EA ===\n",
      "Status: ", eaStatus, "\n",
      "Trades Today: ", totalTrades, "\n",
      "Bid: ", DoubleToString(SymbolInfoDouble(_Symbol, SYMBOL_BID), _Digits), "\n",
      "Ask: ", DoubleToString(SymbolInfoDouble(_Symbol, SYMBOL_ASK), _Digits),
      posInfo
   );
}
//+------------------------------------------------------------------+
