fn load_record(store: &Store, record: &FileRecord) -> Result<Vec<u8>> {
    match record.source_kind.as_str() {
        "blob" => store.read_blob(&record.hash),
        "backing_blob" => {
            let reference = record.source_ref.as_deref().context(
                "backing-store entry is missing its reference",
            )?;
            let (store_root, hash): (PathBuf, String) =
                serde_json::from_str(reference).context("invalid backing-store reference")?;
            Store::open(&store_root)?.read_blob(&hash)
        }
        "memory" => {
            let reference = record.source_ref.as_deref().context(
                "memory entry is missing its reference",
            )?;
            let (memory_id, relative): (String, String) =
                serde_json::from_str(reference).context("invalid memory reference")?;
            std::fs::read(native_path(&store.memory_path(&memory_id)?, &relative))
                .with_context(|| format!("read filesystem memory {reference}"))
        }
        kind => bail!("unsupported resident source kind: {kind}"),
    }
}

fn validate_content(record: &FileRecord, bytes: &[u8]) -> Result<()> {
    let actual = blake3::hash(bytes).to_hex().to_string();
    if actual != record.hash {
        bail!(
            "filesystem memory changed after session creation at {} (expected {}, found {})",
            record.path,
            record.hash,
            actual
        );
    }
    Ok(())
}

fn lock_error<T>(_error: std::sync::PoisonError<T>) -> anyhow::Error {
    anyhow::anyhow!("resident workspace lock was poisoned")
}

fn add_parent_directories(directories: &mut BTreeSet<String>, path: &str) {
    let mut current = String::new();
    let mut parts = path.split('/').peekable();
    while let Some(part) = parts.next() {
        if parts.peek().is_none() {
            break;
        }
        if !current.is_empty() {
            current.push('/');
        }
        current.push_str(part);
        directories.insert(current.clone());
    }
}
