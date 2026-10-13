#[test]
fn io_error_during_candidate_read_cannot_mount_older_root() {
    let mut d = baseline();
    d.fail_read = Some(8);
    let before = d.live.clone();
    assert!(matches!(RostiFs::mount(&mut d), Err(FsError::DeviceIo)));
    assert_eq!(d.live, before);
}
#[test]
fn fragmented_free_space_refuses_large_extent_then_reuses_deleted_run() {
    let mut d = fresh(15); // Eight data blocks beyond the seven reserved blocks.
    {
        let mut fs = RostiFs::mount(&mut d).unwrap();
        for name in ["a", "b", "c", "d", "e", "f", "g", "h"] {
            let id = fs.create_file(NodeId::ROOT, name).unwrap();
            fs.replace(id, &vec![name.as_bytes()[0]; 4096]).unwrap();
        }
        for name in ["a", "c", "e", "g"] {
            fs.remove_file(NodeId::ROOT, name).unwrap();
        }
        fs.create_file(NodeId::ROOT, "advance").unwrap();
        assert_eq!(fs.mount_info().free_blocks, 4);
        let big = fs.create_file(NodeId::ROOT, "big").unwrap();
        assert_eq!(fs.replace(big, &vec![0xcc; 8192]), Err(FsError::FilesystemFull));
        assert_eq!(fs.metadata(big).unwrap().size, 0);
        assert_eq!(fs.mount_info().free_blocks, 4);
        let neighbor = fs.lookup(NodeId::ROOT, "d").unwrap();
        assert_eq!(contents(&fs, neighbor), vec![b'd'; 4096]);
        fs.remove_file(NodeId::ROOT, "b").unwrap();
        assert_eq!(fs.remove_file(NodeId::ROOT, "b"), Err(FsError::NotFound));
        fs.create_file(NodeId::ROOT, "advance2").unwrap();
        fs.replace(big, &vec![0xcc; 8192]).unwrap();
    }
    d.crash();
    let fs = RostiFs::mount(&mut d).unwrap();
    let big = fs.lookup(NodeId::ROOT, "big").unwrap();
    assert_eq!(contents(&fs, big), vec![0xcc; 8192]);
    for name in ["d", "f", "h"] {
        assert_eq!(contents(&fs, fs.lookup(NodeId::ROOT, name).unwrap()),
                   vec![name.as_bytes()[0]; 4096]);
    }
}
#[test]
fn previous_root_data_survives_repeated_cow_and_latest_root_corruption() {
    let mut d = fresh(20);
    let last_bank;
    {
        let mut fs = RostiFs::mount(&mut d).unwrap();
        let a = fs.create_file(NodeId::ROOT, "a").unwrap();
        for data in [
            b"first".as_slice(),
            b"second".as_slice(),
            b"third".as_slice(),
        ] {
            fs.replace(a, data).unwrap();
        }
        last_bank = (fs.mount_info().generation % 2) as usize;
    }
    d.live[(1 + last_bank) * 4096 + 100] ^= 1;
    let fs = RostiFs::mount(&mut d).unwrap();
    let a = fs.lookup(NodeId::ROOT, "a").unwrap();
    assert_eq!(contents(&fs, a), b"second");
    assert_eq!(fs.mount_info().valid_roots, 1);
}
#[test]
fn no_generation_wrap_and_node_retirement() {
    let mut d = fresh(20);
    {
        let mut fs = RostiFs::mount(&mut d).unwrap();
        fs.create_file(NodeId::ROOT, "a").unwrap();
        fs.create_dir(NodeId::ROOT, "checkpoint").unwrap();
    }
    forge(&mut d, |page| {
        if page[128 + 4] == TYPE_FILE {
            put_u32(page, 128, u32::MAX - 1);
        }
    });
    {
        let mut fs = RostiFs::mount(&mut d).unwrap();
        let a = fs.lookup(NodeId::ROOT, "a").unwrap();
        fs.remove_file(NodeId::ROOT, "a").unwrap();
        let b = fs.create_file(NodeId::ROOT, "b").unwrap();
        assert_ne!(a.slot, b.slot);
        assert_eq!(fs.metadata(a), Err(FsError::NotFound));
    }
    // Both roots valid with adjacent exhausted transaction generations.
    for bank in 0..2 {
        let off = (1 + bank) * 4096;
        let mut root = [0; 4096];
        root.copy_from_slice(&d.live[off..off + 4096]);
        let mut sb = Superblock::decode(&root, bank, d.capacity_sectors()).unwrap();
        sb.generation = u64::MAX - 1 + bank as u64;
        sb.encode(&mut root);
        d.live[off..off + 4096].copy_from_slice(&root);
    }
    let mut fs = RostiFs::mount(&mut d).unwrap();
    assert_eq!(
        fs.create_file(NodeId::ROOT, "exhausted"),
        Err(FsError::FilesystemFull)
    );
}
#[test]
fn canonical_path_limit_applies_to_relative_creates() {
    let mut d = fresh(20);
    let mut fs = RostiFs::mount(&mut d).unwrap();
    let name = "x".repeat(60);
    let mut dir = NodeId::ROOT;
    for _ in 0..4 {
        dir = fs.create_dir(dir, &name).unwrap();
    }
    let file = fs.create_file(dir, "eleven_byte").unwrap();
    let mut path = [0; 256];
    assert_eq!(fs.path(file, &mut path), Ok(256));
    assert_eq!(
        fs.create_file(dir, "thirteen_byte"),
        Err(FsError::InvalidPath)
    );
    assert_eq!(fs.path(file, &mut [0; 255]), Err(FsError::InvalidPath));
}
#[test]
fn every_root_sector_every_byte_prefix_tear() {
    let base = baseline();
    let old = snapshot(&RostiFs::mount(&mut base.clone()).unwrap());
    let mut good = base.clone();
    {
        let mut fs = RostiFs::mount(&mut good).unwrap();
        operation(&mut fs, 0).unwrap();
    }
    let new = snapshot(&RostiFs::mount(&mut good).unwrap());
    let mut durable = base.durable.clone();
    let mut pending = vec![];
    let mut cases = 0;
    for event in &good.events {
        match event {
            Event::Flush => {
                for (lba, raw) in pending.drain(..) {
                    let raw: [u8; 512] = raw;
                    durable[lba * 512..(lba + 1) * 512].copy_from_slice(&raw);
                }
            }
            Event::Write(lba, raw) => {
                if *lba < 24 {
                    for split in 0..=512 {
                        let mut d = base.clone();
                        d.live = durable.clone();
                        d.live[lba * 512..lba * 512 + split].copy_from_slice(&raw[..split]);
                        let got = snapshot(&RostiFs::mount(&mut d).unwrap());
                        assert!(got == old || got == new, "root lba {lba} tear {split}");
                        cases += 1;
                    }
                }
                pending.push((*lba, *raw));
            }
        }
    }
    std::println!("all root-sector byte-prefix tears={cases}");
}
#[test]
fn sequence_of_failed_commits_remounts_and_successful_reuse() {
    let mut d = baseline();
    for round in 0..48 {
        d.checkpoint();
        let old = snapshot(&RostiFs::mount(&mut d).unwrap());
        let mut good = d.clone();
        {
            let mut fs = RostiFs::mount(&mut good).unwrap();
            let a = fs.lookup(NodeId::ROOT, "a").unwrap();
            fs.replace(a, &vec![round as u8; 4200 + round]).unwrap();
        }
        let new = snapshot(&RostiFs::mount(&mut good).unwrap());
        let events = good.events.len();
        d.fail = Some((round * 7 % events, round * 31 % 513));
        {
            let mut fs = RostiFs::mount(&mut d).unwrap();
            let a = fs.lookup(NodeId::ROOT, "a").unwrap();
            assert_eq!(
                fs.replace(a, &vec![round as u8; 4200 + round]),
                Err(FsError::DeviceIo)
            );
        }
        d.crash();
        let mut fs = RostiFs::mount(&mut d).unwrap();
        let got = snapshot(&fs);
        assert!(got == old || got == new);
        let a = fs.lookup(NodeId::ROOT, "a").unwrap();
        fs.replace(a, &vec![0x88; 5000]).unwrap();
        assert_eq!(contents(&fs, a), vec![0x88; 5000]);
    }
}
