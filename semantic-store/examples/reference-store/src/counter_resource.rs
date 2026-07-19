use crate::{
    error::ResourceError,
    model::{CounterSample, CounterSelector},
};

const MAX_SAMPLES: u32 = 32;
const MAX_LABEL_BYTES: usize = 64;

pub(crate) struct CounterSeries {
    label: String,
    next_index: u32,
    total: u32,
}

impl CounterSeries {
    pub(crate) fn new(selector: &CounterSelector) -> Result<Self, ResourceError> {
        if !(1..=MAX_SAMPLES).contains(&selector.sample_count) {
            return Err(ResourceError::InvalidInput(format!(
                "sample_count must be between 1 and {MAX_SAMPLES}"
            )));
        }
        let label = selector.label.trim();
        if label.is_empty() || label.len() > MAX_LABEL_BYTES {
            return Err(ResourceError::InvalidInput(format!(
                "label must contain 1 to {MAX_LABEL_BYTES} UTF-8 bytes"
            )));
        }
        Ok(Self {
            label: label.to_owned(),
            next_index: 0,
            total: selector.sample_count,
        })
    }

    pub(crate) fn next_sample(&mut self) -> Option<CounterSample> {
        if self.next_index == self.total {
            return None;
        }
        let sample = CounterSample {
            index: self.next_index,
            label: self.label.clone(),
        };
        self.next_index += 1;
        Some(sample)
    }

    pub(crate) const fn produced(&self) -> u32 {
        self.next_index
    }

    pub(crate) const fn total(&self) -> u32 {
        self.total
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn counter_is_bounded_deterministic_and_incremental() {
        let mut values = CounterSeries::new(&CounterSelector {
            sample_count: 3,
            label: " tick ".to_owned(),
        })
        .unwrap();

        assert_eq!(values.produced(), 0);
        assert_eq!(values.next_sample().unwrap().index, 0);
        assert_eq!(values.produced(), 1);
        assert_eq!(values.next_sample().unwrap().label, "tick");
        assert_eq!(values.next_sample().unwrap().index, 2);
        assert!(values.next_sample().is_none());
    }
}
