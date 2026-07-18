use std::fs::File;
use std::os::unix::fs::FileExt;
use std::sync::{Arc, Mutex};

use fuser::{Errno, INodeNo, OpenAccMode, OpenFlags};

use super::super::error::io_errno;

#[derive(Clone, Copy)]
pub(in crate::unix_vfs) struct OpenAccess {
    readable: bool,
    writable: bool,
}

impl OpenAccess {
    pub(in crate::unix_vfs) fn from_flags(flags: OpenFlags) -> Self {
        match flags.acc_mode() {
            OpenAccMode::O_RDONLY => Self {
                readable: true,
                writable: false,
            },
            OpenAccMode::O_WRONLY => Self {
                readable: false,
                writable: true,
            },
            OpenAccMode::O_RDWR => Self {
                readable: true,
                writable: true,
            },
        }
    }

    pub(in crate::unix_vfs) fn readable(self) -> bool {
        self.readable
    }

    pub(in crate::unix_vfs) fn writable(self) -> bool {
        self.writable
    }
}

#[derive(Clone)]
pub(in crate::unix_vfs) struct OpenHandle {
    inode: INodeNo,
    access: OpenAccess,
    backend: OpenBackend,
}

#[derive(Clone)]
enum OpenBackend {
    Resident(SharedResidentFile),
    Scratch(Arc<File>),
}

pub(super) type SharedResidentFile = Arc<Mutex<ResidentFileState>>;

pub(super) struct ResidentFileState {
    location: ResidentLocation,
}

enum ResidentLocation {
    Linked(String),
    Detached(Vec<u8>),
}

impl OpenHandle {
    pub(super) fn resident(inode: INodeNo, access: OpenAccess, file: SharedResidentFile) -> Self {
        Self {
            inode,
            access,
            backend: OpenBackend::Resident(file),
        }
    }

    pub(super) fn scratch(inode: INodeNo, access: OpenAccess, file: File) -> Self {
        Self {
            inode,
            access,
            backend: OpenBackend::Scratch(Arc::new(file)),
        }
    }

    pub(in crate::unix_vfs) fn inode(&self) -> INodeNo {
        self.inode
    }

    pub(in crate::unix_vfs) fn read<F>(
        &self,
        offset: u64,
        size: u32,
        read_linked: F,
    ) -> Result<Vec<u8>, Errno>
    where
        F: FnOnce(&str) -> Result<Vec<u8>, Errno>,
    {
        if !self.access.readable {
            return Err(Errno::EBADF);
        }
        match &self.backend {
            OpenBackend::Scratch(file) => read_scratch(file, offset, size),
            OpenBackend::Resident(file) => {
                let file = file.lock().map_err(|_| Errno::EIO)?;
                match &file.location {
                    ResidentLocation::Linked(path) => {
                        slice_bytes(&read_linked(path)?, offset, size)
                    }
                    ResidentLocation::Detached(bytes) => slice_bytes(bytes, offset, size),
                }
            }
        }
    }

    pub(in crate::unix_vfs) fn write<F>(
        &self,
        offset: u64,
        data: &[u8],
        write_linked: F,
    ) -> Result<(), Errno>
    where
        F: FnOnce(&str, u64, &[u8]) -> Result<(), Errno>,
    {
        if !self.access.writable {
            return Err(Errno::EBADF);
        }
        match &self.backend {
            OpenBackend::Scratch(file) => write_scratch(file, offset, data),
            OpenBackend::Resident(file) => {
                let mut file = file.lock().map_err(|_| Errno::EIO)?;
                match &mut file.location {
                    ResidentLocation::Linked(path) => write_linked(path, offset, data),
                    ResidentLocation::Detached(bytes) => write_bytes(bytes, offset, data),
                }
            }
        }
    }

    pub(in crate::unix_vfs) fn resize<F>(&self, size: u64, resize_linked: F) -> Result<(), Errno>
    where
        F: FnOnce(&str, u64) -> Result<(), Errno>,
    {
        if !self.access.writable {
            return Err(Errno::EBADF);
        }
        match &self.backend {
            OpenBackend::Scratch(file) => file.set_len(size).map_err(|error| io_errno(&error)),
            OpenBackend::Resident(file) => {
                let mut file = file.lock().map_err(|_| Errno::EIO)?;
                match &mut file.location {
                    ResidentLocation::Linked(path) => resize_linked(path, size),
                    ResidentLocation::Detached(bytes) => {
                        bytes.resize(usize::try_from(size).map_err(|_| Errno::EFBIG)?, 0);
                        Ok(())
                    }
                }
            }
        }
    }

    pub(in crate::unix_vfs) fn len<F>(&self, linked_len: F) -> Result<u64, Errno>
    where
        F: FnOnce(&str) -> Result<u64, Errno>,
    {
        match &self.backend {
            OpenBackend::Scratch(file) => file
                .metadata()
                .map(|metadata| metadata.len())
                .map_err(|error| io_errno(&error)),
            OpenBackend::Resident(file) => {
                let file = file.lock().map_err(|_| Errno::EIO)?;
                match &file.location {
                    ResidentLocation::Linked(path) => linked_len(path),
                    ResidentLocation::Detached(bytes) => Ok(bytes.len() as u64),
                }
            }
        }
    }

    pub(in crate::unix_vfs) fn sync(&self, data_only: bool) -> Result<(), Errno> {
        match &self.backend {
            OpenBackend::Scratch(file) if data_only => {
                file.sync_data().map_err(|error| io_errno(&error))
            }
            OpenBackend::Scratch(file) => file.sync_all().map_err(|error| io_errno(&error)),
            OpenBackend::Resident(_) => Ok(()),
        }
    }
}

impl ResidentFileState {
    pub(super) fn linked(path: String) -> Self {
        Self {
            location: ResidentLocation::Linked(path),
        }
    }

    pub(super) fn linked_path(&self) -> Option<&str> {
        match &self.location {
            ResidentLocation::Linked(path) => Some(path),
            ResidentLocation::Detached(_) => None,
        }
    }

    pub(super) fn detach(&mut self, bytes: Vec<u8>) {
        self.location = ResidentLocation::Detached(bytes);
    }

    pub(super) fn relink(&mut self, path: String) {
        self.location = ResidentLocation::Linked(path);
    }
}

fn slice_bytes(bytes: &[u8], offset: u64, size: u32) -> Result<Vec<u8>, Errno> {
    let start = usize::try_from(offset).map_err(|_| Errno::EINVAL)?;
    if start >= bytes.len() {
        return Ok(Vec::new());
    }
    let end = start.saturating_add(size as usize).min(bytes.len());
    Ok(bytes[start..end].to_vec())
}

fn read_scratch(file: &File, offset: u64, size: u32) -> Result<Vec<u8>, Errno> {
    let mut bytes = vec![0; size as usize];
    let read = file
        .read_at(&mut bytes, offset)
        .map_err(|error| io_errno(&error))?;
    bytes.truncate(read);
    Ok(bytes)
}

fn write_scratch(file: &File, mut offset: u64, mut data: &[u8]) -> Result<(), Errno> {
    while !data.is_empty() {
        let written = file
            .write_at(data, offset)
            .map_err(|error| io_errno(&error))?;
        if written == 0 {
            return Err(Errno::EIO);
        }
        offset = offset.checked_add(written as u64).ok_or(Errno::EFBIG)?;
        data = &data[written..];
    }
    Ok(())
}

fn write_bytes(bytes: &mut Vec<u8>, offset: u64, data: &[u8]) -> Result<(), Errno> {
    let offset = usize::try_from(offset).map_err(|_| Errno::EFBIG)?;
    let end = offset.checked_add(data.len()).ok_or(Errno::EFBIG)?;
    if bytes.len() < offset {
        bytes.resize(offset, 0);
    }
    if bytes.len() < end {
        bytes.resize(end, 0);
    }
    bytes[offset..end].copy_from_slice(data);
    Ok(())
}
