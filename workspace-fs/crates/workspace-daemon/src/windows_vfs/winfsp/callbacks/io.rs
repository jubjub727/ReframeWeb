use winfsp_wrs_sys::{
    BOOLEAN, FSP_FILE_SYSTEM, FSP_FSCTL_FILE_INFO, NTSTATUS, PULONG, PVOID, UINT64, ULONG,
};

use super::{guard, handle, runtime};

pub(in crate::windows_vfs::winfsp) unsafe extern "C" fn read(
    file_system: *mut FSP_FILE_SYSTEM,
    file_context: PVOID,
    buffer: PVOID,
    offset: UINT64,
    length: ULONG,
    bytes_transferred: PULONG,
) -> NTSTATUS {
    guard(|| {
        if buffer.is_null() || bytes_transferred.is_null() {
            return Err(super::super::status::INVALID_PARAMETER);
        }
        let output = unsafe { std::slice::from_raw_parts_mut(buffer.cast(), length as usize) };
        let count = unsafe { runtime(file_system) }?.read(
            unsafe { handle(file_context) }?,
            output,
            offset,
        )?;
        unsafe { bytes_transferred.write(count as ULONG) };
        Ok(())
    })
}

#[allow(clippy::too_many_arguments)]
pub(in crate::windows_vfs::winfsp) unsafe extern "C" fn write(
    file_system: *mut FSP_FILE_SYSTEM,
    file_context: PVOID,
    buffer: PVOID,
    offset: UINT64,
    length: ULONG,
    write_to_end: BOOLEAN,
    constrained: BOOLEAN,
    bytes_transferred: PULONG,
    file_info: *mut FSP_FSCTL_FILE_INFO,
) -> NTSTATUS {
    guard(|| {
        if (buffer.is_null() && length != 0) || bytes_transferred.is_null() || file_info.is_null() {
            return Err(super::super::status::INVALID_PARAMETER);
        }
        let input = if length == 0 {
            &[]
        } else {
            unsafe { std::slice::from_raw_parts(buffer.cast(), length as usize) }
        };
        let (count, info) = unsafe { runtime(file_system) }?.write(
            unsafe { handle(file_context) }?,
            input,
            offset,
            write_to_end != 0,
            constrained != 0,
        )?;
        unsafe {
            bytes_transferred.write(count as ULONG);
            file_info.write(info);
        }
        Ok(())
    })
}

pub(in crate::windows_vfs::winfsp) unsafe extern "C" fn flush(
    file_system: *mut FSP_FILE_SYSTEM,
    file_context: PVOID,
    file_info: *mut FSP_FSCTL_FILE_INFO,
) -> NTSTATUS {
    guard(|| {
        if file_context.is_null() {
            return Ok(());
        }
        if file_info.is_null() {
            return Err(super::super::status::INVALID_PARAMETER);
        }
        let info =
            unsafe { runtime(file_system) }?.handle_info(unsafe { handle(file_context) }?)?;
        unsafe { file_info.write(info) };
        Ok(())
    })
}

pub(in crate::windows_vfs::winfsp) unsafe extern "C" fn set_file_size(
    file_system: *mut FSP_FILE_SYSTEM,
    file_context: PVOID,
    new_size: UINT64,
    set_allocation_size: BOOLEAN,
    file_info: *mut FSP_FSCTL_FILE_INFO,
) -> NTSTATUS {
    guard(|| {
        if file_info.is_null() {
            return Err(super::super::status::INVALID_PARAMETER);
        }
        let info = unsafe { runtime(file_system) }?.resize(
            unsafe { handle(file_context) }?,
            new_size,
            set_allocation_size != 0,
        )?;
        unsafe { file_info.write(info) };
        Ok(())
    })
}
