use crate::ConfigError;
use std::time::Duration;

/// Default maximum encoded envelope size: 8 MiB.
pub const DEFAULT_MAX_FRAME_SIZE: usize = 8 * 1024 * 1024;
/// Hard maximum encoded envelope size: 64 MiB.
pub const MAX_FRAME_SIZE: usize = 64 * 1024 * 1024;
/// Default number of envelopes allowed to wait for the writer.
pub const DEFAULT_OUTBOUND_CAPACITY: usize = 64;
/// Default aggregate encoded-payload budget for one connection: 8 MiB.
pub const DEFAULT_OUTBOUND_BYTE_BUDGET: usize = DEFAULT_MAX_FRAME_SIZE;
/// Default aggregate encoded-payload budget shared by all connections.
pub const DEFAULT_AGGREGATE_OUTBOUND_BYTE_BUDGET: usize = MAX_FRAME_SIZE;
/// Default aggregate request-admission budget shared by all connections.
///
/// Each admitted request reserves one configured maximum frame, allowing
/// eight worst-case handlers with the default 8 MiB frame limit.
pub const DEFAULT_INBOUND_BYTE_BUDGET: usize = MAX_FRAME_SIZE;
/// Default number of handlers running for one connection.
pub const DEFAULT_MAX_IN_FLIGHT: usize = 64;
/// Default number of simultaneously active local connections.
pub const DEFAULT_MAX_CONNECTIONS: usize = 128;
/// Hard ceiling for queued outbound envelopes per connection.
pub const MAX_OUTBOUND_CAPACITY: usize = 4_096;
/// Hard ceiling for concurrent handlers per connection.
pub const MAX_IN_FLIGHT: usize = 4_096;
/// Hard ceiling for simultaneously active local connections.
pub const MAX_CONNECTIONS: usize = 4_096;
/// Time allowed to finish a frame after its first byte arrives.
pub const DEFAULT_READ_TIMEOUT: Duration = Duration::from_secs(30);
/// Time allowed for one complete frame write or stream shutdown.
pub const DEFAULT_WRITE_TIMEOUT: Duration = Duration::from_secs(30);
/// Time allowed for already-dispatched handlers to finish during shutdown.
pub const DEFAULT_HANDLER_DRAIN_TIMEOUT: Duration = Duration::from_secs(30);

/// Resource and framing limits for the local transport.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct TransportConfig {
    max_frame_size: usize,
    outbound_capacity: usize,
    outbound_byte_budget: usize,
    aggregate_outbound_byte_budget: usize,
    inbound_byte_budget: usize,
    max_in_flight: usize,
    max_connections: usize,
    read_timeout: Duration,
    write_timeout: Duration,
    handler_drain_timeout: Duration,
}

impl TransportConfig {
    pub fn new(
        max_frame_size: usize,
        outbound_capacity: usize,
        max_in_flight: usize,
        max_connections: usize,
    ) -> Result<Self, ConfigError> {
        validate_max_frame_size(max_frame_size)?;
        validate_outbound_capacity(outbound_capacity)?;
        validate_max_in_flight(max_in_flight)?;
        validate_max_connections(max_connections)?;
        Ok(Self {
            max_frame_size,
            outbound_capacity,
            outbound_byte_budget: max_frame_size,
            aggregate_outbound_byte_budget: DEFAULT_AGGREGATE_OUTBOUND_BYTE_BUDGET,
            inbound_byte_budget: DEFAULT_INBOUND_BYTE_BUDGET,
            max_in_flight,
            max_connections,
            read_timeout: DEFAULT_READ_TIMEOUT,
            write_timeout: DEFAULT_WRITE_TIMEOUT,
            handler_drain_timeout: DEFAULT_HANDLER_DRAIN_TIMEOUT,
        })
    }

    #[must_use]
    pub const fn max_frame_size(&self) -> usize {
        self.max_frame_size
    }

    #[must_use]
    pub const fn outbound_capacity(&self) -> usize {
        self.outbound_capacity
    }

    /// Maximum aggregate encoded payload bytes retained by the outbound queue
    /// and its active writer.
    #[must_use]
    pub const fn outbound_byte_budget(&self) -> usize {
        self.outbound_byte_budget
    }

    /// Aggregate encoded-payload budget shared by every connection in one
    /// server while retaining the per-connection budget for fairness.
    #[must_use]
    pub const fn aggregate_outbound_byte_budget(&self) -> usize {
        self.aggregate_outbound_byte_budget
    }

    /// Aggregate admission budget shared by every connection in one server.
    /// Each request holds `max_frame_size()` bytes from this budget until its
    /// handler finishes, bounding both inbound allocation and response
    /// construction concurrency.
    #[must_use]
    pub const fn inbound_byte_budget(&self) -> usize {
        self.inbound_byte_budget
    }

    #[must_use]
    pub const fn max_in_flight(&self) -> usize {
        self.max_in_flight
    }

    #[must_use]
    pub const fn max_connections(&self) -> usize {
        self.max_connections
    }

    #[must_use]
    pub const fn read_timeout(&self) -> Duration {
        self.read_timeout
    }

    #[must_use]
    pub const fn write_timeout(&self) -> Duration {
        self.write_timeout
    }

    #[must_use]
    pub const fn handler_drain_timeout(&self) -> Duration {
        self.handler_drain_timeout
    }

    pub fn with_max_frame_size(mut self, value: usize) -> Result<Self, ConfigError> {
        validate_max_frame_size(value)?;
        self.max_frame_size = value;
        self.outbound_byte_budget = self.outbound_byte_budget.max(value);
        self.aggregate_outbound_byte_budget = self.aggregate_outbound_byte_budget.max(value);
        self.inbound_byte_budget = self.inbound_byte_budget.max(value);
        Ok(self)
    }

    pub fn with_outbound_capacity(mut self, value: usize) -> Result<Self, ConfigError> {
        validate_outbound_capacity(value)?;
        self.outbound_capacity = value;
        Ok(self)
    }

    /// Sets the aggregate encoded-payload budget for each connection.
    ///
    /// The budget must accommodate one maximum-size frame, ensuring every
    /// otherwise valid response can make progress.
    pub fn with_outbound_byte_budget(mut self, value: usize) -> Result<Self, ConfigError> {
        validate_outbound_byte_budget(value, self.max_frame_size)?;
        self.outbound_byte_budget = value;
        Ok(self)
    }

    /// Sets the aggregate encoded-payload budget shared by a local server.
    pub fn with_aggregate_outbound_byte_budget(
        mut self,
        value: usize,
    ) -> Result<Self, ConfigError> {
        validate_aggregate_outbound_byte_budget(value, self.max_frame_size)?;
        self.aggregate_outbound_byte_budget = value;
        Ok(self)
    }

    /// Sets the aggregate request-admission budget shared by a local server.
    ///
    /// The budget must accommodate at least one configured maximum frame.
    pub fn with_inbound_byte_budget(mut self, value: usize) -> Result<Self, ConfigError> {
        validate_inbound_byte_budget(value, self.max_frame_size)?;
        self.inbound_byte_budget = value;
        Ok(self)
    }

    pub fn with_max_in_flight(mut self, value: usize) -> Result<Self, ConfigError> {
        validate_max_in_flight(value)?;
        self.max_in_flight = value;
        Ok(self)
    }

    pub fn with_max_connections(mut self, value: usize) -> Result<Self, ConfigError> {
        validate_max_connections(value)?;
        self.max_connections = value;
        Ok(self)
    }

    pub fn with_read_timeout(mut self, value: Duration) -> Result<Self, ConfigError> {
        validate_timeout("read timeout", value)?;
        self.read_timeout = value;
        Ok(self)
    }

    pub fn with_write_timeout(mut self, value: Duration) -> Result<Self, ConfigError> {
        validate_timeout("write timeout", value)?;
        self.write_timeout = value;
        Ok(self)
    }

    pub fn with_handler_drain_timeout(mut self, value: Duration) -> Result<Self, ConfigError> {
        validate_timeout("handler drain timeout", value)?;
        self.handler_drain_timeout = value;
        Ok(self)
    }
}

impl Default for TransportConfig {
    fn default() -> Self {
        Self {
            max_frame_size: DEFAULT_MAX_FRAME_SIZE,
            outbound_capacity: DEFAULT_OUTBOUND_CAPACITY,
            outbound_byte_budget: DEFAULT_OUTBOUND_BYTE_BUDGET,
            aggregate_outbound_byte_budget: DEFAULT_AGGREGATE_OUTBOUND_BYTE_BUDGET,
            inbound_byte_budget: DEFAULT_INBOUND_BYTE_BUDGET,
            max_in_flight: DEFAULT_MAX_IN_FLIGHT,
            max_connections: DEFAULT_MAX_CONNECTIONS,
            read_timeout: DEFAULT_READ_TIMEOUT,
            write_timeout: DEFAULT_WRITE_TIMEOUT,
            handler_drain_timeout: DEFAULT_HANDLER_DRAIN_TIMEOUT,
        }
    }
}

fn validate_timeout(name: &'static str, value: Duration) -> Result<(), ConfigError> {
    if value.is_zero() || std::time::Instant::now().checked_add(value).is_none() {
        Err(ConfigError::Timeout { name })
    } else {
        Ok(())
    }
}

fn validate_max_frame_size(value: usize) -> Result<(), ConfigError> {
    let maximum = MAX_FRAME_SIZE.min(tokio::sync::Semaphore::MAX_PERMITS);
    if value == 0 || value > maximum {
        Err(ConfigError::MaxFrameSize {
            actual: value,
            maximum,
        })
    } else {
        Ok(())
    }
}

fn validate_inbound_byte_budget(value: usize, minimum: usize) -> Result<(), ConfigError> {
    if value < minimum || value > tokio::sync::Semaphore::MAX_PERMITS {
        Err(ConfigError::InboundByteBudget {
            actual: value,
            minimum,
            maximum: tokio::sync::Semaphore::MAX_PERMITS,
        })
    } else {
        Ok(())
    }
}

fn validate_aggregate_outbound_byte_budget(
    value: usize,
    minimum: usize,
) -> Result<(), ConfigError> {
    if value < minimum || value > tokio::sync::Semaphore::MAX_PERMITS {
        Err(ConfigError::AggregateOutboundByteBudget {
            actual: value,
            minimum,
            maximum: tokio::sync::Semaphore::MAX_PERMITS,
        })
    } else {
        Ok(())
    }
}

fn validate_outbound_capacity(value: usize) -> Result<(), ConfigError> {
    if !(1..=MAX_OUTBOUND_CAPACITY).contains(&value) {
        Err(ConfigError::OutboundCapacity {
            actual: value,
            maximum: MAX_OUTBOUND_CAPACITY,
        })
    } else {
        Ok(())
    }
}

fn validate_max_in_flight(value: usize) -> Result<(), ConfigError> {
    if !(1..=MAX_IN_FLIGHT).contains(&value) {
        Err(ConfigError::MaxInFlight {
            actual: value,
            maximum: MAX_IN_FLIGHT,
        })
    } else {
        Ok(())
    }
}

fn validate_max_connections(value: usize) -> Result<(), ConfigError> {
    if !(1..=MAX_CONNECTIONS).contains(&value) {
        Err(ConfigError::MaxConnections {
            actual: value,
            maximum: MAX_CONNECTIONS,
        })
    } else {
        Ok(())
    }
}

fn validate_outbound_byte_budget(value: usize, minimum: usize) -> Result<(), ConfigError> {
    if value < minimum || value > tokio::sync::Semaphore::MAX_PERMITS {
        Err(ConfigError::OutboundByteBudget {
            actual: value,
            minimum,
            maximum: tokio::sync::Semaphore::MAX_PERMITS,
        })
    } else {
        Ok(())
    }
}

#[cfg(test)]
mod tests;
