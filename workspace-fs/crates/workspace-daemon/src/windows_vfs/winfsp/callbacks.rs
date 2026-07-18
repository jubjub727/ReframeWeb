mod directory;
mod io;
mod metadata;
mod namespace;

use std::panic::{AssertUnwindSafe, catch_unwind};
use std::sync::Arc;
use std::sync::OnceLock;

use winfsp_wrs_sys::{FSP_FILE_SYSTEM, NTSTATUS, PVOID};

use super::runtime::{Handle, Runtime};
use super::status;

pub(super) use directory::read_directory;
pub(super) use io::{flush, read, set_file_size, write};
pub(super) use metadata::{get_file_info, get_security_by_name, get_volume_info, set_basic_info};
pub(super) use namespace::{cleanup, close, create, open, overwrite, rename, set_delete};

pub(super) unsafe extern "C" fn dispatcher_stopped(
    file_system: *mut FSP_FILE_SYSTEM,
    _normally: winfsp_wrs_sys::BOOLEAN,
) {
    guard_void(|| {
        if let Ok(runtime) = unsafe { runtime(file_system) } {
            runtime.set_mounted(false);
        }
    });
}

pub(super) unsafe fn runtime<'a>(
    file_system: *mut FSP_FILE_SYSTEM,
) -> Result<&'a Runtime, NTSTATUS> {
    if file_system.is_null() {
        return Err(status::INVALID_PARAMETER);
    }
    let context = unsafe { (*file_system).UserContext.cast::<Runtime>() };
    if context.is_null() {
        return Err(status::INTERNAL_ERROR);
    }
    Ok(unsafe { &*context })
}

pub(super) unsafe fn handle<'a>(file_context: PVOID) -> Result<&'a Arc<Handle>, NTSTATUS> {
    if file_context.is_null() {
        return Err(status::INVALID_PARAMETER);
    }
    Ok(unsafe { &*file_context.cast::<Arc<Handle>>() })
}

pub(super) unsafe fn write_handle(target: *mut PVOID, handle: Arc<Handle>) -> Result<(), NTSTATUS> {
    if target.is_null() {
        return Err(status::INVALID_PARAMETER);
    }
    unsafe { target.write(Box::into_raw(Box::new(handle)).cast()) };
    Ok(())
}

pub(super) fn guard(operation: impl FnOnce() -> Result<(), NTSTATUS>) -> NTSTATUS {
    match catch_unwind(AssertUnwindSafe(operation)) {
        Ok(Ok(())) => status::SUCCESS,
        Ok(Err(status)) => {
            debug_failure(format_args!(
                "callback returned NTSTATUS 0x{:08X}",
                status as u32
            ));
            status
        }
        Err(_) => {
            debug_failure(format_args!("callback panicked"));
            status::INTERNAL_ERROR
        }
    }
}

pub(super) fn guard_void(operation: impl FnOnce()) {
    if catch_unwind(AssertUnwindSafe(operation)).is_err() {
        debug_failure(format_args!("void callback panicked"));
    }
}

fn debug_failure(message: std::fmt::Arguments<'_>) {
    static ENABLED: OnceLock<bool> = OnceLock::new();
    if *ENABLED.get_or_init(|| std::env::var_os("REFRAME_WORKSPACE_WINFSP_DEBUG").is_some()) {
        eprintln!("[winfsp] {message}");
    }
}
