use winfsp_wrs_sys::{
    BOOLEAN, FSP_FILE_SYSTEM, FSP_FSCTL_FILE_INFO, FspCleanupDelete, NTSTATUS,
    PSECURITY_DESCRIPTOR, PVOID, PWSTR, UINT32, UINT64, ULONG,
};

use super::{guard, guard_void, handle, runtime, write_handle};
use crate::windows_vfs::winfsp::path;

#[allow(clippy::too_many_arguments)]
pub(in crate::windows_vfs::winfsp) unsafe extern "C" fn create(
    file_system: *mut FSP_FILE_SYSTEM,
    file_name: PWSTR,
    create_options: UINT32,
    _granted_access: UINT32,
    _file_attributes: UINT32,
    _security_descriptor: PSECURITY_DESCRIPTOR,
    _allocation_size: UINT64,
    file_context: *mut PVOID,
    file_info: *mut FSP_FSCTL_FILE_INFO,
) -> NTSTATUS {
    guard(|| {
        if file_context.is_null() || file_info.is_null() {
            return Err(super::super::status::INVALID_PARAMETER);
        }
        let path = unsafe { path::from_wide(file_name) }?;
        let (handle, info) = unsafe { runtime(file_system) }?.create(&path, create_options)?;
        unsafe {
            write_handle(file_context, handle)?;
            file_info.write(info);
        }
        Ok(())
    })
}

pub(in crate::windows_vfs::winfsp) unsafe extern "C" fn open(
    file_system: *mut FSP_FILE_SYSTEM,
    file_name: PWSTR,
    create_options: UINT32,
    _granted_access: UINT32,
    file_context: *mut PVOID,
    file_info: *mut FSP_FSCTL_FILE_INFO,
) -> NTSTATUS {
    guard(|| {
        if file_context.is_null() || file_info.is_null() {
            return Err(super::super::status::INVALID_PARAMETER);
        }
        let path = unsafe { path::from_wide(file_name) }?;
        let (handle, info) = unsafe { runtime(file_system) }?.open(&path, create_options)?;
        unsafe {
            write_handle(file_context, handle)?;
            file_info.write(info);
        }
        Ok(())
    })
}

pub(in crate::windows_vfs::winfsp) unsafe extern "C" fn overwrite(
    file_system: *mut FSP_FILE_SYSTEM,
    file_context: PVOID,
    _file_attributes: UINT32,
    _replace_file_attributes: BOOLEAN,
    _allocation_size: UINT64,
    file_info: *mut FSP_FSCTL_FILE_INFO,
) -> NTSTATUS {
    guard(|| {
        if file_info.is_null() {
            return Err(super::super::status::INVALID_PARAMETER);
        }
        let info = unsafe { runtime(file_system) }?.overwrite(unsafe { handle(file_context) }?)?;
        unsafe { file_info.write(info) };
        Ok(())
    })
}

pub(in crate::windows_vfs::winfsp) unsafe extern "C" fn cleanup(
    file_system: *mut FSP_FILE_SYSTEM,
    file_context: PVOID,
    _file_name: PWSTR,
    flags: ULONG,
) {
    guard_void(|| {
        if flags & FspCleanupDelete as u32 != 0 {
            let result = unsafe { runtime(file_system) }.and_then(|runtime| {
                unsafe { handle(file_context) }.and_then(|h| runtime.delete(h))
            });
            let _ = result;
        }
    });
}

pub(in crate::windows_vfs::winfsp) unsafe extern "C" fn close(
    _file_system: *mut FSP_FILE_SYSTEM,
    file_context: PVOID,
) {
    guard_void(|| {
        if !file_context.is_null() {
            drop(unsafe {
                Box::from_raw(file_context.cast::<std::sync::Arc<super::super::runtime::Handle>>())
            });
        }
    });
}

pub(in crate::windows_vfs::winfsp) unsafe extern "C" fn rename(
    file_system: *mut FSP_FILE_SYSTEM,
    _file_context: PVOID,
    file_name: PWSTR,
    new_file_name: PWSTR,
    replace_if_exists: BOOLEAN,
) -> NTSTATUS {
    guard(|| {
        let source = unsafe { path::from_wide(file_name) }?;
        let destination = unsafe { path::from_wide(new_file_name) }?;
        unsafe { runtime(file_system) }?.rename(&source, &destination, replace_if_exists != 0)
    })
}

pub(in crate::windows_vfs::winfsp) unsafe extern "C" fn set_delete(
    file_system: *mut FSP_FILE_SYSTEM,
    file_context: PVOID,
    _file_name: PWSTR,
    delete_file: BOOLEAN,
) -> NTSTATUS {
    guard(|| {
        if delete_file != 0 {
            unsafe { runtime(file_system) }?.can_delete(unsafe { handle(file_context) }?)?;
        }
        Ok(())
    })
}
