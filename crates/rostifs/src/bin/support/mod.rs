use rostifs::{
    block::{BlockDevice, BlockError},
    engine::RostiFs,
    format::{DATA_START, MAX_VOLUME_BLOCKS},
    vfs::{NodeId, NodeKind, Vfs},
};
use std::{
    fs::{self, File, OpenOptions},
    io::{Read, Seek, SeekFrom, Write},
    path::{Path, PathBuf},
};
// Only real directories beneath this repository's dist; no devices, UNC,
// symlinks or alternate streams. create_new is mandatory for all formatting.
pub fn checked_path(raw: &str, existing: bool) -> Result<PathBuf, String> {
    let path = Path::new(raw);
    if !path.is_absolute() || raw.contains("\\\\") || raw.contains("/dev/") {
        return Err("absolute test image under repository dist required".into());
    }
    let name = path
        .file_name()
        .and_then(|s| s.to_str())
        .ok_or("invalid filename")?;
    if !name.ends_with(".img")
        || !name
            .bytes()
            .all(|b| b.is_ascii_alphanumeric() || b == b'_' || b == b'-' || b == b'.')
    {
        return Err("simple .img filename required".into());
    }
    let stem = name.split('.').next().unwrap_or("").to_ascii_lowercase();
    if ["con", "prn", "aux", "nul"].contains(&stem.as_str())
        || (stem.len() == 4
            && (stem.starts_with("com") || stem.starts_with("lpt"))
            && matches!(stem.as_bytes()[3], b'1'..=b'9'))
    {
        return Err("Windows device filenames refused".into());
    }
    let dist = Path::new(env!("CARGO_MANIFEST_DIR"))
        .parent()
        .unwrap()
        .parent()
        .unwrap()
        .join("dist");
    let expected = fs::canonicalize(&dist).map_err(|e| format!("dist unavailable: {e}"))?;
    let parent = path.parent().ok_or("image has no parent")?;
    if !fs::canonicalize(parent)
        .map_err(|e| e.to_string())?
        .starts_with(&expected)
    {
        return Err("only repository dist test images accepted".into());
    }
    for component in parent.ancestors() {
        if fs::symlink_metadata(component)
            .map_err(|e| e.to_string())?
            .file_type()
            .is_symlink()
        {
            return Err("symlink directory components refused".into());
        }
    }
    if existing {
        let meta = fs::symlink_metadata(path).map_err(|e| e.to_string())?;
        if !meta.file_type().is_file() {
            return Err("regular image file required (no symlink/device)".into());
        }
    }
    Ok(path.to_path_buf())
}
pub struct Image {
    file: File,
    sectors: usize,
    owned: bool,
    writable: bool,
}
impl Image {
    pub fn create(raw: &str, blocks: usize) -> Result<Self, String> {
        if !(DATA_START..=MAX_VOLUME_BLOCKS).contains(&blocks) {
            return Err("blocks outside 7..65536".into());
        }
        let path = checked_path(raw, false)?;
        let mut file = OpenOptions::new()
            .read(true)
            .write(true)
            .create_new(true)
            .open(path)
            .map_err(|e| e.to_string())?;
        file.set_len((blocks as u64) * 4096)
            .map_err(|e| e.to_string())?;
        let mut sector = [0u8; 512];
        sector[..14].copy_from_slice(b"ROSTI-TESTDISK");
        file.write_all(&sector).map_err(|e| e.to_string())?;
        file.sync_all().map_err(|e| e.to_string())?;
        Ok(Self {
            file,
            sectors: blocks * 8,
            owned: true,
            writable: true,
        })
    }
    pub fn open(raw: &str) -> Result<Self, String> {
        let path = checked_path(raw, true)?;
        let mut file = File::open(path).map_err(|e| e.to_string())?;
        if !file.metadata().map_err(|e| e.to_string())?.is_file() {
            return Err("not a regular file".into());
        }
        let len = file.metadata().map_err(|e| e.to_string())?.len();
        if len % 4096 != 0 || !(7 * 4096..=65536 * 4096).contains(&len) {
            return Err("invalid image geometry".into());
        }
        let mut marker = [0; 14];
        file.read_exact(&mut marker).map_err(|e| e.to_string())?;
        if &marker != b"ROSTI-TESTDISK" {
            return Err("not a test-owned image".into());
        }
        Ok(Self {
            file,
            sectors: (len / 512) as usize,
            owned: true,
            writable: false,
        })
    }
    fn position(&mut self, lba: usize, len: usize) -> Result<(), BlockError> {
        if len != 512 {
            return Err(BlockError::BufferSizeMismatch);
        }
        if lba >= self.sectors {
            return Err(BlockError::OutOfRange);
        }
        self.file
            .seek(SeekFrom::Start((lba as u64) * 512))
            .map_err(|_| BlockError::Rejected)?;
        Ok(())
    }
}
impl BlockDevice for Image {
    fn sector_size(&self) -> usize {
        512
    }
    fn capacity_sectors(&self) -> usize {
        self.sectors
    }
    fn test_owned(&self) -> bool {
        self.owned
    }
    fn read_sector(&mut self, lba: usize, buf: &mut [u8]) -> Result<(), BlockError> {
        self.position(lba, buf.len())?;
        self.file.read_exact(buf).map_err(|_| BlockError::Rejected)
    }
    fn write_sector(&mut self, lba: usize, data: &[u8]) -> Result<(), BlockError> {
        if !self.writable || lba < 8 {
            return Err(BlockError::Protected);
        }
        self.position(lba, data.len())?;
        self.file.write_all(data).map_err(|_| BlockError::Rejected)
    }
    fn flush(&mut self) -> Result<(), BlockError> {
        if !self.writable {
            return Err(BlockError::Protected);
        }
        self.file.sync_all().map_err(|_| BlockError::Rejected)
    }
}
pub fn run(mode: &str) -> Result<(), String> {
    let args: Vec<String> = std::env::args().skip(1).collect();
    if mode == "mkrostifs" {
        if args.len() != 4 || args[0] != "--test-owned-image" || args[2] != "--blocks" {
            return Err(
                "usage: mkrostifs --test-owned-image ABSOLUTE_DIST_PATH.img --blocks 7..65536"
                    .into(),
            );
        }
        let blocks = args[3].parse::<usize>().map_err(|_| "invalid blocks")?;
        let mut image = Image::create(&args[1], blocks)?;
        use std::hash::{BuildHasher, Hasher};
        // RandomState has OS-seeded keys: probabilistic 64-bit identity, not a
        // cryptographic UUID or an absolute global uniqueness guarantee.
        let mut hash = std::collections::hash_map::RandomState::new().build_hasher();
        hash.write(args[1].as_bytes());
        hash.write_u32(std::process::id());
        hash.write_u128(
            std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .map_err(|e| e.to_string())?
                .as_nanos(),
        );
        let fs_id = hash.finish();
        let sb = RostiFs::format(&mut image, fs_id).map_err(|e| e.to_string())?;
        let fs = RostiFs::mount(&mut image).map_err(|e| e.to_string())?;
        println!(
            "FORMATTED version=1 blocks={} generation={} nodes={}",
            sb.total_blocks,
            sb.generation,
            fs.stats().nodes
        );
        return Ok(());
    }
    if args.len() != 2 || args[0] != "--test-owned-image" {
        return Err(format!(
            "usage: {mode} --test-owned-image ABSOLUTE_DIST_PATH.img"
        ));
    }
    let mut image = Image::open(&args[1])?;
    let fs = RostiFs::mount(&mut image).map_err(|e| e.to_string())?;
    let info = fs.mount_info();
    if mode == "rostifsck" && info.valid_roots != 2 {
        return Err(format!(
            "degraded: {} valid root; no repair performed",
            info.valid_roots
        ));
    }
    println!(
        "OK version=1 fs_id={} generation={} blocks={} used={} free={} nodes={} metadata_bytes={}",
        info.fs_id,
        info.generation,
        info.total_blocks,
        info.used_blocks,
        info.free_blocks,
        fs.stats().nodes,
        info.metadata_bytes
    );
    if mode == "rostifs-inspect" {
        fn walk(fs: &RostiFs<'_>, id: NodeId) -> Result<(), String> {
            let mut path = [0; 256];
            let n = fs.path(id, &mut path).map_err(|e| e.to_string())?;
            let m = fs.metadata(id).map_err(|e| e.to_string())?;
            println!(
                "{:?} {} {}",
                m.kind,
                m.size,
                std::str::from_utf8(&path[..n]).map_err(|e| e.to_string())?
            );
            let mut result = Ok(());
            if m.kind == NodeKind::Directory {
                fs.list(id, &mut |_, child, _| {
                    if result.is_ok() {
                        result = walk(fs, child);
                    }
                })
                .map_err(|e| e.to_string())?;
            }
            result
        }
        walk(&fs, NodeId::ROOT)?;
    }
    Ok(())
}
