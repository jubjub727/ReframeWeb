use super::*;

pub unsafe extern "system" fn get_placeholder(data: *const PRJ_CALLBACK_DATA) -> HRESULT {
    guard("get_placeholder_info", || {
        let runtime = runtime(data)?;
        let callback = unsafe { &*data };
        let path = wide(callback.FilePathName)?;
        let (is_directory, size, content_hash) = match runtime.file(&path) {
            Some(file) => (false, file.bytes.len() as u64, Some(file.hash)),
            None if runtime.exists(&path) => (true, 0, None),
            None => return Err(HRESULT::from_win32(ERROR_FILE_NOT_FOUND.0)),
        };
        let mut placeholder = PRJ_PLACEHOLDER_INFO {
            FileBasicInfo: basic_info(is_directory, size),
            ..Default::default()
        };
        let content = content_hash
            .map(|hash| blake3::hash(hash.as_bytes()))
            .unwrap_or_else(|| blake3::hash(path.as_bytes()));
        placeholder.VersionInfo.ProviderID[..16].copy_from_slice(&[0x52; 16]);
        placeholder.VersionInfo.ContentID[..32].copy_from_slice(content.as_bytes());
        unsafe {
            PrjWritePlaceholderInfo(
                callback.NamespaceVirtualizationContext,
                callback.FilePathName,
                &placeholder,
                size_of::<PRJ_PLACEHOLDER_INFO>() as u32,
            )
        }
        .map_err(|error| error.code())
    })
}

pub unsafe extern "system" fn get_file_data(
    data: *const PRJ_CALLBACK_DATA,
    offset: u64,
    length: u32,
) -> HRESULT {
    guard("get_file_data", || {
        let runtime = runtime(data)?;
        let callback = unsafe { &*data };
        let path = wide(callback.FilePathName)?;
        let file = runtime
            .file(&path)
            .ok_or(HRESULT::from_win32(ERROR_FILE_NOT_FOUND.0))?;
        let bytes = file.bytes;
        let start = usize::try_from(offset).map_err(|_| E_INVALIDARG)?;
        let requested = usize::try_from(length).map_err(|_| E_INVALIDARG)?;
        if start > bytes.len() {
            return Err(E_INVALIDARG);
        }
        let end = start.saturating_add(requested).min(bytes.len());
        let data = &bytes[start..end];
        if data.is_empty() {
            return Ok(());
        }
        let buffer = unsafe {
            PrjAllocateAlignedBuffer(callback.NamespaceVirtualizationContext, data.len())
        };
        if buffer.is_null() {
            return Err(E_FAIL);
        }
        unsafe {
            ptr::copy_nonoverlapping(data.as_ptr(), buffer.cast(), data.len());
        }
        let result = unsafe {
            PrjWriteFileData(
                callback.NamespaceVirtualizationContext,
                &callback.DataStreamId,
                buffer,
                offset,
                data.len() as u32,
            )
        }
        .map_err(|error| error.code());
        unsafe {
            PrjFreeAlignedBuffer(buffer);
        }
        result
    })
}

pub unsafe extern "system" fn query_file_name(data: *const PRJ_CALLBACK_DATA) -> HRESULT {
    guard("query_file_name", || {
        let callback = unsafe { &*data };
        if runtime(data)?.exists(&wide(callback.FilePathName)?) {
            Ok(())
        } else {
            Err(HRESULT::from_win32(ERROR_FILE_NOT_FOUND.0))
        }
    })
}
