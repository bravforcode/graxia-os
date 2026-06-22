//+------------------------------------------------------------------+
//| BE-P8.3.3 — Terminal Time Authority Probe                         |
//| Read-only script that logs MT5 internal timestamps to JSONL.      |
//| No order_send, no trade operations.                               |
//+------------------------------------------------------------------+
#property copyright "QuantOS BE-P8.3.3"
#property version   "1.00"
#property strict
#property script_show_inputs

#include <Trade/Trade.mqh>

input string OutputFile = "terminal_time_probe.jsonl";  // Output filename
input int    SampleCount = 10;                          // Number of samples
input int    SampleDelayMs = 100;                       // Delay between samples (ms)

//+------------------------------------------------------------------+
//| JSON escape helper                                                |
//+------------------------------------------------------------------+
string JsonEscape(string s)
{
   string result = s;
   StringReplace(result, "\\", "\\\\");
   StringReplace(result, "\"", "\\\"");
   StringReplace(result, "\n", "\\n");
   StringReplace(result, "\r", "\\r");
   return result;
}

//+------------------------------------------------------------------+
//| Format datetime as ISO string                                     |
//+------------------------------------------------------------------+
string FormatDateTime(datetime dt)
{
   return TimeToString(dt, TIME_DATE|TIME_SECONDS|TIME_MINUTES);
}

//+------------------------------------------------------------------+
//| Collect one sample                                                |
//+------------------------------------------------------------------+
string CollectSample(int sampleIndex)
{
   // MT5 internal time functions
   datetime timeCurrent    = TimeCurrent();       // Server quote time
   datetime timeTradeServer= TimeTradeServer();   // Terminal-calculated server time
   datetime timeLocal      = TimeLocal();         // Machine local clock
   datetime timeGMT        = TimeGMT();           // UTC from machine clock
   long     gmtOffset      = TimeGMTOffset();     // Offset in seconds

   // Raw epoch values
   long tc_raw   = (long)timeCurrent;
   long tts_raw  = (long)timeTradeServer;
   long tl_raw   = (long)timeLocal;
   long tgmt_raw = (long)timeGMT;

   // Tick data
   MqlTick tick;
   bool tickOk = SymbolInfoTick(_Symbol, tick);
   long tick_time_raw = 0;
   long tick_time_msc = 0;
   double tick_bid = 0;
   double tick_ask = 0;
   if(tickOk)
   {
      tick_time_raw = (long)tick.time;
      tick_time_msc = tick.time_msc;
      tick_bid = tick.bid;
      tick_ask = tick.ask;
   }

   // Current bar time
   datetime barTime = iTime(_Symbol, PERIOD_CURRENT, 0);
   long bar_time_raw = (long)barTime;

   // M1 bar time
   datetime m1Time = iTime(_Symbol, PERIOD_M1, 0);
   long m1_time_raw = (long)m1Time;

   // H1 bar time
   datetime h1Time = iTime(_Symbol, PERIOD_H1, 0);
   long h1_time_raw = (long)h1Time;

   // Server minus GMT offset
   long server_minus_gmt = tc_raw - tgmt_raw;
   long tick_minus_tc = tickOk ? (tick_time_raw - tc_raw) : 0;
   long tick_minus_tc_msc = tickOk ? (tick_time_msc - tc_raw * 1000) : 0;

   // Build JSON line
   string json = "{";
   json += "\"sample\":" + IntegerToString(sampleIndex) + ",";
   json += "\"symbol\":\"" + JsonEscape(_Symbol) + "\",";
   json += "\"server\":\"" + JsonEscape(AccountInfoString(ACCOUNT_SERVER)) + "\",";
   json += "\"login\":" + IntegerToString(AccountInfoInteger(ACCOUNT_LOGIN)) + ",";
   json += "\"terminal_build\":" + IntegerToString(TERMINAL_BUILD) + ",";
   json += "\"timecurrent_raw\":" + IntegerToString(tc_raw) + ",";
   json += "\"timecurrent_struct\":\"" + FormatDateTime(timeCurrent) + "\",";
   json += "\"timetradeserver_raw\":" + IntegerToString(tts_raw) + ",";
   json += "\"timetradeserver_struct\":\"" + FormatDateTime(timeTradeServer) + "\",";
   json += "\"timelocal_raw\":" + IntegerToString(tl_raw) + ",";
   json += "\"timelocal_struct\":\"" + FormatDateTime(timeLocal) + "\",";
   json += "\"timegmt_raw\":" + IntegerToString(tgmt_raw) + ",";
   json += "\"timegmt_struct\":\"" + FormatDateTime(timeGMT) + "\",";
   json += "\"timegmtoffset_seconds\":" + IntegerToString(gmtOffset) + ",";
   json += "\"tick_time_raw\":" + IntegerToString(tick_time_raw) + ",";
   json += "\"tick_time_msc\":" + IntegerToString(tick_time_msc) + ",";
   json += "\"tick_bid\":" + DoubleToString(tick_bid, _Digits) + ",";
   json += "\"tick_ask\":" + DoubleToString(tick_ask, _Digits) + ",";
   json += "\"bar_time_raw\":" + IntegerToString(bar_time_raw) + ",";
   json += "\"m1_time_raw\":" + IntegerToString(m1_time_raw) + ",";
   json += "\"h1_time_raw\":" + IntegerToString(h1_time_raw) + ",";
   json += "\"server_minus_gmt_seconds\":" + IntegerToString(server_minus_gmt) + ",";
   json += "\"tick_minus_timecurrent_ms\":" + IntegerToString(tick_minus_tc * 1000) + ",";
   json += "\"tick_minus_timecurrent_msc\":" + IntegerToString(tick_minus_tc_msc);
   json += "}";

   return json;
}

//+------------------------------------------------------------------+
//| Script start function                                             |
//+------------------------------------------------------------------+
void OnStart()
{
   Print("BE-P8.3.3 Terminal Time Probe — collecting ", SampleCount, " samples...");

   int handle = FileOpen(OutputFile, FILE_WRITE|FILE_TXT|FILE_ANSI);
   if(handle == INVALID_HANDLE)
   {
      Print("ERROR: Cannot open ", OutputFile, " for writing");
      return;
   }

   // Write header comment
   FileWriteString(handle, "# BE-P8.3.3 Terminal Time Authority Probe\n");
   FileWriteString(handle, "# Symbol: " + _Symbol + "\n");
   FileWriteString(handle, "# Server: " + AccountInfoString(ACCOUNT_SERVER) + "\n");
   FileWriteString(handle, "# Login: " + IntegerToString(AccountInfoInteger(ACCOUNT_LOGIN)) + "\n");
   FileWriteString(handle, "# Samples: " + IntegerToString(SampleCount) + "\n\n");

   for(int i = 0; i < SampleCount; i++)
   {
      string json = CollectSample(i);
      FileWriteString(handle, json + "\n");
      FileFlush(handle);

      Print("Sample ", i+1, "/", SampleCount, " collected");

      if(i < SampleCount - 1)
         Sleep(SampleDelayMs);
   }

   FileClose(handle);
   Print("Probe complete. Output: ", OutputFile);
   Print("File size: ", FileSize(handle), " bytes");
}
