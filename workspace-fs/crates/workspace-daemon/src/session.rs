use std::collections::{BTreeMap, BTreeSet};
use std::fs;
use std::path::{Path, PathBuf};

use anyhow::{Context, Result, bail};
use rusqlite::{OptionalExtension, params};
use walkdir::WalkDir;

use crate::model::{
    Change, ChangeKind, CheckpointResult, FileRecord, SessionCreated, SessionStatus, SessionSummary,
};
use crate::paths::{ScratchMatcher, native_path, normalize_relative, scratch_rules};
use crate::store::{PersistedMemorySource, Store, now_millis, validate_id};

include!("session/create.rs");
include!("session/lifecycle.rs");
include!("session/checkpoint.rs");
include!("session/state.rs");
include!("session/tests.rs");
