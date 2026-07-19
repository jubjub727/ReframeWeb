#[cfg(unix)]
#[path = "local/unix.rs"]
mod platform;
#[cfg(windows)]
#[path = "local/windows.rs"]
mod platform;
#[cfg(windows)]
#[path = "local/windows_security.rs"]
mod windows_security;

/// Default deadline for establishing a local connection.
pub const DEFAULT_CONNECT_TIMEOUT: std::time::Duration = std::time::Duration::from_secs(5);

pub use platform::{LocalListener, LocalStream, connect, connect_with_timeout};
