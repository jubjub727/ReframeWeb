use anyhow::{Result, bail};
use winfsp_wrs_sys::FspVersion;

use super::status;

const MINIMUM_SAFE_API_VERSION: u32 = 0x0002_0002;

pub(super) fn require_safe_runtime() -> Result<()> {
    let mut version = 0u32;
    let result = unsafe { FspVersion(&mut version) };
    if result != status::SUCCESS {
        bail!("query WinFsp runtime version failed with NTSTATUS 0x{result:08X}");
    }
    if !is_safe(version) {
        let (major, minor) = decode(version);
        bail!("WinFsp {major}.{minor} is unsupported; WinFsp 2.2.26112 or newer is required");
    }
    Ok(())
}

fn is_safe(version: u32) -> bool {
    version >= MINIMUM_SAFE_API_VERSION
}

fn decode(version: u32) -> (u16, u16) {
    ((version >> 16) as u16, version as u16)
}

#[cfg(test)]
mod tests {
    use super::{decode, is_safe};

    #[test]
    fn decodes_major_and_minor_halves() {
        assert_eq!((2, 0), decode(0x0002_0000));
        assert_eq!((2, 2), decode(0x0002_0002));
    }

    #[test]
    fn rejects_versions_before_safe_release_line() {
        assert!(!is_safe(0x0002_0000));
        assert!(!is_safe(0x0002_0001));
        assert!(is_safe(0x0002_0002));
        assert!(is_safe(0x0003_0000));
    }
}
