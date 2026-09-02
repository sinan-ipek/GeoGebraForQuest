#include <windows.h>

// GeoGebraForQuest PC v0.9
// The v0.8 diagnostic opened the shared-memory mapping read-only, but then
// used InterlockedCompareExchange64 merely to read the sequence counter.
// That intrinsic is a read-modify-write operation and can fault on a
// FILE_MAP_READ view. On the x64 target an aligned volatile 64-bit load is
// atomic, so replace that specific read primitive before compiling v0.8.
static inline LONG64 GgqReadOnlySequence(volatile LONG64* address) noexcept
{
#if defined(_M_X64) || defined(_M_ARM64)
    return *address;
#else
    return InterlockedCompareExchange64(address, 0, 0);
#endif
}

#ifdef InterlockedCompareExchange64
#undef InterlockedCompareExchange64
#endif
#define InterlockedCompareExchange64(destination, exchange, comparand) \
    GgqReadOnlySequence(destination)

#include "main-v08.cpp"
