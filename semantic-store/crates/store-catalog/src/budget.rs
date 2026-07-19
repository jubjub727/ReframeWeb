use prost::Message;

use crate::{
    CatalogError, DEFAULT_INSPECTION_BYTE_BUDGET, DEFAULT_LIST_BYTE_BUDGET,
    MAX_INSPECTION_BYTE_BUDGET,
};

pub(crate) fn list_budget(value: u32) -> Result<usize, CatalogError> {
    budget_or_default(value, DEFAULT_LIST_BYTE_BUDGET)
}

pub(crate) fn inspection_budget(value: u32) -> Result<usize, CatalogError> {
    let budget = budget_or_default(value, DEFAULT_INSPECTION_BYTE_BUDGET)?;
    if budget > MAX_INSPECTION_BYTE_BUDGET {
        return Err(CatalogError::InvalidBudget { budget: value });
    }
    Ok(budget)
}

fn budget_or_default(value: u32, default: usize) -> Result<usize, CatalogError> {
    if value == 0 {
        return Ok(default);
    }
    usize::try_from(value).map_err(|_| CatalogError::InvalidBudget { budget: value })
}

/// Bounds the owned protobuf data created while projecting descriptor graphs.
///
/// Charging both encoded bytes and the Rust node itself prevents a wide shared
/// descriptor graph from multiplying small wire nodes into unbounded host-side
/// allocations before the exact response budget is checked. The node charge
/// also conservatively covers parent length delimiters and collection storage,
/// keeping the final exact-fit pass small.
pub(crate) struct ProjectionBudget {
    remaining: usize,
}

impl ProjectionBudget {
    pub(crate) const fn new(limit: usize) -> Self {
        Self { remaining: limit }
    }

    pub(crate) fn claim<M: Message>(&mut self, node: &M) -> bool {
        let work = node
            .encoded_len()
            .saturating_add(std::mem::size_of_val(node))
            .max(1);
        let Some(remaining) = self.remaining.checked_sub(work) else {
            self.remaining = 0;
            return false;
        };
        self.remaining = remaining;
        true
    }

    #[must_use]
    pub(crate) const fn exhausted(&self) -> bool {
        self.remaining == 0
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn inspection_budget_rejects_values_above_the_host_safe_ceiling() {
        let too_large = u32::try_from(MAX_INSPECTION_BYTE_BUDGET + 1).expect("small ceiling");
        assert_eq!(
            inspection_budget(too_large),
            Err(CatalogError::InvalidBudget { budget: too_large })
        );
        assert_eq!(inspection_budget(0), Ok(DEFAULT_INSPECTION_BYTE_BUDGET));
        let maximum = u32::try_from(MAX_INSPECTION_BYTE_BUDGET).expect("small ceiling");
        assert_eq!(inspection_budget(maximum), Ok(MAX_INSPECTION_BYTE_BUDGET));
    }
}
