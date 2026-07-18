use std::sync::OnceLock;

use anyhow::{Context, Result};
use windows::Win32::Foundation::{HLOCAL, LocalFree};
use windows::Win32::Security::Authorization::{
    ConvertStringSecurityDescriptorToSecurityDescriptorW, SDDL_REVISION_1,
};
use windows::Win32::Security::PSECURITY_DESCRIPTOR as WindowsSecurityDescriptor;
use windows::core::PCWSTR;

const DEFAULT_SDDL: &str = "O:BAG:BAD:P(A;;FA;;;SY)(A;;FA;;;BA)(A;;FA;;;WD)";

pub(super) fn default_descriptor() -> Result<&'static [u8]> {
    static DESCRIPTOR: OnceLock<Result<Vec<u8>, String>> = OnceLock::new();
    DESCRIPTOR
        .get_or_init(create_default_descriptor)
        .as_ref()
        .map(Vec::as_slice)
        .map_err(|message| anyhow::Error::msg(message.clone()))
}

fn create_default_descriptor() -> Result<Vec<u8>, String> {
    let sddl = DEFAULT_SDDL.encode_utf16().chain([0]).collect::<Vec<_>>();
    let mut descriptor = WindowsSecurityDescriptor::default();
    let mut descriptor_size = 0u32;
    unsafe {
        ConvertStringSecurityDescriptorToSecurityDescriptorW(
            PCWSTR::from_raw(sddl.as_ptr()),
            SDDL_REVISION_1,
            &mut descriptor,
            Some(&mut descriptor_size),
        )
    }
    .context("create the WinFsp default security descriptor")
    .map_err(|error| format!("{error:#}"))?;

    let bytes = unsafe {
        std::slice::from_raw_parts(descriptor.0.cast::<u8>(), descriptor_size as usize).to_vec()
    };
    unsafe {
        LocalFree(Some(HLOCAL(descriptor.0)));
    }
    Ok(bytes)
}
