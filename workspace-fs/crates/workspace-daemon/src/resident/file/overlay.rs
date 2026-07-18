use std::collections::HashMap;

use crate::store::VerifiedBlob;

const PAGE_SIZE: usize = 4 * 1024;

pub(super) struct PagedContent {
    base: VerifiedBlob,
    pages: HashMap<usize, Box<[u8; PAGE_SIZE]>>,
    len: usize,
    base_visible_len: usize,
    digest: Option<blake3::Hash>,
}

impl PagedContent {
    pub(super) fn new(base: VerifiedBlob) -> Self {
        let len = base.bytes().len();
        Self {
            base,
            pages: HashMap::new(),
            len,
            base_visible_len: len,
            digest: None,
        }
    }

    pub(super) fn len(&self) -> usize {
        self.len
    }

    pub(super) fn copy_into(&self, offset: usize, output: &mut [u8]) -> usize {
        if offset >= self.len || output.is_empty() {
            return 0;
        }
        let count = output.len().min(self.len - offset);
        let output = &mut output[..count];
        output.fill(0);

        let base_end = offset.saturating_add(count).min(self.base_visible_len);
        if offset < base_end {
            output[..base_end - offset].copy_from_slice(&self.base.bytes()[offset..base_end]);
        }
        self.copy_pages(offset, output);
        count
    }

    pub(super) fn write(&mut self, offset: usize, data: &[u8]) {
        let end = offset + data.len();
        let mut source_offset = 0;
        while source_offset < data.len() {
            let absolute = offset + source_offset;
            let page_index = absolute / PAGE_SIZE;
            let in_page = absolute % PAGE_SIZE;
            let count = (PAGE_SIZE - in_page).min(data.len() - source_offset);
            let page = self.page_for_write(page_index);
            page[in_page..in_page + count]
                .copy_from_slice(&data[source_offset..source_offset + count]);
            source_offset += count;
        }
        self.len = self.len.max(end);
        self.digest = None;
    }

    pub(super) fn resize(&mut self, size: usize) {
        if size < self.len {
            self.base_visible_len = self.base_visible_len.min(size);
            self.pages
                .retain(|page_index, _| page_index.saturating_mul(PAGE_SIZE) < size);
            let tail = size % PAGE_SIZE;
            if tail != 0 {
                if let Some(page) = self.pages.get_mut(&(size / PAGE_SIZE)) {
                    page[tail..].fill(0);
                }
            }
        }
        self.len = size;
        self.digest = None;
    }

    pub(super) fn digest(&mut self) -> blake3::Hash {
        if let Some(digest) = self.digest {
            return digest;
        }
        let mut hasher = blake3::Hasher::new();
        let mut buffer = [0; PAGE_SIZE];
        let mut offset = 0;
        while offset < self.len {
            let count = self.copy_into(offset, &mut buffer);
            hasher.update(&buffer[..count]);
            offset += count;
        }
        let digest = hasher.finalize();
        self.digest = Some(digest);
        digest
    }

    pub(super) fn materialize(&self) -> Vec<u8> {
        let mut bytes = vec![0; self.len];
        self.copy_into(0, &mut bytes);
        bytes
    }

    #[cfg(test)]
    pub(super) fn allocated_bytes(&self) -> usize {
        self.pages.len() * PAGE_SIZE
    }

    fn page_for_write(&mut self, page_index: usize) -> &mut [u8; PAGE_SIZE] {
        self.pages.entry(page_index).or_insert_with(|| {
            let mut page = Box::new([0; PAGE_SIZE]);
            let start = page_index * PAGE_SIZE;
            let end = start.saturating_add(PAGE_SIZE).min(self.base_visible_len);
            if start < end {
                page[..end - start].copy_from_slice(&self.base.bytes()[start..end]);
            }
            page
        })
    }

    fn copy_pages(&self, offset: usize, output: &mut [u8]) {
        let end = offset + output.len();
        let first_page = offset / PAGE_SIZE;
        let last_page = (end - 1) / PAGE_SIZE;
        let requested_pages = last_page - first_page + 1;
        if requested_pages <= self.pages.len() {
            for page_index in first_page..=last_page {
                if let Some(page) = self.pages.get(&page_index) {
                    copy_page(page_index, page, offset, end, output);
                }
            }
        } else {
            for (&page_index, page) in &self.pages {
                if (first_page..=last_page).contains(&page_index) {
                    copy_page(page_index, page, offset, end, output);
                }
            }
        }
    }
}

fn copy_page(
    page_index: usize,
    page: &[u8; PAGE_SIZE],
    offset: usize,
    end: usize,
    output: &mut [u8],
) {
    let page_start = page_index * PAGE_SIZE;
    let overlap_start = offset.max(page_start);
    let overlap_end = end.min(page_start + PAGE_SIZE);
    let destination = overlap_start - offset;
    let source = overlap_start - page_start;
    output[destination..destination + overlap_end - overlap_start]
        .copy_from_slice(&page[source..source + overlap_end - overlap_start]);
}
