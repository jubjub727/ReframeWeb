use std::mem::size_of;
use std::panic::{AssertUnwindSafe, catch_unwind};
use std::ptr;

use windows::Win32::Foundation::{
    E_FAIL, E_INVALIDARG, ERROR_FILE_NOT_FOUND, ERROR_INSUFFICIENT_BUFFER, S_OK,
};
use windows::Win32::Storage::ProjectedFileSystem::*;
use windows::core::{GUID, HRESULT, PCWSTR};

use super::runtime::{Enumeration, Runtime};

include!("callbacks/enumeration.rs");
include!("callbacks/hydration.rs");
include!("callbacks/notification.rs");
include!("callbacks/support.rs");
