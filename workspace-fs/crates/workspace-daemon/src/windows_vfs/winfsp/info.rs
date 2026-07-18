use std::mem::size_of;

use winfsp_wrs_sys::{FSP_FSCTL_DIR_INFO, FSP_FSCTL_FILE_INFO, FSP_FSCTL_VOLUME_INFO};

const DIRECTORY: u32 = 0x10;
const ARCHIVE: u32 = 0x20;
const TEMPORARY: u32 = 0x100;
const ALLOCATION_UNIT: u64 = 4096;

pub(super) fn file(
    path: &str,
    is_directory: bool,
    size: u64,
    timestamp: u64,
) -> FSP_FSCTL_FILE_INFO {
    FSP_FSCTL_FILE_INFO {
        FileAttributes: if is_directory {
            DIRECTORY
        } else {
            ARCHIVE | TEMPORARY
        },
        AllocationSize: size.div_ceil(ALLOCATION_UNIT) * ALLOCATION_UNIT,
        FileSize: size,
        CreationTime: timestamp,
        LastAccessTime: timestamp,
        LastWriteTime: timestamp,
        ChangeTime: timestamp,
        IndexNumber: index_number(path),
        HardLinks: 1,
        ..Default::default()
    }
}

pub(super) fn volume(used: u64) -> FSP_FSCTL_VOLUME_INFO {
    const CAPACITY: u64 = 1 << 40;
    let label: Vec<u16> = "Reframe RAM".encode_utf16().collect();
    let total = CAPACITY.max(used.saturating_mul(2));
    let mut info = FSP_FSCTL_VOLUME_INFO {
        TotalSize: total,
        FreeSize: total.saturating_sub(used),
        VolumeLabelLength: (label.len() * size_of::<u16>()) as u16,
        ..Default::default()
    };
    info.VolumeLabel[..label.len()].copy_from_slice(&label);
    info
}

#[repr(C)]
pub(super) struct DirectoryInfo {
    size: u16,
    align_padding: [u8; 6],
    file_info: FSP_FSCTL_FILE_INFO,
    union_padding: [u8; 24],
    file_name: [u16; 255],
}

impl DirectoryInfo {
    pub(super) fn new(name: &str, file_info: FSP_FSCTL_FILE_INFO) -> Option<Self> {
        let name = name.encode_utf16().collect::<Vec<_>>();
        if name.len() > 255 {
            return None;
        }
        let mut file_name = [0; 255];
        file_name[..name.len()].copy_from_slice(&name);
        Some(Self {
            size: (size_of::<FSP_FSCTL_DIR_INFO>() + name.len() * size_of::<u16>()) as u16,
            align_padding: [0; 6],
            file_info,
            union_padding: [0; 24],
            file_name,
        })
    }

    pub(super) fn raw(&mut self) -> *mut FSP_FSCTL_DIR_INFO {
        std::ptr::from_mut(self).cast()
    }
}

fn index_number(path: &str) -> u64 {
    let hash = blake3::hash(path.as_bytes());
    u64::from_le_bytes(hash.as_bytes()[..8].try_into().expect("fixed digest size"))
}

const _: () = assert!(std::mem::offset_of!(DirectoryInfo, file_info) == 8);
const _: () = assert!(std::mem::offset_of!(DirectoryInfo, file_name) == 104);

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn dir_info_has_winfsp_layout_and_utf16_size() {
        let mut info = DirectoryInfo::new("a.rs", file("a.rs", false, 7, 1)).unwrap();
        let raw = unsafe { &*info.raw() };
        assert_eq!(raw.Size as usize, size_of::<FSP_FSCTL_DIR_INFO>() + 8);
        assert_eq!(raw.FileInfo.FileSize, 7);
    }
}
