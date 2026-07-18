use std::collections::HashMap;
use std::io::{Read, Write};
use std::path::{Path, PathBuf};
use std::sync::Arc;

use anyhow::{Context, Result, bail};
use rusqlite::{OptionalExtension, params};
use serde_json::json;

use crate::paths::normalize_relative;
use crate::protocol::{Operation, ProtocolError, Request, Response};
use crate::{
    resident::ResidentWorkspace,
    session,
    store::{Store, now_millis},
};

#[cfg(unix)]
use crate::unix_vfs::Provider;
#[cfg(windows)]
use crate::windows_vfs::Provider;

include!("daemon/server.rs");
include!("daemon/framing.rs");
include!("daemon/tests.rs");
