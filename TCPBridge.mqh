//+------------------------------------------------------------------+
//|  TCPBridge.mqh                                                   |
//|  Author: HCX Elite University                                    |
//|  Purpose: Robust TCP Client Bridge for MQL5 EAs                  |
//|  Description:                                                    |
//|    • Handles Winsock-based TCP connections via DLL imports        |
//|    • Supports JSON framing, authentication, ping/pong, queues     |
//|    • Ready for local Python relay → VPS TCP Server integration    |
//+------------------------------------------------------------------+
#property strict

//--- DLL imports from ws2_32.dll
#import "ws2_32.dll"
int    WSAStartup(ushort wVersionRequested, uchar &lpWSAData[]);
int    WSACleanup();
int    socket(int af, int type, int protocol);
int    connect(int s, uchar &name[], int namelen);
int    closesocket(int s);
int    send(int s, uchar &buf[], int len, int flags);
int    recv(int s, uchar &buf[], int len, int flags);
uint   inet_addr(uchar &cp[]);
ushort htons(ushort hostshort);
int    setsockopt(int s, int level, int optname, uchar &optval[], int optlen);
int    WSAGetLastError();
#import

//--- Winsock constants
#define AF_INET 2
#define SOCK_STREAM 1
#define IPPROTO_TCP 6
#define SOL_SOCKET 0xffff
#define SO_SNDTIMEO 0x1005
#define SO_RCVTIMEO 0x1006

//+------------------------------------------------------------------+
//| Utility Class: CSignalBuilder                                    |
//| Builds client_msg_ids and JSON payloads for trading signals      |
//+------------------------------------------------------------------+
class CSignalBuilder
{
private:
   ulong counter;
public:
   CSignalBuilder() { counter = 0; }

   string BuildClientID()
   {
      counter++;
      return TimeToString(TimeCurrent(), TIME_DATE|TIME_SECONDS) + "-" + IntegerToString((int)counter);
   }

   string BuildSignal(string action, string symbol, double price, int open_signal_id=0)
   {
      string cid = BuildClientID();
      string payload = "{";
      payload += "\"client_msg_id\":\"" + cid + "\",";
      payload += "\"action\":\"" + action + "\",";
      payload += "\"symbol\":\"" + symbol + "\",";
      payload += "\"price\":" + DoubleToString(price, _Digits);
      if(action == "CLOSE" && open_signal_id > 0)
         payload += ",\"open_signal_id\":" + IntegerToString(open_signal_id);
      payload += "}";
      return payload;
   }
};

//+------------------------------------------------------------------+
//| Networking Class: CTCPBridge                                     |
//| Handles socket connection, auth, queue, ping/pong, recv logic    |
//+------------------------------------------------------------------+
class CTCPBridge
{
private:
   //--- state
   int      sock;
   bool     connected, authenticated;
   ulong    last_recv, last_ping;
   string   server_ip, secret_key;
   int      server_port;

   //--- send queue
   string   queue_payloads[];
   string   queue_msgids[];

   //--- operational params
   int sock_timeout_ms;
   int ping_interval_sec;
   int max_message_size;

   //--- internal helpers
   bool SendAll(uchar &buf[], int len)
   {
      int sent = 0;
      while(sent < len)
      {
         int rem = len - sent;
         uchar slice[];
         ArrayResize(slice, rem);
         for(int i=0; i<rem; i++) slice[i] = buf[sent+i];
         int res = send(sock, slice, rem, 0);
         if(res > 0) sent += res;
         else
         {
            PrintFormat("SendAll() failed, errno=%d", WSAGetLastError());
            return false;
         }
      }
      return true;
   }

   int BuildMessageBytes(const string &payload, uchar &out[])
   {
      uchar bytes[];
      int len = StringToCharArray(payload, bytes, 0, -1, CP_UTF8) - 1;
      if(len <= 0) return 0;
      if(len > max_message_size) return -1;

      ArrayResize(out, len + 4);
      out[0] = (uchar)((len >> 24) & 0xFF);
      out[1] = (uchar)((len >> 16) & 0xFF);
      out[2] = (uchar)((len >> 8) & 0xFF);
      out[3] = (uchar)(len & 0xFF);
      for(int i=0; i<len; i++) out[4+i] = bytes[i];
      return len + 4;
   }

   bool ConnectSocket()
   {
      uchar wsaData[400];
      if(WSAStartup(0x202, wsaData) != 0)
      {
         Print("WSAStartup failed: ", WSAGetLastError());
         return false;
      }

      sock = socket(AF_INET, SOCK_STREAM, IPPROTO_TCP);
      if(sock < 0)
      {
         Print("socket() failed: ", WSAGetLastError());
         WSACleanup();
         return false;
      }

      int to_ms = sock_timeout_ms;
      uchar to_bytes[4];
      to_bytes[0] = (uchar)(to_ms & 0xFF);
      to_bytes[1] = (uchar)((to_ms >> 8) & 0xFF);
      to_bytes[2] = (uchar)((to_ms >> 16) & 0xFF);
      to_bytes[3] = (uchar)((to_ms >> 24) & 0xFF);
      setsockopt(sock, SOL_SOCKET, SO_SNDTIMEO, to_bytes, 4);
      setsockopt(sock, SOL_SOCKET, SO_RCVTIMEO, to_bytes, 4);

      uchar sockaddr[16];
      ArrayInitialize(sockaddr, 0);
      sockaddr[0] = AF_INET;
      ushort port_net = htons((ushort)server_port);
      sockaddr[2] = (uchar)((port_net >> 8) & 0xFF);
      sockaddr[3] = (uchar)(port_net & 0xFF);

      uchar ip_bytes[];
      StringToCharArray(server_ip, ip_bytes, 0, WHOLE_ARRAY, CP_ACP);
      uint ip_addr = inet_addr(ip_bytes);
      sockaddr[4] = (uchar)(ip_addr & 0xFF);
      sockaddr[5] = (uchar)((ip_addr >> 8) & 0xFF);
      sockaddr[6] = (uchar)((ip_addr >> 16) & 0xFF);
      sockaddr[7] = (uchar)((ip_addr >> 24) & 0xFF);

      if(connect(sock, sockaddr, 16) != 0)
      {
         PrintFormat("connect() failed to %s:%d. errno=%d", server_ip, server_port, WSAGetLastError());
         closesocket(sock);
         WSACleanup();
         return false;
      }
      connected = true;
      return true;
   }

public:
   CTCPBridge()
   {
      sock = -1;
      connected = false;
      authenticated = false;
      last_recv = 0;
      last_ping = 0;
      sock_timeout_ms = 2000;
      ping_interval_sec = 30;
      max_message_size = 4 * 1024 * 1024;
   }

   bool Connect(string ip, int port)
   {
      server_ip = ip;
      server_port = port;
      return ConnectSocket();
   }

   bool Authenticate(string key)
   {
      secret_key = key;
      if(!connected) return false;

      string auth = "{\"secret_key\":\"" + secret_key + "\"}";
      uchar msg[];
      int total = BuildMessageBytes(auth, msg);
      if(total <= 0) return false;

      if(!SendAll(msg, total)) return false;

      uchar hdr[4];
      int got = recv(sock, hdr, 4, 0);
      if(got <= 0) return false;

      int len = (hdr[0]<<24)|(hdr[1]<<16)|(hdr[2]<<8)|hdr[3];
      if(len <= 0 || len > 8192) return false;

      uchar body[];
      ArrayResize(body, len);
      int rc = recv(sock, body, len, 0);
      if(rc <= 0) return false;

      string resp = CharArrayToString(body, 0, rc);
      if(StringFind(resp, "\"status\":\"success\"") >= 0)
      {
         Print("Authenticated with server successfully.");
         authenticated = true;
         last_recv = GetTickCount64();
         last_ping = GetTickCount64();
         return true;
      }
      Print("Authentication failed: ", resp);
      return false;
   }

   bool SendJSON(string payload)
   {
      if(!authenticated) return false;
      uchar msg[];
      int total = BuildMessageBytes(payload, msg);
      if(total <= 0) return false;
      return SendAll(msg, total);
   }

   void HandleIncoming()
   {
      if(!authenticated) return;
      uchar hdr[4];
      int r = recv(sock, hdr, 4, 0);
      if(r <= 0) return;
      int len = (hdr[0]<<24)|(hdr[1]<<16)|(hdr[2]<<8)|hdr[3];
      if(len <= 0 || len > max_message_size) return;

      uchar body[];
      ArrayResize(body, len);
      int got = recv(sock, body, len, 0);
      if(got <= 0) return;
      string resp = CharArrayToString(body, 0, got);
      last_recv = GetTickCount64();

      if(StringFind(resp, "\"type\":\"pong\"") >= 0)
         Print("Received pong.");
      else
         Print("Server response: ", resp);
   }

   void SendPingIfNeeded()
   {
      if(!authenticated) return;
      if(GetTickCount64() - last_ping > (ulong)ping_interval_sec * 1000)
      {
         string ping = "{\"type\":\"ping\"}";
         uchar msg[];
         int total = BuildMessageBytes(ping, msg);
         if(total > 0) SendAll(msg, total);
         last_ping = GetTickCount64();
      }
   }

   void Disconnect()
   {
      if(sock >= 0) closesocket(sock);
      if(connected || authenticated) WSACleanup();
      connected = false;
      authenticated = false;
      sock = -1;
      Print("Disconnected TCP bridge.");
   }
};
