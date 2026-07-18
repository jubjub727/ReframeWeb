use std::os::windows::ffi::OsStrExt;
use std::path::{Path, PathBuf};
use std::sync::{Arc, OnceLock};

use anyhow::{Context, Result, bail};
use windows::Win32::System::LibraryLoader::LoadLibraryW;
use windows::core::PCWSTR;
use winfsp_wrs_sys::{
    FSP_FILE_SYSTEM, FSP_FILE_SYSTEM_INTERFACE,
    FSP_FILE_SYSTEM_OPERATION_GUARD_STRATEGY_FSP_FILE_SYSTEM_OPERATION_GUARD_STRATEGY_FINE,
    FSP_FSCTL_VOLUME_PARAMS, FspFileSystemCreate, FspFileSystemDelete,
    FspFileSystemRemoveMountPoint, FspFileSystemSetMountPoint,
    FspFileSystemSetOperationGuardStrategyF, FspFileSystemStartDispatcher,
    FspFileSystemStopDispatcher,
};

use crate::resident::ResidentWorkspace;

use super::callbacks;
use super::runtime::Runtime;
use super::security;
use super::status;
use super::version;

pub(super) struct Host {
    file_system: *mut FSP_FILE_SYSTEM,
    runtime: Box<Runtime>,
    _interface: Box<FSP_FILE_SYSTEM_INTERFACE>,
    mount_path: PathBuf,
    running: bool,
}

// WinFsp owns dispatcher threads and synchronizes callbacks before StopDispatcher returns.
unsafe impl Send for Host {}

impl Host {
    pub(super) fn start(_worktree: &Path, resident: Arc<ResidentWorkspace>) -> Result<Self> {
        initialize_dll()?;
        version::require_safe_runtime()?;
        security::default_descriptor()?;
        let runtime = Box::new(Runtime::new(resident));
        let interface = Box::new(interface());
        let params = volume_params();
        let mut file_system = std::ptr::null_mut();
        let mut device = wide_null("WinFsp.Disk");
        let status = unsafe {
            FspFileSystemCreate(device.as_mut_ptr(), &params, &*interface, &mut file_system)
        };
        check(status, "create WinFsp filesystem")?;
        if file_system.is_null() {
            bail!("WinFsp returned a null filesystem");
        }
        unsafe {
            (*file_system).UserContext = (&*runtime as *const Runtime).cast_mut().cast();
            FspFileSystemSetOperationGuardStrategyF(
                file_system,
                FSP_FILE_SYSTEM_OPERATION_GUARD_STRATEGY_FSP_FILE_SYSTEM_OPERATION_GUARD_STRATEGY_FINE,
            );
        }
        // Directory mount points require Mount Manager privileges on stock
        // WinFsp installations. A null mount point asks WinFsp for the next
        // available drive letter and works for an ordinary desktop user.
        let status = unsafe { FspFileSystemSetMountPoint(file_system, std::ptr::null_mut()) };
        if let Err(error) = check(status, "set WinFsp mount point") {
            unsafe {
                FspFileSystemRemoveMountPoint(file_system);
                FspFileSystemDelete(file_system);
            }
            return Err(error);
        }
        let mount_path = match unsafe { mounted_path(file_system) } {
            Ok(path) => path,
            Err(error) => {
                unsafe {
                    FspFileSystemRemoveMountPoint(file_system);
                    FspFileSystemDelete(file_system);
                }
                return Err(error);
            }
        };
        // Set this before dispatcher startup so an immediately-stopped
        // dispatcher cannot race with us and leave a dead mount marked live.
        runtime.set_mounted(true);
        let status = unsafe { FspFileSystemStartDispatcher(file_system, 0) };
        if let Err(error) = check(status, "start WinFsp dispatcher") {
            runtime.set_mounted(false);
            unsafe {
                FspFileSystemRemoveMountPoint(file_system);
                FspFileSystemDelete(file_system);
            }
            return Err(error);
        }
        Ok(Self {
            file_system,
            runtime,
            _interface: interface,
            mount_path,
            running: true,
        })
    }

    pub(super) fn stop(&mut self) {
        if !self.running {
            return;
        }
        unsafe {
            FspFileSystemStopDispatcher(self.file_system);
            FspFileSystemRemoveMountPoint(self.file_system);
            FspFileSystemDelete(self.file_system);
        }
        self.runtime.set_mounted(false);
        self.file_system = std::ptr::null_mut();
        self.running = false;
    }

    pub(super) fn is_running(&self) -> bool {
        self.running && self.runtime.is_mounted()
    }

    pub(super) fn mount_path(&self) -> &Path {
        &self.mount_path
    }
}

impl Drop for Host {
    fn drop(&mut self) {
        self.stop();
    }
}

fn interface() -> FSP_FILE_SYSTEM_INTERFACE {
    FSP_FILE_SYSTEM_INTERFACE {
        GetVolumeInfo: Some(callbacks::get_volume_info),
        GetSecurityByName: Some(callbacks::get_security_by_name),
        Create: Some(callbacks::create),
        Open: Some(callbacks::open),
        Overwrite: Some(callbacks::overwrite),
        Cleanup: Some(callbacks::cleanup),
        Close: Some(callbacks::close),
        Read: Some(callbacks::read),
        Write: Some(callbacks::write),
        Flush: Some(callbacks::flush),
        GetFileInfo: Some(callbacks::get_file_info),
        SetBasicInfo: Some(callbacks::set_basic_info),
        SetFileSize: Some(callbacks::set_file_size),
        Rename: Some(callbacks::rename),
        ReadDirectory: Some(callbacks::read_directory),
        SetDelete: Some(callbacks::set_delete),
        DispatcherStopped: Some(callbacks::dispatcher_stopped),
        ..Default::default()
    }
}

fn volume_params() -> FSP_FSCTL_VOLUME_PARAMS {
    let mut params = FSP_FSCTL_VOLUME_PARAMS {
        Version: std::mem::size_of::<FSP_FSCTL_VOLUME_PARAMS>() as u16,
        SectorSize: 512,
        SectorsPerAllocationUnit: 8,
        MaxComponentLength: 255,
        VolumeCreationTime: filetime_now(),
        VolumeSerialNumber: 0x5246_524D,
        FileInfoTimeout: 60_000,
        DirInfoTimeout: 60_000,
        VolumeInfoTimeout: 60_000,
        ..Default::default()
    };
    params.set_CaseSensitiveSearch(1);
    params.set_CasePreservedNames(1);
    params.set_UnicodeOnDisk(1);
    params.set_PostCleanupWhenModifiedOnly(1);
    params.set_UmFileContextIsUserContext2(1);
    let name: Vec<u16> = "ReframeRam".encode_utf16().collect();
    params.FileSystemName[..name.len()].copy_from_slice(&name);
    params
}

fn initialize_dll() -> Result<()> {
    static INITIALIZED: OnceLock<Result<(), String>> = OnceLock::new();
    INITIALIZED
        .get_or_init(|| {
            let candidates = dll_candidates();
            for path in &candidates {
                let wide: Vec<u16> = path.as_os_str().encode_wide().chain([0]).collect();
                if unsafe { LoadLibraryW(PCWSTR::from_raw(wide.as_ptr())) }.is_ok() {
                    return Ok(());
                }
            }
            Err(format!(
                "WinFsp runtime DLL was not found in {} candidate locations",
                candidates.len()
            ))
        })
        .clone()
        .map_err(anyhow::Error::msg)
        .context("initialize WinFsp runtime")
}

fn dll_candidates() -> Vec<PathBuf> {
    let Some(program_files) = std::env::var_os("ProgramFiles(x86)") else {
        return Vec::new();
    };
    let install = PathBuf::from(program_files).join("WinFsp");
    let dll = if cfg!(target_arch = "x86_64") {
        "winfsp-x64.dll"
    } else if cfg!(target_arch = "x86") {
        "winfsp-x86.dll"
    } else {
        "winfsp-a64.dll"
    };
    let mut candidates = vec![install.join("bin").join(dll)];
    if let Ok(entries) = std::fs::read_dir(install.join("SxS")) {
        let mut side_by_side = entries
            .filter_map(Result::ok)
            .map(|entry| entry.path().join("bin").join(dll))
            .collect::<Vec<_>>();
        side_by_side.sort();
        side_by_side.reverse();
        candidates.extend(side_by_side);
    }
    candidates
}

fn check(code: i32, operation: &str) -> Result<()> {
    if code == status::SUCCESS {
        Ok(())
    } else {
        bail!("{operation} failed with NTSTATUS 0x{:08X}", code as u32)
    }
}

fn wide_null(value: &str) -> Vec<u16> {
    value.encode_utf16().chain([0]).collect()
}

unsafe fn mounted_path(file_system: *mut FSP_FILE_SYSTEM) -> Result<PathBuf> {
    let raw = unsafe { (*file_system).MountPoint };
    if raw.is_null() {
        bail!("WinFsp did not report its selected mount point");
    }
    let mut length = 0usize;
    while unsafe { *raw.add(length) } != 0 {
        length += 1;
    }
    let value = String::from_utf16(unsafe { std::slice::from_raw_parts(raw, length) })
        .context("decode the WinFsp mount point")?;
    Ok(PathBuf::from(format!("{value}\\")))
}

fn filetime_now() -> u64 {
    const WINDOWS_TO_UNIX_SECONDS: u64 = 11_644_473_600;
    let unix = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .unwrap_or_default();
    (unix.as_secs() + WINDOWS_TO_UNIX_SECONDS) * 10_000_000 + u64::from(unix.subsec_nanos() / 100)
}
