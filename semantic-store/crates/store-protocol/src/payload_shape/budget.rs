use super::{PayloadShapeError, ProtobufShapeBudget, RepeatedFieldLimit};

pub(super) struct ValueBudget {
    pub(super) maximum_depth: usize,
    remaining: usize,
    remaining_messages: usize,
    repeated_field_limits: &'static [RepeatedFieldLimit],
    repeated_counts: Vec<usize>,
}

impl ValueBudget {
    pub(super) fn new(limits: ProtobufShapeBudget) -> Self {
        Self {
            maximum_depth: limits.maximum_depth,
            remaining: limits.maximum_values,
            remaining_messages: limits.maximum_messages,
            repeated_field_limits: limits.repeated_field_limits,
            repeated_counts: Vec::new(),
        }
    }

    pub(super) fn consume(&mut self, count: usize) -> Result<(), PayloadShapeError> {
        self.remaining = self
            .remaining
            .checked_sub(count)
            .ok_or(PayloadShapeError::ValueLimit)?;
        Ok(())
    }

    pub(super) fn consume_message(&mut self) -> Result<(), PayloadShapeError> {
        self.remaining_messages = self
            .remaining_messages
            .checked_sub(1)
            .ok_or(PayloadShapeError::MessageLimit)?;
        Ok(())
    }

    pub(super) fn enter_message(&mut self) -> usize {
        let base = self.repeated_counts.len();
        self.repeated_counts
            .resize(base + self.repeated_field_limits.len(), 0);
        base
    }

    pub(super) fn leave_message(&mut self, base: usize) {
        self.repeated_counts.truncate(base);
    }

    pub(super) fn consume_repeated(
        &mut self,
        message_name: &str,
        field_number: u32,
        count_base: usize,
        count: usize,
    ) -> Result<(), PayloadShapeError> {
        for (index, limit) in self.repeated_field_limits.iter().enumerate() {
            if limit.message_full_name != message_name || limit.field_number != field_number {
                continue;
            }
            let observed = &mut self.repeated_counts[count_base + index];
            *observed = observed
                .checked_add(count)
                .ok_or(PayloadShapeError::RepeatedFieldLimit)?;
            if *observed > limit.maximum_values {
                return Err(PayloadShapeError::RepeatedFieldLimit);
            }
        }
        Ok(())
    }
}

#[derive(Clone, Copy)]
pub(super) struct FieldLocation<'a> {
    pub(super) message_name: &'a str,
    pub(super) count_base: usize,
}
