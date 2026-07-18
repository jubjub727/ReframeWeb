use std::mem::size_of;
use std::panic::{AssertUnwindSafe, catch_unwind};
use std::ptr;

use windows::Win32::Foundation::{
    E_FAIL, E_INVALIDARG, ERROR_FILE_NOT_FOUND, ERROR_INSUFFICIENT_BUFFER, ERROR_NOT_SAME_DEVICE,
    ERROR_NOT_SUPPORTED, S_OK,
};
use windows::Win32::Storage::ProjectedFileSystem::*;
use windows::core::{GUID, HRESULT, PCWSTR};

use super::runtime::{Enumeration, Runtime};

mod enumeration;
mod hydration;
mod notification;
mod support;

pub use enumeration::{end_enumeration, get_enumeration, start_enumeration};
pub use hydration::{get_file_data, get_placeholder, query_file_name};
pub use notification::notification;
use support::*;
