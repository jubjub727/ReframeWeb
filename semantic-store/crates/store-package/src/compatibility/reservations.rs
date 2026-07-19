pub(super) fn covers(
    ranges: impl IntoIterator<Item = (i64, i64)>,
    required_start: i64,
    required_end: i64,
) -> bool {
    if required_end <= required_start {
        return true;
    }
    let mut ranges = ranges.into_iter().collect::<Vec<_>>();
    ranges.sort_unstable();
    let mut covered_until = required_start;
    for (start, end) in ranges {
        if end <= covered_until {
            continue;
        }
        if start > covered_until {
            return false;
        }
        covered_until = end;
        if covered_until >= required_end {
            return true;
        }
    }
    false
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn accepts_merged_or_split_covering_ranges() {
        assert!(covers([(1, 3), (3, 6)], 2, 5));
        assert!(covers([(1, 6)], 2, 5));
        assert!(!covers([(1, 3), (4, 6)], 2, 5));
    }
}
