use std::fmt;

use thiserror::Error;

use super::violation::CompatibilityViolation;

/// Complete, deterministically ordered set of breaking Store contract changes.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct CompatibilityIssues {
    violations: Vec<CompatibilityViolation>,
}

impl CompatibilityIssues {
    pub(super) const fn new(violations: Vec<CompatibilityViolation>) -> Self {
        Self { violations }
    }

    #[must_use]
    pub const fn is_empty(&self) -> bool {
        self.violations.is_empty()
    }

    #[must_use]
    pub fn violations(&self) -> &[CompatibilityViolation] {
        &self.violations
    }

    #[must_use]
    pub fn into_violations(self) -> Vec<CompatibilityViolation> {
        self.violations
    }
}

impl fmt::Display for CompatibilityIssues {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        writeln!(
            formatter,
            "candidate Store interface has {} breaking change(s):",
            self.violations.len()
        )?;
        for violation in &self.violations {
            writeln!(formatter, "- {violation}")?;
        }
        Ok(())
    }
}

impl std::error::Error for CompatibilityIssues {}

/// Package identity/scope failure or Store contract compatibility failure.
#[derive(Debug, Clone, PartialEq, Eq, Error)]
#[non_exhaustive]
pub enum CompatibilityError {
    #[error("cannot compare different Stores: previous={previous:?}, candidate={candidate:?}")]
    StoreIdMismatch { previous: String, candidate: String },
    #[error(
        "compatibility checks require one interface major: previous={previous}, candidate={candidate}"
    )]
    InterfaceMajorMismatch { previous: u32, candidate: u32 },
    #[error("candidate interface minor regressed from {previous} to {candidate}")]
    InterfaceMinorRegression { previous: u32, candidate: u32 },
    #[error("minimum generic protocol major changed from {previous} to {candidate}")]
    MinimumProtocolMajorChanged { previous: u32, candidate: u32 },
    #[error("candidate minimum generic protocol minor increased from {previous} to {candidate}")]
    MinimumProtocolMinorIncreased { previous: u32, candidate: u32 },
    #[error(transparent)]
    BreakingChanges(#[from] CompatibilityIssues),
}
