use std::time::Duration;

use thiserror::Error;

const DEFAULT_MAX_SESSIONS: usize = 1_024;
const DEFAULT_MAX_INVOCATIONS_PER_SESSION: usize = 128;
const DEFAULT_MAX_ACTIVE_INVOCATIONS: usize = 1_024;
const DEFAULT_COMPLETION_HISTORY: usize = 1_024;
const DEFAULT_SEND_TIMEOUT: Duration = Duration::from_secs(30);
const DEFAULT_SHUTDOWN_TIMEOUT: Duration = Duration::from_secs(30);
// Leaves framing headroom under the default 8 MiB local transport limit.
const DEFAULT_MAX_COMPONENT_EVENT_BYTES: usize = 7 * 1024 * 1024;
const MAX_SESSIONS: usize = 1_000_000;
const MAX_INVOCATIONS_PER_SESSION: usize = 65_536;
const MAX_ACTIVE_INVOCATIONS: usize = 1_000_000;
const MAX_COMPLETION_HISTORY: usize = 65_536;
const MAX_COMPONENT_EVENT_BYTES: usize = 64 * 1024 * 1024;

/// Bounded host lifecycle settings independent of Store business data.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct RuntimeConfig {
    max_sessions: usize,
    max_invocations_per_session: usize,
    max_active_invocations: usize,
    completion_history: usize,
    send_timeout: Duration,
    shutdown_timeout: Duration,
    max_component_event_bytes: usize,
}

impl RuntimeConfig {
    #[must_use]
    pub const fn max_sessions(&self) -> usize {
        self.max_sessions
    }

    #[must_use]
    pub const fn max_invocations_per_session(&self) -> usize {
        self.max_invocations_per_session
    }

    #[must_use]
    pub const fn max_active_invocations(&self) -> usize {
        self.max_active_invocations
    }

    #[must_use]
    pub const fn completion_history(&self) -> usize {
        self.completion_history
    }

    #[must_use]
    pub const fn send_timeout(&self) -> Duration {
        self.send_timeout
    }

    #[must_use]
    pub const fn shutdown_timeout(&self) -> Duration {
        self.shutdown_timeout
    }

    #[must_use]
    pub const fn max_component_event_bytes(&self) -> usize {
        self.max_component_event_bytes
    }

    pub fn with_max_sessions(mut self, value: usize) -> Result<Self, RuntimeConfigError> {
        require_bounded("max_sessions", value, MAX_SESSIONS)?;
        self.max_sessions = value;
        Ok(self)
    }

    pub fn with_max_invocations_per_session(
        mut self,
        value: usize,
    ) -> Result<Self, RuntimeConfigError> {
        require_bounded(
            "max_invocations_per_session",
            value,
            MAX_INVOCATIONS_PER_SESSION,
        )?;
        self.max_invocations_per_session = value;
        Ok(self)
    }

    pub fn with_max_active_invocations(mut self, value: usize) -> Result<Self, RuntimeConfigError> {
        require_bounded(
            "max_active_invocations",
            value,
            MAX_ACTIVE_INVOCATIONS.min(tokio::sync::Semaphore::MAX_PERMITS),
        )?;
        self.max_active_invocations = value;
        Ok(self)
    }

    pub fn with_completion_history(mut self, value: usize) -> Result<Self, RuntimeConfigError> {
        require_bounded("completion_history", value, MAX_COMPLETION_HISTORY)?;
        self.completion_history = value;
        Ok(self)
    }

    pub fn with_send_timeout(mut self, value: Duration) -> Result<Self, RuntimeConfigError> {
        require_timeout("send_timeout", value)?;
        self.send_timeout = value;
        Ok(self)
    }

    pub fn with_shutdown_timeout(mut self, value: Duration) -> Result<Self, RuntimeConfigError> {
        require_timeout("shutdown_timeout", value)?;
        self.shutdown_timeout = value;
        Ok(self)
    }

    pub fn with_max_component_event_bytes(
        mut self,
        value: usize,
    ) -> Result<Self, RuntimeConfigError> {
        require_bounded(
            "max_component_event_bytes",
            value,
            MAX_COMPONENT_EVENT_BYTES,
        )?;
        self.max_component_event_bytes = value;
        Ok(self)
    }
}

impl Default for RuntimeConfig {
    fn default() -> Self {
        Self {
            max_sessions: DEFAULT_MAX_SESSIONS,
            max_invocations_per_session: DEFAULT_MAX_INVOCATIONS_PER_SESSION,
            max_active_invocations: DEFAULT_MAX_ACTIVE_INVOCATIONS,
            completion_history: DEFAULT_COMPLETION_HISTORY,
            send_timeout: DEFAULT_SEND_TIMEOUT,
            shutdown_timeout: DEFAULT_SHUTDOWN_TIMEOUT,
            max_component_event_bytes: DEFAULT_MAX_COMPONENT_EVENT_BYTES,
        }
    }
}

fn require_bounded(
    field: &'static str,
    value: usize,
    maximum: usize,
) -> Result<(), RuntimeConfigError> {
    if value == 0 {
        Err(RuntimeConfigError::Zero { field })
    } else if value > maximum {
        Err(RuntimeConfigError::TooLarge { field, maximum })
    } else {
        Ok(())
    }
}

fn require_timeout(field: &'static str, value: Duration) -> Result<(), RuntimeConfigError> {
    if value.is_zero() {
        Err(RuntimeConfigError::Zero { field })
    } else if std::time::Instant::now().checked_add(value).is_none() {
        Err(RuntimeConfigError::TimeoutOutOfRange { field })
    } else {
        Ok(())
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Error)]
pub enum RuntimeConfigError {
    #[error("runtime setting {field} must be non-zero")]
    Zero { field: &'static str },
    #[error("runtime setting {field} must not exceed {maximum}")]
    TooLarge { field: &'static str, maximum: usize },
    #[error("runtime setting {field} does not fit the platform monotonic clock")]
    TimeoutOutOfRange { field: &'static str },
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn rejects_unbounded_zeroes() {
        assert!(RuntimeConfig::default().with_max_sessions(0).is_err());
        assert!(
            RuntimeConfig::default()
                .with_max_active_invocations(0)
                .is_err()
        );
        assert!(
            RuntimeConfig::default()
                .with_send_timeout(Duration::ZERO)
                .is_err()
        );
        assert!(
            RuntimeConfig::default()
                .with_shutdown_timeout(Duration::ZERO)
                .is_err()
        );
    }

    #[test]
    fn rejects_values_that_could_panic_or_preallocate_without_bound() {
        assert!(
            RuntimeConfig::default()
                .with_max_active_invocations(usize::MAX)
                .is_err()
        );
        assert!(
            RuntimeConfig::default()
                .with_completion_history(usize::MAX)
                .is_err()
        );
        assert!(
            RuntimeConfig::default()
                .with_max_sessions(usize::MAX)
                .is_err()
        );
    }
}
