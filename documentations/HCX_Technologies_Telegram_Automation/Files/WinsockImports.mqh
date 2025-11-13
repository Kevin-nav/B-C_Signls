// WinsockImports.mqh
// Single place to declare ws2_32.dll imports.  Keep this file simple and unguarded.

#import "Ws2_32.dll"
int    WSAStartup(ushort wVersionRequested, uchar &lpWSAData[]);
int    WSACleanup();
int    socket(int af, int type, int protocol);
int    connect(int s, uchar &name[], int namelen);
int    send(int s, uchar &buf[], int len, int flags);
int    recv(int s, uchar &buf[], int len, int flags);
int    closesocket(int s);
uint   inet_addr(uchar &cp[]);
ushort htons(ushort hostshort);
int    setsockopt(int s, int level, int optname, uchar &optval[], int optlen);
int    WSAGetLastError();
#import
