// TCPRawBridge.mqh
// Raw Winsock TCP bridge for MQL5 EAs
// - Persistent Winsock connection (ws2_32.dll) via guarded include
// - 4-byte big-endian length-prefix framing + UTF-8 JSON payloads
// - Multi-symbol signal tracking, optional close, heartbeats
// - Reconnect with exponential backoff

#ifndef __TCPRAWBRIDGE_MQH__
#define __TCPRAWBRIDGE_MQH__

#property strict

// include winsock imports (guarded single definition shared by all EAs)
#include <WinsockImports.mqh>

//--- Constants
#define AF_INET 2
#define SOCK_STREAM 1
#define IPPROTO_TCP 6
#define SOL_SOCKET 0xffff
#define SO_SNDTIMEO 0x1005
#define SO_RCVTIMEO 0x1006

//--- Configuration defaults (adjust in EA or set via TCP_Config)
int   TCP_DEFAULT_RCV_TIMEOUT_MS = 50;  // small recv timeout so polling doesn't block
int   TCP_DEFAULT_SND_TIMEOUT_MS = 2000;
int   TCP_PING_INTERVAL_SEC = 30;
int   TCP_MAX_MESSAGE_SIZE = 4 * 1024 * 1024; // 4MB max

//--- Signal status enums
#define S_PENDING   0
#define S_CONFIRMED 1
#define S_FAILED    2
#define S_CLOSED    3

//--- SignalInfo struct
struct SignalInfo
{
   string client_id;
   string symbol;
   string action; // "BUY","SELL","OPEN","CLOSE" etc.
   double price;
   bool   open;
   int    server_signal_id; // from VPS/database
   int    status; // S_PENDING, S_CONFIRMED, S_FAILED, S_CLOSED
   datetime ts;
};

//--- Internal globals (visible to EA because header included there)
int      TCP_sock = -1;
bool     TCP_connected = false;
bool     TCP_authenticated = false;
string   TCP_host = "127.0.0.1";
int      TCP_port = 31415;
ulong    TCP_last_recv_ms = 0;
ulong    TCP_last_ping_ms = 0;
int      TCP_rcv_timeout_ms = 50;
int      TCP_snd_timeout_ms = 2000;
int      TCP_backoff_sec = 1;
ulong    TCP_client_counter = 0;
SignalInfo g_signals[];

//--- Forward declarations (public API)
bool TCP_Init(const string host, const int port);
bool TCP_IsConnected();
void TCP_Close();
bool TCP_SendJSON(const string json);
void TCP_Poll(); // call periodically (OnTimer) to process incoming messages
string SignalOpen(const string symbol, const string action, const double price, const bool allow_close=true);
string SignalClose(const string open_client_id, const double price);
int    FindSignalIndexByClientID(const string cid);
void   TCP_SetTimeouts(int rcv_ms, int snd_ms);
void   TCP_SetPingInterval(int sec);

//+------------------------------------------------------------------+
//| Utility: current ms (approx)                                     |
//+------------------------------------------------------------------+
ulong NowMS()
{
   return (ulong)TimeCurrent() * 1000;
}

//+------------------------------------------------------------------+
//| Internal: build length prefixed message into byte array          |
//+------------------------------------------------------------------+
int TCP_BuildMessageBytes(const string &payload, uchar &out[])
{
   uchar payload_bytes[];
   int payload_len = StringToCharArray(payload, payload_bytes, 0, -1, CP_UTF8) - 1;
   if(payload_len <= 0) return 0;
   if(payload_len > TCP_MAX_MESSAGE_SIZE) return -1;

   ArrayResize(out, payload_len + 4);
   out[0] = (uchar)((payload_len >> 24) & 0xFF);
   out[1] = (uchar)((payload_len >> 16) & 0xFF);
   out[2] = (uchar)((payload_len >> 8) & 0xFF);
   out[3] = (uchar)(payload_len & 0xFF);
   for(int i=0;i<payload_len;i++) out[4+i] = payload_bytes[i];
   return payload_len + 4;
}

//+------------------------------------------------------------------+
//| Internal: SendAll - send all bytes using slices (safe for MQL)   |
//+------------------------------------------------------------------+
bool TCP_SendAll(int sock, uchar &buf[], int len)
{
   int sent = 0;
   while(sent < len)
   {
      int rem = len - sent;
      uchar slice[];
      ArrayResize(slice, rem);
      for(int i=0;i<rem;i++) slice[i] = buf[sent + i];
      int res = send(sock, slice, rem, 0);
      if(res > 0)
      {
         sent += res;
      }
      else
      {
         int err = WSAGetLastError();
         PrintFormat("TCP_SendAll: send() failed, errno=%d", err);
         return false;
      }
   }
   return true;
}

//+------------------------------------------------------------------+
//| Internal: try connect socket (no auth)                           |
//+------------------------------------------------------------------+
// Robust TCP_ConnectSocket(): explicit port/IP byte placement (avoids endian surprises)
bool TCP_ConnectSocket()
{
   // Clean up previous
   if(TCP_sock >= 0) { closesocket(TCP_sock); TCP_sock = -1; TCP_connected = false; TCP_authenticated = false; }

   uchar wsaData[400];
   if(WSAStartup(0x202, wsaData) != 0)
   {
      PrintFormat("TCP_ConnectSocket: WSAStartup failed (errno=%d)", WSAGetLastError());
      return false;
   }

   int sock = socket(AF_INET, SOCK_STREAM, IPPROTO_TCP);
   if(sock < 0)
   {
      PrintFormat("TCP_ConnectSocket: socket() failed (errno=%d)", WSAGetLastError());
      WSACleanup();
      return false;
   }

   // set send/recv timeouts
   int to_ms = TCP_rcv_timeout_ms;
   uchar to_bytes[];
   ArrayResize(to_bytes,4);
   to_bytes[0] = (uchar)(to_ms & 0xFF);
   to_bytes[1] = (uchar)((to_ms >> 8) & 0xFF);
   to_bytes[2] = (uchar)((to_ms >> 16) & 0xFF);
   to_bytes[3] = (uchar)((to_ms >> 24) & 0xFF);
   setsockopt(sock, SOL_SOCKET, SO_RCVTIMEO, to_bytes, 4);

   to_ms = TCP_snd_timeout_ms;
   to_bytes[0] = (uchar)(to_ms & 0xFF);
   to_bytes[1] = (uchar)((to_ms >> 8) & 0xFF);
   to_bytes[2] = (uchar)((to_ms >> 16) & 0xFF);
   to_bytes[3] = (uchar)((to_ms >> 24) & 0xFF);
   setsockopt(sock, SOL_SOCKET, SO_SNDTIMEO, to_bytes, 4);

   // build sockaddr_in (16 bytes)
   uchar sockaddr[16];
   ArrayInitialize(sockaddr,0);

   // sin_family (ushort) little-endian -> write low then high (AF_INET == 2 -> 0x02 0x00)
   sockaddr[0] = (uchar)(AF_INET & 0xFF);
   sockaddr[1] = (uchar)((AF_INET >> 8) & 0xFF);

   // Place port bytes explicitly in network (big-endian) order: MSB then LSB
   ushort port_val = (ushort)TCP_port;
   sockaddr[2] = (uchar)((port_val >> 8) & 0xFF); // MSB
   sockaddr[3] = (uchar)(port_val & 0xFF);        // LSB

   // --- Resolve IP: prefer dotted-quad parsing (deterministic) ---
   string parts[];
   int parts_count = StringSplit(TCP_host, ".", parts);
   bool ip_ok = false;
   if(parts_count == 4)
   {
      bool valid = true;
      for(int i=0;i<4;i++)
      {
         int oct = (int)StringToInteger(parts[i]);
         if(oct < 0 || oct > 255) { valid = false; break; }
         sockaddr[4 + i] = (uchar)(oct & 0xFF); // store MSB-first: parts[0] -> sockaddr[4]
      }
      if(valid) ip_ok = true;
      else
      {
         // Fall through to inet_addr() fallback
         ArrayInitialize(sockaddr,0);
         sockaddr[0] = (uchar)(AF_INET & 0xFF);
         sockaddr[1] = (uchar)((AF_INET >> 8) & 0xFF);
         sockaddr[2] = (uchar)((port_val >> 8) & 0xFF);
         sockaddr[3] = (uchar)(port_val & 0xFF);
      }
   }

   if(!ip_ok)
   {
      // Fallback: use inet_addr() and place bytes explicitly from least-significant to most
      uchar ip_chars[];
      StringToCharArray(TCP_host, ip_chars, 0, WHOLE_ARRAY, CP_ACP);
      uint ip_addr = inet_addr(ip_chars); // may return (uint)-1 on failure
      if(ip_addr == (uint)-1)
      {
         PrintFormat("TCP_ConnectSocket: inet_addr() failed for host='%s' (not a dotted IPv4).", TCP_host);
         closesocket(sock);
         WSACleanup();
         return false;
      }
      // ip_addr here may be in host or network order depending on platform; write bytes LSB->MSB to obtain correct dotted-quad
      sockaddr[4] = (uchar)((ip_addr) & 0xFF);
      sockaddr[5] = (uchar)((ip_addr >> 8) & 0xFF);
      sockaddr[6] = (uchar)((ip_addr >> 16) & 0xFF);
      sockaddr[7] = (uchar)((ip_addr >> 24) & 0xFF);
   }

   // Diagnostic prints
   PrintFormat("TCP_ConnectSocket: attempting connect to host='%s' port=%d", TCP_host, TCP_port);
   PrintFormat("TCP_ConnectSocket: sockaddr[0..7]=%02X %02X %02X %02X %02X %02X %02X %02X",
               sockaddr[0], sockaddr[1], sockaddr[2], sockaddr[3],
               sockaddr[4], sockaddr[5], sockaddr[6], sockaddr[7]);

   int rc = connect(sock, sockaddr, 16);
   if(rc != 0)
   {
      int err = WSAGetLastError();
      PrintFormat("TCP_ConnectSocket: connect() failed to %s:%d errno=%d (connect rc=%d)", TCP_host, TCP_port, err, rc);
      closesocket(sock);
      WSACleanup();
      return false;
   }

   TCP_sock = sock;
   TCP_connected = true;
   TCP_last_recv_ms = NowMS();
   TCP_last_ping_ms = NowMS();
   TCP_backoff_sec = 1;
   PrintFormat("TCP_ConnectSocket: Connected to %s:%d", TCP_host, TCP_port);
   return true;
}


//+------------------------------------------------------------------+
//| Public: init and configure                                       |
//+------------------------------------------------------------------+
bool TCP_Init(const string host, const int port)
{
   TCP_host = host;
   TCP_port = port;
   TCP_rcv_timeout_ms = TCP_DEFAULT_RCV_TIMEOUT_MS;
   TCP_snd_timeout_ms = TCP_DEFAULT_SND_TIMEOUT_MS;
   return TCP_ConnectSocket();
}

void TCP_SetTimeouts(int rcv_ms, int snd_ms)
{
   TCP_rcv_timeout_ms = rcv_ms;
   TCP_snd_timeout_ms = snd_ms;
}

void TCP_SetPingInterval(int sec)
{
   TCP_PING_INTERVAL_SEC = sec;
}

//+------------------------------------------------------------------+
//| Public: check connection                                          |
//+------------------------------------------------------------------+
bool TCP_IsConnected()
{
   return (TCP_connected && TCP_sock >= 0);
}

//+------------------------------------------------------------------+
//| Public: close                                                     |
//+------------------------------------------------------------------+
void TCP_Close()
{
   if(TCP_sock >= 0)
   {
      closesocket(TCP_sock);
      TCP_sock = -1;
   }
   if(TCP_connected || TCP_authenticated) WSACleanup();
   TCP_connected = false;
   TCP_authenticated = false;
   Print("TCP_Close: Connection closed.");
}

//+------------------------------------------------------------------+
//| Public: send JSON (synchronous, safe)                            |
//+------------------------------------------------------------------+
bool TCP_SendJSON(const string json)
{
   if(!TCP_IsConnected())
   {
      Print("TCP_SendJSON: Not connected.");
      return false;
   }

   uchar out[];
   int total = TCP_BuildMessageBytes(json, out);
   if(total <= 0)
   {
      Print("TCP_SendJSON: payload invalid or too large");
      return false;
   }
   return TCP_SendAll(TCP_sock, out, total);
}

//+------------------------------------------------------------------+
//| Internal: parse and apply a JSON-like response string from VPS   |
//| using substring extraction (no heavy JSON library)               |
//+------------------------------------------------------------------+
void TCP_HandleMessage(const string m)
{
   // Example messages expected:
   // {"status":"success","message":"Signal BUY processed successfully","signal_id":12,"client_msg_id":"2025..."}
   // {"type":"pong"}
   string s = m;
   // trim and normalize JSON spacing to make parsing reliable
   StringTrimLeft(s);
   StringTrimRight(s);
   StringReplace(s, ": ", ":");
   StringReplace(s, ", ", ",");
   if(StringLen(s) == 0) return;

   // pong
   if(StringFind(s, "\"type\":\"pong\"", 0) >= 0 || StringFind(s, "\"type\": \"pong\"", 0) >= 0)
   {
      // update last recv
      TCP_last_recv_ms = NowMS();
      //Print("TCP_HandleMessage: pong received");
      return;
   }

   // get client_msg_id
   string cid = "";
   int pos = StringFind(s, "\"client_msg_id\":\"", 0);
   if(pos >= 0)
   {
      int start = pos + StringLen("\"client_msg_id\":\"");
      int end = StringFind(s, "\"", start);
      if(end > start) cid = StringSubstr(s, start, end - start);
   }

   // get status success/error
   bool confirmed = (StringFind(s, "\"status\":\"success\"", 0) >= 0 || StringFind(s, "\"status\": \"success\"", 0) >= 0);
   bool is_error = (StringFind(s, "\"status\":\"error\"", 0) >= 0 || StringFind(s, "\"status\": \"error\"", 0) >= 0);

   // get signal_id numeric if present
   int sigid = 0;
   int pos_sig = StringFind(s, "\"signal_id\":", 0);
   if(pos_sig >= 0)
   {
      int j = pos_sig + StringLen("\"signal_id\":");
      string digits = "";
      while(j < StringLen(s))
      {
         int ch = StringGetCharacter(s, j);
         if(ch >= '0' && ch <= '9') digits += CharToString((uchar)ch);
         else break;
         j++;
      }
      if(StringLen(digits) > 0) sigid = (int)StringToInteger(digits);
   }

   // get open_client_msg_id (used for close ack)
   string open_cid = "";
   int pos_open = StringFind(s, "\"open_client_msg_id\":\"", 0);
   if(pos_open >= 0)
   {
      int start = pos_open + StringLen("\"open_client_msg_id\":\"");
      int end = StringFind(s, "\"", start);
      if(end > start) open_cid = StringSubstr(s, start, end - start);
   }

      // Apply to tracked signals
      if(cid != "")
      {
         int idx = FindSignalIndexByClientID(cid);
         if(idx >= 0)
         {
            if(confirmed)
            {
               g_signals[idx].status = S_CONFIRMED;
               if(sigid > 0) g_signals[idx].server_signal_id = sigid; // Store the server ID
               g_signals[idx].open = (StringFind(g_signals[idx].action, "CLOSE", 0) < 0);
               PrintFormat("[TCP] Confirmed client=%s -> server_id=%d", cid, sigid);
            }
            else if(is_error)
            {
               g_signals[idx].status = S_FAILED;
               PrintFormat("[TCP] Error for client=%s payload=%s", cid, s);
            }
         }
         else
         {
            // This could be a confirmation for a CLOSE signal, which has its own client_id
            // We need to find the original signal via open_client_msg_id if present
            if(open_cid != "")
            {
               int open_idx = FindSignalIndexByClientID(open_cid);
               if(open_idx >= 0)
               {
                  g_signals[open_idx].status = S_CLOSED;
                  g_signals[open_idx].open = false;
                  PrintFormat("[TCP] Closed confirmation received for open_client_id=%s", open_cid);
               }
            }
            else
            {
               PrintFormat("[TCP] Received confirmation for unknown client_msg_id=%s payload=%s", cid, s);
            }
         }
      }   else
   {
      PrintFormat("[TCP] Message without client id: %s", s);
   }

   TCP_last_recv_ms = NowMS();
}
//+------------------------------------------------------------------+
//| Public: Poll incoming data (non-blocking because of small timeout)|
//| Call this periodically (OnTimer)                                 |
//+------------------------------------------------------------------+
void TCP_Poll()
{
   if(!TCP_IsConnected()) return;

   uchar hdr[4];
   int r = recv(TCP_sock, hdr, 4, 0);
   if(r <= 0) return; // nothing or error (timeout)

   int msg_len = (hdr[0]<<24)|(hdr[1]<<16)|(hdr[2]<<8)|hdr[3];
   if(msg_len <= 0 || msg_len > TCP_MAX_MESSAGE_SIZE)
   {
      PrintFormat("TCP_Poll: invalid message len=%d", msg_len);
      return;
   }

   uchar body[];
   ArrayResize(body, msg_len);
   int got = recv(TCP_sock, body, msg_len, 0);
   if(got <= 0) return;
   string resp = CharArrayToString(body, 0, got);
   TCP_HandleMessage(resp);
}

//+------------------------------------------------------------------+
//| Public: ensure connection (call regularly) with exponential backoff|
//+------------------------------------------------------------------+
void TCP_ReconnectIfNeeded()
{
   if(TCP_IsConnected()) return;

   // try to connect with exponential backoff
   if(TCP_ConnectSocket())
   {
      Print("TCP_ReconnectIfNeeded: reconnected.");
      return;
   }
   else
   {
      PrintFormat("TCP_ReconnectIfNeeded: connect failed; sleeping %d sec", TCP_backoff_sec);
      Sleep(TCP_backoff_sec * 1000);
      TCP_backoff_sec = MathMin(TCP_backoff_sec * 2, 64);
   }
}

//+------------------------------------------------------------------+
//| Public: Generate client id and register open signal              |
//+------------------------------------------------------------------+
string GenerateClientID()
{
   TCP_client_counter++;
   return(TimeToString(TimeCurrent(), TIME_DATE|TIME_SECONDS) + "-" + IntegerToString((int)TCP_client_counter));
}

//+------------------------------------------------------------------+
//| Public: SignalOpen - create + send open signal, returns client id |
//+------------------------------------------------------------------+
string SignalOpen(const string symbol, const string action, const double price, const bool allow_close=true)
{
   string cid = GenerateClientID();
   // register locally
   SignalInfo info;
   info.client_id = cid;
   info.symbol = symbol;
   info.action = action;
   info.price = price;
   info.open = allow_close; // treat allow_close true means we expect it can be closed
   info.server_signal_id = 0;
   info.status = S_PENDING;
   info.ts = TimeCurrent();
   int pos = ArraySize(g_signals);
   ArrayResize(g_signals, pos+1);
   g_signals[pos] = info;

   // build JSON payload
   string payload = "{";
   payload += "\"type\":\"signal\",";
   payload += "\"client_msg_id\":\"" + cid + "\",";
   payload += "\"action\":\"" + action + "\",";
   payload += "\"symbol\":\"" + symbol + "\",";
   payload += "\"price\":" + DoubleToString(price, _Digits);
   if(allow_close) payload += ",\"allow_close\":true";
   payload += "}";

   if(TCP_IsConnected())
   {
      if(TCP_SendJSON(payload))
         PrintFormat("[SignalOpen] Sent client_msg_id=%s symbol=%s", cid, symbol);
      else
         PrintFormat("[SignalOpen] Failed to send client_msg_id=%s", cid);
   }
   else
   {
      PrintFormat("[SignalOpen] Not connected; queued locally client_msg_id=%s", cid);
      // left in g_signals for retry or manual resend later
   }
   return(cid);
}


//+------------------------------------------------------------------+
//| Public: SignalClose - send close referencing open_client_msg_id  |
//+------------------------------------------------------------------+
string SignalClose(const int open_server_id, const double price)
{
   // --- Find the original signal to get its symbol ---
   string symbol_to_close = "";
   for(int i=0; i<ArraySize(g_signals); i++)
   {
      if(g_signals[i].server_signal_id == open_server_id)
      {
         symbol_to_close = g_signals[i].symbol;
         break;
      }
   }
   if(symbol_to_close == "")
   {
      PrintFormat("[SignalClose] Error: Could not find original signal with server_id=%d to close.", open_server_id);
      return "";
   }
   // --- End of fix ---

   string cid = GenerateClientID();
   // register closing signal locally
   SignalInfo info;
   info.client_id = cid;
   info.symbol = symbol_to_close; // Use the found symbol
   info.action = "CLOSE";
   info.price = price;
   info.open = false;
   info.server_signal_id = 0;
   info.status = S_PENDING;
   info.ts = TimeCurrent();
   int pos = ArraySize(g_signals);
   ArrayResize(g_signals, pos+1);
   g_signals[pos] = info;

   string payload = "{";
   payload += "\"type\":\"signal\",";
   payload += "\"client_msg_id\":\"" + cid + "\",";
   payload += "\"action\":\"CLOSE\",";
   payload += "\"symbol\":\"" + symbol_to_close + "\","; // Correctly include the symbol
   payload += "\"open_signal_id\":" + IntegerToString(open_server_id) + ","; // Use the correct field name
   payload += "\"price\":" + DoubleToString(price, _Digits);
   payload += "}";

   if(TCP_IsConnected())
   {
      if(TCP_SendJSON(payload))
         PrintFormat("[SignalClose] Sent close client_msg_id=%s for open_server_id=%d", cid, open_server_id);
      else
         PrintFormat("[SignalClose] Failed to send close client_msg_id=%s", cid);
   }
   else
   {
      PrintFormat("[SignalClose] Not connected; queued close client_msg_id=%s", cid);
   }
   return(cid);
}

//+------------------------------------------------------------------+
//| Public: Find signal index by client id                           |
//+------------------------------------------------------------------+
int FindSignalIndexByClientID(const string cid)
{
   for(int i=0;i<ArraySize(g_signals);i++)
      if(g_signals[i].client_id == cid) return i;
   return -1;
}

//+------------------------------------------------------------------+
//| End of header                                                     |
//+------------------------------------------------------------------+
#endif // __TCPRAWBRIDGE_MQH__