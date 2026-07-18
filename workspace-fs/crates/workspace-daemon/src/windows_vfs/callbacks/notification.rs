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
        if runtime.is_scratch(&source) {
            return Ok(());
        }
        if notification == PRJ_NOTIFICATION_FILE_HANDLE_CLOSED_FILE_DELETED {
            runtime.remove_resident(&source).map_err(|_| E_FAIL)?;
        } else if notification == PRJ_NOTIFICATION_FILE_RENAMED {
            let destination = wide(destination)?;
            runtime
                .rename_resident(&source, &destination)
                .map_err(|_| E_FAIL)?;
        } else if notification == PRJ_NOTIFICATION_NEW_FILE_CREATED {
            if is_directory {
                runtime
                    .create_resident_directory(&source)
                    .map_err(|_| E_FAIL)?;
            } else {
                runtime.mark_temporary(&source).map_err(|_| E_FAIL)?;
            }
        } else if notification == PRJ_NOTIFICATION_FILE_HANDLE_CLOSED_FILE_MODIFIED {
            if is_directory {
                return Ok(());
            }
            runtime.absorb_native_file(&source).map_err(|_| E_FAIL)?;
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
