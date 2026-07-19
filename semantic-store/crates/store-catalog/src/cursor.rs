use sha2::{Digest, Sha256};
use subtle::ConstantTimeEq as _;
use uuid::Uuid;

use crate::CatalogError;

const MAGIC: &[u8; 4] = b"RSC1";
const PAYLOAD_LEN: usize = 4 + 1 + 8 + 32 + 32;
const TOKEN_LEN: usize = PAYLOAD_LEN + 32;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub(crate) enum Operation {
    Search = 1,
    Browse = 2,
}

impl Operation {
    fn from_byte(value: u8) -> Option<Self> {
        match value {
            1 => Some(Self::Search),
            2 => Some(Self::Browse),
            _ => None,
        }
    }
}

/// Opaque signing authority for authenticated catalog cursors.
///
/// Clone one authority across revisions of the same Store so a cursor can be
/// authenticated before its embedded revision is checked. Use a different
/// authority for every Store ID. The signing key is intentionally inaccessible
/// and omitted from debug output.
#[derive(Clone)]
pub struct CursorAuthority {
    key: [u8; 32],
}

impl CursorAuthority {
    #[must_use]
    pub fn new() -> Self {
        let first = Uuid::new_v4();
        let second = Uuid::new_v4();
        let mut hasher = Sha256::new();
        hasher.update(first.as_bytes());
        hasher.update(second.as_bytes());
        hasher.update(b"reframe.semantic-store.catalog.cursor.v1");
        Self {
            key: hasher.finalize().into(),
        }
    }

    #[cfg(test)]
    const fn with_key(key: [u8; 32]) -> Self {
        Self { key }
    }
}

impl Default for CursorAuthority {
    fn default() -> Self {
        Self::new()
    }
}

impl std::fmt::Debug for CursorAuthority {
    fn fmt(&self, formatter: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        formatter
            .debug_struct("CursorAuthority")
            .finish_non_exhaustive()
    }
}

pub(crate) struct CursorCodec {
    authority: CursorAuthority,
}

impl CursorCodec {
    pub(crate) const fn with_authority(authority: CursorAuthority) -> Self {
        Self { authority }
    }

    pub(crate) fn encode(
        &self,
        operation: Operation,
        offset: usize,
        revision: &[u8; 32],
        binding: &[u8; 32],
    ) -> String {
        let mut bytes = Vec::with_capacity(TOKEN_LEN);
        bytes.extend_from_slice(MAGIC);
        bytes.push(operation as u8);
        bytes.extend_from_slice(&u64::try_from(offset).unwrap_or(u64::MAX).to_be_bytes());
        bytes.extend_from_slice(revision);
        bytes.extend_from_slice(binding);
        let tag = hmac_sha256(&self.authority.key, &bytes);
        bytes.extend_from_slice(&tag);
        base64url_encode(&bytes)
    }

    pub(crate) fn decode(
        &self,
        token: &str,
        operation: Operation,
        revision: &[u8; 32],
        binding: &[u8; 32],
    ) -> Result<usize, CatalogError> {
        let bytes = base64url_decode(token).ok_or(CatalogError::InvalidCursor)?;
        if bytes.len() != TOKEN_LEN || &bytes[..MAGIC.len()] != MAGIC {
            return Err(CatalogError::InvalidCursor);
        }
        let (payload, supplied_tag) = bytes.split_at(PAYLOAD_LEN);
        let expected_tag = hmac_sha256(&self.authority.key, payload);
        if supplied_tag.ct_eq(&expected_tag).unwrap_u8() != 1 {
            return Err(CatalogError::InvalidCursor);
        }
        if Operation::from_byte(payload[4]) != Some(operation) {
            return Err(CatalogError::InvalidCursor);
        }
        if &payload[13..45] != revision {
            return Err(CatalogError::StaleCursor);
        }
        if &payload[45..77] != binding {
            return Err(CatalogError::InvalidCursor);
        }
        let offset_bytes: [u8; 8] = payload[5..13]
            .try_into()
            .map_err(|_| CatalogError::InvalidCursor)?;
        usize::try_from(u64::from_be_bytes(offset_bytes)).map_err(|_| CatalogError::InvalidCursor)
    }
}

pub(crate) fn binding_hash(parts: &[&[u8]]) -> [u8; 32] {
    let mut hasher = Sha256::new();
    hasher.update(b"reframe.semantic-store.catalog.binding.v1");
    for part in parts {
        hasher.update(u64::try_from(part.len()).unwrap_or(u64::MAX).to_be_bytes());
        hasher.update(part);
    }
    hasher.finalize().into()
}

fn hmac_sha256(key: &[u8; 32], message: &[u8]) -> [u8; 32] {
    let mut inner_pad = [0x36; 64];
    let mut outer_pad = [0x5c; 64];
    for (index, byte) in key.iter().enumerate() {
        inner_pad[index] ^= byte;
        outer_pad[index] ^= byte;
    }
    let mut inner = Sha256::new();
    inner.update(inner_pad);
    inner.update(message);
    let inner_hash = inner.finalize();

    let mut outer = Sha256::new();
    outer.update(outer_pad);
    outer.update(inner_hash);
    outer.finalize().into()
}

const ALPHABET: &[u8; 64] = b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_";

fn base64url_encode(input: &[u8]) -> String {
    let mut output = String::with_capacity(input.len().div_ceil(3) * 4);
    for chunk in input.chunks(3) {
        let first = chunk[0];
        let second = chunk.get(1).copied().unwrap_or(0);
        let third = chunk.get(2).copied().unwrap_or(0);
        output.push(char::from(ALPHABET[usize::from(first >> 2)]));
        output.push(char::from(
            ALPHABET[usize::from((first & 0x03) << 4 | second >> 4)],
        ));
        if chunk.len() > 1 {
            output.push(char::from(
                ALPHABET[usize::from((second & 0x0f) << 2 | third >> 6)],
            ));
        }
        if chunk.len() > 2 {
            output.push(char::from(ALPHABET[usize::from(third & 0x3f)]));
        }
    }
    output
}

fn base64url_decode(input: &str) -> Option<Vec<u8>> {
    if input.is_empty() || input.len() % 4 == 1 || !input.is_ascii() {
        return None;
    }
    let mut output = Vec::with_capacity(input.len() / 4 * 3 + 2);
    for chunk in input.as_bytes().chunks(4) {
        let first = decode_digit(chunk[0])?;
        let second = decode_digit(*chunk.get(1)?)?;
        output.push(first << 2 | second >> 4);
        if chunk.len() > 2 {
            let third = decode_digit(chunk[2])?;
            output.push(second << 4 | third >> 2);
            if chunk.len() > 3 {
                let fourth = decode_digit(chunk[3])?;
                output.push(third << 6 | fourth);
            } else if third & 0x03 != 0 {
                return None;
            }
        } else if second & 0x0f != 0 {
            return None;
        }
    }
    (base64url_encode(&output) == input).then_some(output)
}

fn decode_digit(value: u8) -> Option<u8> {
    match value {
        b'A'..=b'Z' => Some(value - b'A'),
        b'a'..=b'z' => Some(value - b'a' + 26),
        b'0'..=b'9' => Some(value - b'0' + 52),
        b'-' => Some(62),
        b'_' => Some(63),
        _ => None,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn base64url_round_trips_without_padding() {
        for value in [b"f".as_slice(), b"fo", b"foo", b"foobar"] {
            let encoded = base64url_encode(value);
            assert!(!encoded.contains('='));
            assert_eq!(base64url_decode(&encoded).as_deref(), Some(value));
        }
    }

    #[test]
    fn cursor_rejects_tampering_and_wrong_bindings() {
        let codec = CursorCodec::with_authority(CursorAuthority::with_key([7; 32]));
        let revision = [3; 32];
        let binding = binding_hash(&[b"query"]);
        let token = codec.encode(Operation::Search, 12, &revision, &binding);
        assert_eq!(
            codec.decode(&token, Operation::Search, &revision, &binding),
            Ok(12)
        );

        let mut tampered = token.into_bytes();
        tampered[20] = if tampered[20] == b'A' { b'B' } else { b'A' };
        assert_eq!(
            codec.decode(
                std::str::from_utf8(&tampered).expect("ASCII"),
                Operation::Search,
                &revision,
                &binding
            ),
            Err(CatalogError::InvalidCursor)
        );
    }

    #[test]
    fn shared_authority_authenticates_before_revision_check() {
        let authority = CursorAuthority::with_key([9; 32]);
        let encoder = CursorCodec::with_authority(authority.clone());
        let decoder = CursorCodec::with_authority(authority);
        let binding = binding_hash(&[b"same request"]);
        let token = encoder.encode(Operation::Browse, 2, &[1; 32], &binding);
        assert_eq!(
            decoder.decode(&token, Operation::Browse, &[2; 32], &binding),
            Err(CatalogError::StaleCursor)
        );
    }

    #[test]
    fn independent_authority_rejects_foreign_cursor() {
        let encoder = CursorCodec::with_authority(CursorAuthority::with_key([1; 32]));
        let decoder = CursorCodec::with_authority(CursorAuthority::with_key([2; 32]));
        let binding = binding_hash(&[b"same request"]);
        let token = encoder.encode(Operation::Browse, 2, &[1; 32], &binding);

        assert_eq!(
            decoder.decode(&token, Operation::Browse, &[2; 32], &binding),
            Err(CatalogError::InvalidCursor)
        );
    }
}
