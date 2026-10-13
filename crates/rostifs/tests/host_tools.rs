#![cfg(feature = "host-tools")]
#[allow(dead_code)]
#[path = "../src/bin/support/mod.rs"]
mod support;
use rostifs::{
    block::BlockDevice,
    engine::RostiFs,
    vfs::{NodeId, Vfs},
};
use std::{
    fs,
    io::{Seek, SeekFrom, Write},
    process::Command,
    sync::atomic::{AtomicUsize, Ordering},
};
static COUNTER: AtomicUsize = AtomicUsize::new(0);
struct Fixture(std::path::PathBuf);
impl Fixture {
    fn new() -> Self {
        let dir = std::path::Path::new(env!("CARGO_MANIFEST_DIR"))
            .parent()
            .unwrap()
            .parent()
            .unwrap()
            .join("dist")
            .join(format!(
                "rostifs_hosttest_{}_{}",
                std::process::id(),
                COUNTER.fetch_add(1, Ordering::Relaxed)
            ));
        fs::create_dir(&dir).unwrap();
        Self(dir)
    }
    fn image(&self, name: &str) -> String {
        self.0.join(name).to_str().unwrap().to_owned()
    }
}
impl Drop for Fixture {
    fn drop(&mut self) {
        fs::remove_dir_all(&self.0).unwrap();
    }
}
fn run(exe: &str, args: &[&str]) -> std::process::Output {
    Command::new(exe).args(args).output().unwrap()
}
#[test]
fn binaries_format_check_inspect_refuse_overwrite_and_unique_ids() {
    let f = Fixture::new();
    let p = f.image("one.img");
    let args = ["--test-owned-image", p.as_str(), "--blocks", "40"];
    let mk = env!("CARGO_BIN_EXE_mkrostifs");
    let out = run(mk, &args);
    assert!(
        out.status.success(),
        "{}",
        String::from_utf8_lossy(&out.stderr)
    );
    let bytes = fs::read(&p).unwrap();
    assert_eq!(&bytes[..14], b"ROSTI-TESTDISK");
    assert!(!run(mk, &args).status.success());
    assert_eq!(fs::read(&p).unwrap(), bytes);
    let check = run(env!("CARGO_BIN_EXE_rostifsck"), &args[..2]);
    assert!(check.status.success());
    assert!(String::from_utf8_lossy(&check.stdout).contains("OK version=1"));
    let inspect = run(env!("CARGO_BIN_EXE_rostifs-inspect"), &args[..2]);
    assert!(inspect.status.success());
    assert!(String::from_utf8_lossy(&inspect.stdout).contains("Directory 0 /"));
    let p2 = f.image("two.img");
    assert!(
        run(mk, &["--test-owned-image", &p2, "--blocks", "40"])
            .status
            .success()
    );
    let other = fs::read(p2).unwrap();
    assert_ne!(&bytes[4096 + 24..4096 + 32], &other[4096 + 24..4096 + 32]);
    assert_eq!(fs::read(&p).unwrap(), bytes);
}
#[test]
fn regular_image_reopen_persists_nested_files_and_readonly_tools() {
    let f = Fixture::new();
    let p = f.image("persistent.img");
    {
        let mut d = support::Image::create(&p, 80).unwrap();
        RostiFs::format(&mut d, 0xabcdef).unwrap();
        let mut fs = RostiFs::mount(&mut d).unwrap();
        let dir = fs.create_dir(NodeId::ROOT, "nested").unwrap();
        let a = fs.create_file(dir, "file").unwrap();
        fs.replace(a, b"old").unwrap();
        fs.append(a, b" and new ").unwrap();
    }
    let before = fs::read(&p).unwrap();
    let mut d = support::Image::open(&p).unwrap();
    {
        let fs = RostiFs::mount(&mut d).unwrap();
        let a = fs.lookup(NodeId::ROOT, "nested/file").unwrap();
        let mut b = [0; 32];
        let n = fs.read(a, 0, &mut b).unwrap();
        assert_eq!(&b[..n], b"old and new ");
    }
    assert!(d.flush().is_err());
    drop(d);
    let out = run(
        env!("CARGO_BIN_EXE_rostifs-inspect"),
        &["--test-owned-image", &p],
    );
    assert!(out.status.success());
    assert!(String::from_utf8_lossy(&out.stdout).contains("File 12 /nested/file"));
    assert_eq!(fs::read(&p).unwrap(), before);
}
#[test]
fn tools_refuse_devices_relative_outside_dist_ads_and_bad_geometry() {
    let f = Fixture::new();
    for p in [
        "/dev/sda",
        "/dev/null",
        r"\\.\PhysicalDrive0",
        r"\\server\share\x.img",
        "C:/Windows/x.img",
        "relative.img",
        f.image("CON.img").as_str(),
        f.image("NUL.img").as_str(),
        f.image("x.img:stream").as_str(),
    ] {
        assert!(support::checked_path(p, false).is_err(), "{p}");
        assert!(
            !run(
                env!("CARGO_BIN_EXE_mkrostifs"),
                &["--test-owned-image", p, "--blocks", "20"]
            )
            .status
            .success()
        );
    }
    let p = f.image("geometry.img");
    for blocks in ["0", "6", "65537", "18446744073709551615"] {
        assert!(
            !run(
                env!("CARGO_BIN_EXE_mkrostifs"),
                &["--test-owned-image", &p, "--blocks", blocks]
            )
            .status
            .success()
        );
        assert!(!std::path::Path::new(&p).exists());
    }
}
#[test]
fn fsck_degraded_and_corrupt_images_fail_without_repairs() {
    let f = Fixture::new();
    let p = f.image("damaged.img");
    assert!(
        run(
            env!("CARGO_BIN_EXE_mkrostifs"),
            &["--test-owned-image", &p, "--blocks", "20"]
        )
        .status
        .success()
    );
    let mut file = fs::OpenOptions::new().write(true).open(&p).unwrap();
    file.seek(SeekFrom::Start(4096 + 100)).unwrap();
    file.write_all(&[1]).unwrap();
    file.sync_all().unwrap();
    let before = fs::read(&p).unwrap();
    let check = run(env!("CARGO_BIN_EXE_rostifsck"), &["--test-owned-image", &p]);
    assert!(!check.status.success());
    assert!(String::from_utf8_lossy(&check.stderr).contains("degraded"));
    assert_eq!(fs::read(&p).unwrap(), before);
    file.seek(SeekFrom::Start(8192 + 100)).unwrap();
    file.write_all(&[1]).unwrap();
    file.sync_all().unwrap();
    let before = fs::read(&p).unwrap();
    assert!(
        !run(
            env!("CARGO_BIN_EXE_rostifs-inspect"),
            &["--test-owned-image", &p]
        )
        .status
        .success()
    );
    assert_eq!(fs::read(&p).unwrap(), before);
}
