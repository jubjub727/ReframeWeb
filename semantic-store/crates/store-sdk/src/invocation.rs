use crate::{BufferedInvocation, GuestError, PullInvocation};

/// A WIT-ready invocation backed by either buffered events or retained state.
#[derive(Debug)]
pub enum Invocation {
    Buffered(BufferedInvocation),
    Pull(PullInvocation),
}

impl Invocation {
    /// Returns one encoded event per WIT `invocation.next` call.
    pub fn next(&self) -> Result<Option<Vec<u8>>, GuestError> {
        match self {
            Self::Buffered(invocation) => invocation.next().map_err(GuestError::from),
            Self::Pull(invocation) => invocation.next(),
        }
    }
}

impl From<BufferedInvocation> for Invocation {
    fn from(value: BufferedInvocation) -> Self {
        Self::Buffered(value)
    }
}

impl From<PullInvocation> for Invocation {
    fn from(value: PullInvocation) -> Self {
        Self::Pull(value)
    }
}
