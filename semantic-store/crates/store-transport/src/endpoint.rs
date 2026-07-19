#[cfg(unix)]
#[path = "endpoint/unix_runtime.rs"]
mod unix_runtime;

use std::fmt;

use crate::EndpointError;

pub const DEFAULT_SERVICE_NAME: &str = "reframe-semantic-store";

#[cfg(any(unix, test))]
const PORTABLE_UNIX_SOCKET_PATH_CAPACITY: usize = 103;

/// Platform-local address for one Semantic Store host.
#[derive(Clone, Debug)]
pub struct LocalEndpoint {
    #[cfg(unix)]
    path: std::path::PathBuf,
    #[cfg(unix)]
    managed_parent: bool,
    #[cfg(windows)]
    pipe_name: String,
}

impl PartialEq for LocalEndpoint {
    fn eq(&self, other: &Self) -> bool {
        #[cfg(unix)]
        {
            self.path == other.path
        }
        #[cfg(windows)]
        {
            self.pipe_name.eq_ignore_ascii_case(&other.pipe_name)
        }
    }
}

impl Eq for LocalEndpoint {}

impl std::hash::Hash for LocalEndpoint {
    fn hash<H: std::hash::Hasher>(&self, state: &mut H) {
        #[cfg(unix)]
        self.path.hash(state);
        #[cfg(windows)]
        self.pipe_name.to_ascii_lowercase().hash(state);
    }
}

impl LocalEndpoint {
    /// Builds a deterministic endpoint from a stable service name.
    ///
    /// Names are normalized to ASCII lowercase so Windows and Unix agree on
    /// identity. Use a distinct name when intentionally running multiple hosts.
    pub fn for_service(service_name: &str) -> Result<Self, EndpointError> {
        validate_service_name(service_name)?;
        let normalized = service_name.to_ascii_lowercase();
        #[cfg(unix)]
        let endpoint = Self {
            path: unix_runtime::default_endpoint_path(&normalized),
            managed_parent: true,
        };
        #[cfg(windows)]
        let endpoint = Self {
            pipe_name: format!(r"\\.\pipe\{normalized}"),
        };
        Ok(endpoint)
    }

    #[cfg(unix)]
    pub fn from_path(path: impl Into<std::path::PathBuf>) -> Result<Self, EndpointError> {
        use std::os::unix::ffi::OsStrExt as _;

        let path = path.into();
        if path.as_os_str().as_bytes().contains(&0) {
            return Err(EndpointError::InteriorNul);
        }
        Ok(Self {
            path,
            managed_parent: false,
        })
    }

    #[cfg(unix)]
    #[must_use]
    pub fn as_path(&self) -> &std::path::Path {
        &self.path
    }

    #[cfg(unix)]
    pub(crate) fn prepare_parent(&self) -> std::io::Result<()> {
        if !self.managed_parent {
            return Ok(());
        }
        unix_runtime::ensure_private_directory(
            self.path
                .parent()
                .expect("managed endpoint always has a parent"),
        )
    }

    #[cfg(windows)]
    pub fn from_pipe_name(pipe_name: impl Into<String>) -> Result<Self, EndpointError> {
        let pipe_name = pipe_name.into();
        let local_prefix = r"\\.\pipe\";
        if !pipe_name
            .get(..local_prefix.len())
            .is_some_and(|prefix| prefix.eq_ignore_ascii_case(local_prefix))
            || pipe_name.len() == local_prefix.len()
        {
            return Err(EndpointError::InvalidPipeName);
        }
        Ok(Self { pipe_name })
    }

    #[cfg(windows)]
    #[must_use]
    pub fn as_pipe_name(&self) -> &str {
        &self.pipe_name
    }
}

impl Default for LocalEndpoint {
    fn default() -> Self {
        Self::for_service(DEFAULT_SERVICE_NAME).expect("default service name is valid")
    }
}

impl fmt::Display for LocalEndpoint {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        #[cfg(unix)]
        {
            self.path.display().fmt(formatter)
        }
        #[cfg(windows)]
        {
            self.pipe_name.fmt(formatter)
        }
    }
}

fn validate_service_name(service_name: &str) -> Result<(), EndpointError> {
    let valid = (1..=64).contains(&service_name.len())
        && service_name
            .bytes()
            .all(|byte| byte.is_ascii_alphanumeric() || matches!(byte, b'.' | b'_' | b'-'));
    if valid {
        Ok(())
    } else {
        Err(EndpointError::InvalidServiceName)
    }
}

#[cfg(any(unix, test))]
fn managed_socket_relative_path(user_id: u32, normalized_service_name: &str) -> String {
    use sha2::{Digest as _, Sha256};
    use std::fmt::Write as _;

    let digest = Sha256::digest(normalized_service_name.as_bytes());
    let mut filename = String::with_capacity(2 + digest.len() * 2 + 5);
    filename.push_str("s-");
    for byte in digest {
        write!(filename, "{byte:02x}").expect("writing to a string cannot fail");
    }
    filename.push_str(".sock");
    format!("rfs-{user_id}/{filename}")
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn service_names_are_stable_and_case_normalized() {
        assert_eq!(
            LocalEndpoint::for_service("Reframe-Test").unwrap(),
            LocalEndpoint::for_service("reframe-test").unwrap()
        );
    }

    #[test]
    fn service_names_cannot_escape_the_endpoint_namespace() {
        assert!(LocalEndpoint::for_service("").is_err());
        assert!(LocalEndpoint::for_service("../host").is_err());
        assert!(LocalEndpoint::for_service("name with spaces").is_err());
    }

    #[test]
    fn managed_unix_names_are_portable_and_collision_resistant() {
        let longest_name = "a".repeat(64);
        let first = managed_socket_relative_path(u32::MAX, &longest_name);
        let repeated = managed_socket_relative_path(u32::MAX, &longest_name);
        let different = managed_socket_relative_path(u32::MAX, &format!("b{}", &longest_name[1..]));

        assert_eq!(first, repeated);
        assert_ne!(first, different);
        assert!(format!("/tmp/{first}").len() <= PORTABLE_UNIX_SOCKET_PATH_CAPACITY);
        assert_eq!(first.len(), different.len());
    }

    #[cfg(unix)]
    #[test]
    fn managed_runtime_directory_is_private() {
        use std::os::unix::fs::PermissionsExt as _;

        let parent = tempfile::tempdir().unwrap();
        let runtime = parent.path().join("runtime");
        unix_runtime::ensure_private_directory(&runtime).unwrap();
        assert_eq!(
            std::fs::metadata(runtime).unwrap().permissions().mode() & 0o777,
            0o700
        );
    }
}
