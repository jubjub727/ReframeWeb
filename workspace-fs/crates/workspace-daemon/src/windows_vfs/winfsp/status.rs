use winfsp_wrs_sys::NTSTATUS;

pub const SUCCESS: NTSTATUS = 0;
pub const BUFFER_OVERFLOW: NTSTATUS = 0x8000_0005_u32 as i32;
pub const END_OF_FILE: NTSTATUS = 0xC000_0011_u32 as i32;
pub const INVALID_PARAMETER: NTSTATUS = 0xC000_000D_u32 as i32;
pub const INVALID_DEVICE_REQUEST: NTSTATUS = 0xC000_0010_u32 as i32;
pub const ACCESS_DENIED: NTSTATUS = 0xC000_0022_u32 as i32;
pub const OBJECT_NAME_NOT_FOUND: NTSTATUS = 0xC000_0034_u32 as i32;
pub const OBJECT_NAME_COLLISION: NTSTATUS = 0xC000_0035_u32 as i32;
pub const OBJECT_PATH_NOT_FOUND: NTSTATUS = 0xC000_003A_u32 as i32;
pub const FILE_IS_A_DIRECTORY: NTSTATUS = 0xC000_00BA_u32 as i32;
pub const INTERNAL_ERROR: NTSTATUS = 0xC000_00E5_u32 as i32;
pub const DIRECTORY_NOT_EMPTY: NTSTATUS = 0xC000_0101_u32 as i32;
pub const NOT_A_DIRECTORY: NTSTATUS = 0xC000_0103_u32 as i32;

pub fn mutation(error: anyhow::Error) -> NTSTATUS {
    let message = format!("{error:#}");
    if message.contains("scratch") {
        ACCESS_DENIED
    } else if message.contains("destination already exists") {
        OBJECT_NAME_COLLISION
    } else if message.contains("file over a directory") {
        FILE_IS_A_DIRECTORY
    } else if message.contains("directory over a file") {
        NOT_A_DIRECTORY
    } else if message.contains("destination directory is not empty") {
        DIRECTORY_NOT_EMPTY
    } else if message.contains("does not exist") || message.contains("source does not exist") {
        OBJECT_NAME_NOT_FOUND
    } else {
        INTERNAL_ERROR
    }
}
