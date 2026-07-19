//! Audited FFI boundary for a current-owner-only named-pipe DACL.

#![allow(unsafe_code)]

use std::ffi::{OsStr, c_void};
use std::io;
use std::os::windows::ffi::OsStrExt as _;
use std::ptr;

use tokio::net::windows::named_pipe::{NamedPipeServer, ServerOptions};
use windows_sys::Win32::Foundation::{CloseHandle, ERROR_INSUFFICIENT_BUFFER, HANDLE, LocalFree};
use windows_sys::Win32::Security::Authorization::{
    ConvertSidToStringSidW, ConvertStringSecurityDescriptorToSecurityDescriptorW, SDDL_REVISION_1,
};
use windows_sys::Win32::Security::{
    GetTokenInformation, IsValidSid, PSECURITY_DESCRIPTOR, PSID, SECURITY_ATTRIBUTES, TOKEN_QUERY,
    TOKEN_USER, TokenUser,
};
use windows_sys::Win32::System::Threading::{GetCurrentProcess, OpenProcessToken};

pub(super) fn create_current_user_only(
    options: &ServerOptions,
    pipe_name: &str,
) -> io::Result<NamedPipeServer> {
    let mut security = CurrentUserSecurity::new()?;
    // SAFETY: `attributes_ptr` points to a fully initialized
    // SECURITY_ATTRIBUTES whose descriptor remains alive for this synchronous
    // CreateNamedPipeW call. Tokio does not retain the pointer.
    unsafe { options.create_with_security_attributes_raw(pipe_name, security.attributes_ptr()) }
}

struct CurrentUserSecurity {
    descriptor: PSECURITY_DESCRIPTOR,
    attributes: SECURITY_ATTRIBUTES,
}

impl CurrentUserSecurity {
    fn new() -> io::Result<Self> {
        let user_sid = current_process_user_sid()?;
        // `O:` sets an explicit owner. `D:P` protects the DACL from inherited
        // entries, and its only ACE grants generic-all to that same user SID.
        let sddl = format!("O:{user_sid}D:P(A;;GA;;;{user_sid})");
        let encoded = OsStr::new(&sddl)
            .encode_wide()
            .chain([0])
            .collect::<Vec<_>>();
        let mut descriptor = ptr::null_mut();
        // SAFETY: `encoded` is NUL-terminated and lives through the call;
        // `descriptor` is a valid out pointer. Windows allocates the returned
        // self-relative descriptor with LocalAlloc.
        let succeeded = unsafe {
            ConvertStringSecurityDescriptorToSecurityDescriptorW(
                encoded.as_ptr(),
                SDDL_REVISION_1,
                &mut descriptor,
                ptr::null_mut(),
            )
        };
        if succeeded == 0 {
            return Err(io::Error::last_os_error());
        }
        let attributes = SECURITY_ATTRIBUTES {
            nLength: u32::try_from(size_of::<SECURITY_ATTRIBUTES>())
                .expect("SECURITY_ATTRIBUTES size fits u32"),
            lpSecurityDescriptor: descriptor,
            bInheritHandle: 0,
        };
        Ok(Self {
            descriptor,
            attributes,
        })
    }

    fn attributes_ptr(&mut self) -> *mut c_void {
        ptr::from_mut(&mut self.attributes).cast()
    }
}

fn current_process_user_sid() -> io::Result<String> {
    let token = ProcessToken::open()?;
    let mut required = 0_u32;
    // SAFETY: this documented sizing call accepts a null information buffer
    // and writes only `required`; `token` remains valid for the call.
    let sized =
        unsafe { GetTokenInformation(token.0, TokenUser, ptr::null_mut(), 0, &mut required) };
    if sized != 0 {
        return Err(io::Error::new(
            io::ErrorKind::InvalidData,
            "TokenUser sizing unexpectedly succeeded without a buffer",
        ));
    }
    let error = io::Error::last_os_error();
    if error.raw_os_error() != Some(ERROR_INSUFFICIENT_BUFFER as i32)
        || required < u32::try_from(size_of::<TOKEN_USER>()).expect("TOKEN_USER size fits u32")
    {
        return Err(error);
    }

    let mut information = vec![
        0_u8;
        usize::try_from(required).map_err(|_| {
            io::Error::new(
                io::ErrorKind::InvalidData,
                "TokenUser size does not fit usize",
            )
        })?
    ];
    // SAFETY: `information` has the exact size requested by Windows and is
    // writable for the duration of the call.
    let succeeded = unsafe {
        GetTokenInformation(
            token.0,
            TokenUser,
            information.as_mut_ptr().cast(),
            required,
            &mut required,
        )
    };
    if succeeded == 0 {
        return Err(io::Error::last_os_error());
    }
    // SAFETY: GetTokenInformation initialized at least one TOKEN_USER. An
    // unaligned read avoids assuming Vec<u8>'s allocation alignment.
    let token_user = unsafe { ptr::read_unaligned(information.as_ptr().cast::<TOKEN_USER>()) };
    if token_user.User.Sid.is_null() || unsafe { IsValidSid(token_user.User.Sid) } == 0 {
        return Err(io::Error::new(
            io::ErrorKind::InvalidData,
            "process TokenUser contains an invalid SID",
        ));
    }
    sid_to_string(token_user.User.Sid)
}

fn sid_to_string(sid: PSID) -> io::Result<String> {
    let mut encoded = ptr::null_mut();
    // SAFETY: `sid` was validated by the caller and `encoded` is a valid out
    // pointer. Windows returns a NUL-terminated LocalAlloc allocation.
    let succeeded = unsafe { ConvertSidToStringSidW(sid, &mut encoded) };
    if succeeded == 0 {
        return Err(io::Error::last_os_error());
    }
    let encoded = LocalWideString(encoded);
    let mut length = 0_usize;
    // SAFETY: ConvertSidToStringSidW guarantees a NUL-terminated string.
    while unsafe { *encoded.0.add(length) } != 0 {
        length = length.checked_add(1).ok_or_else(|| {
            io::Error::new(io::ErrorKind::InvalidData, "SID string length overflow")
        })?;
    }
    // SAFETY: the preceding scan established the initialized string length.
    String::from_utf16(unsafe { std::slice::from_raw_parts(encoded.0, length) })
        .map_err(|_| io::Error::new(io::ErrorKind::InvalidData, "SID string is not valid UTF-16"))
}

struct ProcessToken(HANDLE);

impl ProcessToken {
    fn open() -> io::Result<Self> {
        let mut token = ptr::null_mut();
        // SAFETY: GetCurrentProcess returns a valid pseudo-handle and `token`
        // is a valid out pointer.
        let succeeded = unsafe { OpenProcessToken(GetCurrentProcess(), TOKEN_QUERY, &mut token) };
        if succeeded == 0 {
            Err(io::Error::last_os_error())
        } else {
            Ok(Self(token))
        }
    }
}

impl Drop for ProcessToken {
    fn drop(&mut self) {
        // SAFETY: this is the still-owned handle returned by OpenProcessToken.
        let succeeded = unsafe { CloseHandle(self.0) };
        debug_assert_ne!(succeeded, 0, "CloseHandle unexpectedly failed");
    }
}

struct LocalWideString(*mut u16);

impl Drop for LocalWideString {
    fn drop(&mut self) {
        // SAFETY: this is the LocalAlloc allocation returned by
        // ConvertSidToStringSidW.
        let result = unsafe { LocalFree(self.0.cast()) };
        debug_assert!(result.is_null(), "LocalFree unexpectedly failed");
    }
}

impl Drop for CurrentUserSecurity {
    fn drop(&mut self) {
        // SAFETY: the descriptor is the still-owned LocalAlloc allocation
        // returned by ConvertStringSecurityDescriptorToSecurityDescriptorW.
        let result = unsafe { LocalFree(self.descriptor) };
        debug_assert!(result.is_null(), "LocalFree unexpectedly failed");
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use windows_sys::Win32::Foundation::GENERIC_ALL;
    use windows_sys::Win32::Security::{
        ACCESS_ALLOWED_ACE, GetAce, GetSecurityDescriptorControl, GetSecurityDescriptorDacl,
        GetSecurityDescriptorOwner, SE_DACL_PROTECTED,
    };

    #[test]
    fn descriptor_is_owned_and_exclusively_allowed_by_the_process_user() {
        let security = CurrentUserSecurity::new().unwrap();
        let expected_user = current_process_user_sid().unwrap();
        let mut owner = ptr::null_mut();
        let mut owner_defaulted = 0;
        // SAFETY: the descriptor is valid and all output pointers are valid.
        assert_ne!(
            unsafe {
                GetSecurityDescriptorOwner(security.descriptor, &mut owner, &mut owner_defaulted)
            },
            0
        );
        assert_eq!(sid_to_string(owner).unwrap(), expected_user);
        assert_eq!(owner_defaulted, 0);

        let mut control = 0;
        let mut revision = 0;
        // SAFETY: the descriptor is valid and all output pointers are valid.
        assert_ne!(
            unsafe {
                GetSecurityDescriptorControl(security.descriptor, &mut control, &mut revision)
            },
            0
        );
        assert_ne!(control & SE_DACL_PROTECTED, 0);

        let mut dacl_present = 0;
        let mut dacl = ptr::null_mut();
        let mut dacl_defaulted = 0;
        // SAFETY: the descriptor is valid and all output pointers are valid.
        assert_ne!(
            unsafe {
                GetSecurityDescriptorDacl(
                    security.descriptor,
                    &mut dacl_present,
                    &mut dacl,
                    &mut dacl_defaulted,
                )
            },
            0
        );
        assert_ne!(dacl_present, 0);
        assert!(!dacl.is_null());
        assert_eq!(dacl_defaulted, 0);
        // SAFETY: GetSecurityDescriptorDacl returned a valid ACL pointer.
        assert_eq!(unsafe { (*dacl).AceCount }, 1);

        let mut ace = ptr::null_mut();
        // SAFETY: the DACL has exactly one ACE and `ace` is a valid out pointer.
        assert_ne!(unsafe { GetAce(dacl, 0, &mut ace) }, 0);
        let ace = ace.cast::<ACCESS_ALLOWED_ACE>();
        // SAFETY: the SDDL created an ACCESS_ALLOWED_ACE at index zero.
        assert_eq!(unsafe { (*ace).Mask }, GENERIC_ALL);
        // SAFETY: SidStart is the documented start of the variable-size SID
        // embedded in ACCESS_ALLOWED_ACE.
        let allowed_sid = unsafe { ptr::addr_of_mut!((*ace).SidStart).cast() };
        assert_eq!(sid_to_string(allowed_sid).unwrap(), expected_user);
    }
}
