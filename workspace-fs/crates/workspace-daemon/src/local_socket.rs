#[cfg(unix)]
#[path = "local_socket/unix.rs"]
mod platform;

#[cfg(windows)]
#[path = "local_socket/windows.rs"]
mod platform;

pub use platform::{LocalListener, StoreLock};

#[cfg(test)]
#[path = "local_socket/tests.rs"]
mod tests;
