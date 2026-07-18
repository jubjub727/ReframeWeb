# Third-party notices

## WinFsp

WinFsp - Windows File System Proxy, Copyright (C) Bill Zissimopoulos.

WinFsp is licensed under GPLv3 with a special exception that permits qualifying
FLOSS software to link the platform WinFsp DLL and distribute an unmodified
WinFsp installer. The exception does not permit mixing WinFsp with proprietary
software; commercial licensing is available from the WinFsp author. Reframe's
Windows provider loads the separately installed WinFsp runtime and does not
redistribute it here. See the [WinFsp repository](https://github.com/winfsp/winfsp)
and the license shipped with the WinFsp installer for the complete terms.

The provider uses `winfsp_wrs_sys` under the MIT license and `winfsp_build`
under MIT OR Apache-2.0. It deliberately does not use the GPL-3.0 `winfsp`
high-level Rust wrapper.
