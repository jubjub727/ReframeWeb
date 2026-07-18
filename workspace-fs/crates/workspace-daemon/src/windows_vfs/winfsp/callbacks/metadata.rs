use winfsp_wrs_sys::{
    FSP_FILE_SYSTEM, FSP_FSCTL_FILE_INFO, FSP_FSCTL_VOLUME_INFO, NTSTATUS, PSECURITY_DESCRIPTOR,
    PUINT32, PVOID, PWSTR, SIZE_T, UINT32, UINT64,
};

use super::{guard, handle, runtime};
use crate::windows_vfs::winfsp::path;

pub(in crate::windows_vfs::winfsp) unsafe extern "C" fn get_volume_info(
    file_system: *mut FSP_FILE_SYSTEM,
    volume_info: *mut FSP_FSCTL_VOLUME_INFO,
) -> NTSTATUS {
    guard(|| {
        if volume_info.is_null() {
            return Err(super::super::status::INVALID_PARAMETER);
        }
        unsafe { volume_info.write(runtime(file_system)?.volume_info()) };
        Ok(())
    })
}

pub(in crate::windows_vfs::winfsp) unsafe extern "C" fn get_security_by_name(
    file_system: *mut FSP_FILE_SYSTEM,
    file_name: PWSTR,
    file_attributes: PUINT32,
    security_descriptor: PSECURITY_DESCRIPTOR,
    security_descriptor_size: *mut SIZE_T,
) -> NTSTATUS {
    guard(|| {
        let path = unsafe { path::from_wide(file_name) }?;
        let attributes = unsafe { runtime(file_system) }?.attributes(&path)?;
        if !file_attributes.is_null() {
            unsafe { file_attributes.write(attributes) };
        }
        if !security_descriptor_size.is_null() {
            let descriptor = super::super::security::default_descriptor()
                .map_err(|_| super::super::status::INTERNAL_ERROR)?;
            let capacity = unsafe { security_descriptor_size.read() };
            let descriptor_size = descriptor.len() as SIZE_T;
            unsafe { security_descriptor_size.write(descriptor_size) };
            if descriptor_size > capacity {
                return Err(super::super::status::BUFFER_OVERFLOW);
            }
            if !security_descriptor.is_null() {
                unsafe {
                    std::ptr::copy_nonoverlapping(
                        descriptor.as_ptr(),
                        security_descriptor.cast::<u8>(),
                        descriptor.len(),
                    )
                };
            }
        }
        Ok(())
    })
}

pub(in crate::windows_vfs::winfsp) unsafe extern "C" fn get_file_info(
    file_system: *mut FSP_FILE_SYSTEM,
    file_context: PVOID,
    file_info: *mut FSP_FSCTL_FILE_INFO,
) -> NTSTATUS {
    guard(|| {
        if file_info.is_null() {
            return Err(super::super::status::INVALID_PARAMETER);
        }
        let info =
            unsafe { runtime(file_system) }?.handle_info(unsafe { handle(file_context) }?)?;
        unsafe { file_info.write(info) };
        Ok(())
    })
}

pub(in crate::windows_vfs::winfsp) unsafe extern "C" fn set_basic_info(
    _file_system: *mut FSP_FILE_SYSTEM,
    _file_context: PVOID,
    _file_attributes: UINT32,
    _creation_time: UINT64,
    _last_access_time: UINT64,
    _last_write_time: UINT64,
    _change_time: UINT64,
    _file_info: *mut FSP_FSCTL_FILE_INFO,
) -> NTSTATUS {
    super::super::status::INVALID_DEVICE_REQUEST
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn set_basic_info_rejects_unpersisted_metadata_changes() {
        let status = unsafe {
            set_basic_info(
                std::ptr::null_mut(),
                std::ptr::null_mut(),
                0,
                0,
                0,
                0,
                0,
                std::ptr::null_mut(),
            )
        };

        assert_eq!(status, super::super::super::status::INVALID_DEVICE_REQUEST);
    }
}
