/// Process-local owner of protocol sessions created through an external
/// connection. The value is an identity, not a credential.
#[derive(Clone, Copy, Debug, Eq, Hash, PartialEq)]
pub struct SessionOwner(u64);

impl SessionOwner {
    #[must_use]
    pub const fn new(value: u64) -> Self {
        Self(value)
    }
}
