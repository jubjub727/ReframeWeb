use super::*;

pub unsafe extern "system" fn notification(
    data: *const PRJ_CALLBACK_DATA,
    is_directory: bool,
    notification: PRJ_NOTIFICATION,
    destination: PCWSTR,
    _parameters: *mut PRJ_NOTIFICATION_PARAMETERS,
) -> HRESULT {
    guard("notification", || {
        let callback = unsafe { &*data };
        let source = wide(callback.FilePathName)?;
        let runtime = runtime(data)?;
        if notification == PRJ_NOTIFICATION_PRE_SET_HARDLINK {
            return Err(HRESULT::from_win32(ERROR_NOT_SUPPORTED.0));
        }
        if notification == PRJ_NOTIFICATION_PRE_RENAME {
            let destination = wide(destination)?;
            if source.is_empty()
                || destination.is_empty()
                || runtime.is_scratch(&source) != runtime.is_scratch(&destination)
            {
                return Err(HRESULT::from_win32(ERROR_NOT_SAME_DEVICE.0));
            }
            return Ok(());
        }
        if runtime.is_scratch(&source) {
            return Ok(());
        }
        if notification == PRJ_NOTIFICATION_FILE_HANDLE_CLOSED_FILE_DELETED {
            runtime
                .remove_resident(&source)
                .map_err(|error| callback_error("remove resident path", &error))?;
        } else if notification == PRJ_NOTIFICATION_FILE_RENAMED {
            let destination = wide(destination)?;
            runtime
                .rename_resident(&source, &destination)
                .map_err(|error| callback_error("rename resident path", &error))?;
        } else if notification == PRJ_NOTIFICATION_NEW_FILE_CREATED {
            if is_directory {
                runtime
                    .create_resident_directory(&source)
                    .map_err(|error| callback_error("create resident directory", &error))?;
            } else {
                runtime
                    .mark_temporary(&source)
                    .map_err(|error| callback_error("mark projected file temporary", &error))?;
            }
        } else if notification == PRJ_NOTIFICATION_FILE_HANDLE_CLOSED_FILE_MODIFIED {
            if is_directory {
                return Ok(());
            }
            runtime
                .absorb_native_file(&source)
                .map_err(|error| callback_error("absorb projected file", &error))?;
            let flags = PRJ_UPDATE_ALLOW_DIRTY_DATA
                | PRJ_UPDATE_ALLOW_DIRTY_METADATA
                | PRJ_UPDATE_ALLOW_READ_ONLY
                | PRJ_UPDATE_ALLOW_TOMBSTONE;
            unsafe {
                PrjDeleteFile(
                    callback.NamespaceVirtualizationContext,
                    callback.FilePathName,
                    Some(flags),
                    None,
                )
            }
            .map_err(|error| error.code())?;
        }
        Ok(())
    })
}
