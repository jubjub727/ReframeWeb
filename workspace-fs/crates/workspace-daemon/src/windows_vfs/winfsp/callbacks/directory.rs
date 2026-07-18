use winfsp_wrs_sys::{
    FSP_FILE_SYSTEM, FspFileSystemAddDirInfo, NTSTATUS, PULONG, PVOID, PWSTR, ULONG,
};

use super::{guard, handle, runtime};
use crate::windows_vfs::winfsp::{info::DirectoryInfo, path};

pub(in crate::windows_vfs::winfsp) unsafe extern "C" fn read_directory(
    file_system: *mut FSP_FILE_SYSTEM,
    file_context: PVOID,
    _pattern: PWSTR,
    marker: PWSTR,
    buffer: PVOID,
    length: ULONG,
    bytes_transferred: PULONG,
) -> NTSTATUS {
    guard(|| {
        if buffer.is_null() || bytes_transferred.is_null() {
            return Err(super::super::status::INVALID_PARAMETER);
        }
        unsafe { bytes_transferred.write(0) };
        let marker = unsafe { path::optional_component(marker) }?;
        let mut invalid_name = false;
        let complete = unsafe { runtime(file_system) }?.visit_directory_entries(
            unsafe { handle(file_context) }?,
            marker.as_deref(),
            |name, file_info| {
                let Some(mut entry) = DirectoryInfo::new(name, file_info) else {
                    invalid_name = true;
                    return false;
                };
                unsafe {
                    FspFileSystemAddDirInfo(entry.raw(), buffer, length, bytes_transferred) != 0
                }
            },
        )?;
        if invalid_name {
            return Err(super::super::status::INVALID_PARAMETER);
        }
        if !complete {
            return Ok(());
        }
        unsafe {
            FspFileSystemAddDirInfo(std::ptr::null_mut(), buffer, length, bytes_transferred);
        }
        Ok(())
    })
}
