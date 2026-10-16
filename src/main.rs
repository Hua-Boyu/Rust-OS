#![warn(clippy::all)]
#![cfg_attr(not(test), no_std)]
#![cfg_attr(not(test), no_main)]
#![feature(abi_x86_interrupt)]

use core::arch::global_asm;
use core::panic::PanicInfo;

extern crate alloc;

mod allocator;
mod block;
use block::BlockDevice;
mod cpu;
mod fd;
mod fs;
mod fs_commands;
mod fs_stress;
mod gdt;
mod initramfs;
mod initramfs_trust;
mod interrupt;
mod io;
mod kbd;
mod memory;
mod multiboot;
mod reboot;
mod shell;
mod storage;
mod system_image;
mod timer;
mod utils;

// Initialized data, not BSS: the pre-entry GDB fixture survives boot stack/BSS setup.
#[cfg(feature = "initramfs-failure-test")]
#[used]
#[unsafe(no_mangle)]
pub static mut INITRAMFS_TEST_MODE: u8 = 0xff;

#[cfg(not(test))]
global_asm!(include_str!("boot.s"), options(att_syntax));

#[cfg(not(test))]
#[panic_handler]
fn panic_handler(info: &PanicInfo) -> ! {
    use core::fmt::Write;
    io::serial::init();
    let _ = writeln!(io::serial::SerialWriter, "PANIC: {}", info);
    println!("{}", info);
    loop {}
}

static PORT_MANAGER: utils::mutex::SpinMutex<io::ports::PortAllocator> =
    utils::mutex::SpinMutex::new(io::ports::PortAllocator::new());

enum BootModuleSelection {
    Absent,
    Selected(multiboot::inventory::ModuleDescriptor),
    Ambiguous,
}

/// Called before paging, once, with the kernel-BSS heap initialized.
unsafe fn prepare_boot_memory(
    magic: u32,
    info: u64,
) -> Result<BootModuleSelection, multiboot::inventory::BootError> {
    use multiboot::inventory::BootError;
    let inventory = unsafe { multiboot::inventory::from_physical(magic, info)? };
    // Copy only owned scalar metadata; all loader spans remain reserved even
    // when selection or later archive import fails.
    let selected = match inventory.select_initramfs() {
        Ok(None) => BootModuleSelection::Absent,
        Ok(Some(module)) => BootModuleSelection::Selected(*module),
        Err(_) => BootModuleSelection::Ambiguous,
    };
    io::serial::puts("DBG: mmap print\n");
    println!("----- multiboot mmap -----");
    println!("num entries: {}", inventory.entries.len());
    io::serial::puts("DBG: mmap printed\n");
    let mut entries = inventory.entries;
    entries
        .try_reserve_exact(inventory.reservations.len())
        .map_err(|_| BootError::Allocation)?;
    for (start, end) in inventory.reservations {
        entries.push(multiboot::MmapEntry {
            size: 20,
            base_addr: start,
            length: end - start,
            type_: 2,
        });
    }
    io::serial::puts("DBG: mmap parsed\n");
    let total_kb = entries
        .iter()
        .filter(|e| e.type_ == 1)
        .map(|e| e.length / 1024)
        .fold(0u64, u64::saturating_add);
    shell::set_mem_info(total_kb, allocator::bootstrap_heap_bounds().0 as u64);
    io::serial::puts("DBG: mem info set\n");
    let (start, end) = allocator::bootstrap_heap_bounds();
    match memory::prepare(&entries, info, start as u64, end as u64) {
        Ok(window) => {
            let (total, reserved, free) = {
                let fa = memory::FRAME_ALLOC.lock();
                let s = fa.stats();
                (s.total_frames, s.reserved_frames, s.free_frames)
            };
            println!(
                "frame allocator: {} frames total, {} reserved, {} free",
                total, reserved, free
            );
            println!(
                "paging window: {:#010x} (page tables built, validated)",
                window
            );
        }
        Err(message) => {
            io::serial::puts("paging validation FAILED, paging left disabled:\n");
            io::serial::puts(message);
            io::serial::putc(b'\n');
        }
    }
    Ok(selected)
}

// Privileged guest-only exhaustion probe. Fixed metadata stays off the boot stack.
// No infallible allocation, filesystem mutation, formatting or held guard occurs
// while pressure is live. Every buffer is released before recovery diagnostics.
#[cfg(feature = "initramfs-failure-test")]
fn build_under_heap_pressure(
    archive: &mut fs::ArchiveFs,
    index: &initramfs::Archive,
    bytes: &[u8],
) -> Result<(), fs::FsError> {
    use alloc::vec::Vec;
    static mut PRESSURE: [Vec<u8>; 768] = [const { Vec::new() }; 768];
    // SAFETY: this test-only boot path executes once; no ISR accesses PRESSURE.
    let pressure = unsafe { &mut *(&raw mut PRESSURE) };
    let before = allocator::heap_stats();
    for (group, chunk) in [32768, 1024, 32].into_iter().enumerate() {
        for buffer in &mut pressure[group * 256..(group + 1) * 256] {
            if buffer.try_reserve_exact(chunk).is_err() {
                break;
            }
        }
    }
    let result = archive.try_build(index, bytes);
    for buffer in pressure {
        *buffer = Vec::new();
    }
    let after = allocator::heap_stats();
    if result == Err(fs::FsError::OutOfMemory)
        && after.failed_allocs > before.failed_allocs
        && after.live_allocs == before.live_allocs
        && after.used == before.used
    {
        io::serial::puts("ROSTI: initramfs real allocator OOM recovered\n");
    } else {
        io::serial::puts("ROSTI: initramfs OOM fixture FAILED\n");
    }
    result
}

#[cfg(not(test))]
#[unsafe(no_mangle)]
/// # Safety
/// Entered once via boot.s in flat 32-bit protected mode with paging off,
/// interrupts disabled, DF clear and the i686 C ABI stack contract established.
/// `info` is treated as an untrusted physical address, not dereferenced as a
/// Rust BootInfo reference. The inventory adapter bounds all reads first.
/// The loader/firmware must provide readable conventional RAM and truthful
/// RAM-map backing; this is not a hostile firmware isolation boundary.
pub unsafe extern "C" fn kernel_main(magic: u32, info: *const multiboot::BootInfo) -> ! {
    io::serial::init();
    io::serial::puts("ROSTI: entered kernel_main\n");

    io::vga::init_writer();
    unsafe {
        io::serial::puts("DBG: alloc init\n");
        allocator::ALLOC.lock().init(info);
    }
    // Rejected inventory never initializes frames or enables paging. The
    // independent kernel-BSS heap still supports the RAMFS recovery namespace.
    // A rejected inventory also closes the persistent-storage gate: no ATA
    // probe, mount or raw shell write runs against media under untrusted boot
    // metadata. Accepted boot keeps the storage paths open.
    let boot_module = match unsafe { prepare_boot_memory(magic, info as u64) } {
        Ok(selected) => selected,
        Err(error) => {
            multiboot::inventory::record(error);
            use core::fmt::Write;
            let _ = writeln!(
                io::serial::SerialWriter,
                "ROSTI: boot metadata rejected: {:?}; bootstrap-heap recovery",
                error
            );
            BootModuleSelection::Absent
        }
    };
    println!("hi");

    gdt::init_gdt();
    interrupt::init_idt(&mut PORT_MANAGER.lock());

    // Enable paging only after the IDT is loaded (page faults must be
    // handled) and the mapping was validated above.
    if memory::page_directory().is_some() {
        memory::enable_paging();
        io::serial::puts("ROSTI: paging enabled (CR0.PG, identity map)\n");
    }

    // stub: enable ps2 & interrupts
    {
        let pm = &mut PORT_MANAGER.lock();
        let mut ps2_status = pm.allocate(0x64).expect("ps2 status");
        let _ps2_data = pm.allocate(0x60).expect("ps2 data");
        // read the status register from port 0x64 (not the data port 0x60),
        // set bit 0 (enable reception of keyboard scancodes) and write it back
        // to the command port 0x64.
        ps2_status.outb(0xAE);
        ps2_status.outb(0x20);
        let s = ps2_status.inb() | 0x01;
        ps2_status.outb(s);
        core::mem::forget(ps2_status);
        core::mem::forget(_ps2_data);
    } // release allocator guard before ATA allocation or formatting

    println!("ps2 init enable");
    timer::init();

    // Phase 8 block layer: acquire the primary IDE channel through the port
    // allocator, release the guard, then probe with finite bounded polls.
    // Main context only; ISRs never touch ports or this subsystem.
    // A rejected boot inventory closes the persistent-storage gate before any
    // device access: media cannot be probed or modified under untrusted boot
    // metadata. The RAMFS recovery shell remains fully functional.
    if multiboot::inventory::storage_allowed() {
        let ports = block::acquire_channel(&mut PORT_MANAGER.lock(), block::PRIMARY_BASE);
        if let Some(ports) = ports {
            let disk = &mut *storage::DISK.lock();
            disk.rebind_ports(ports);
            match disk.probe() {
                Ok(()) if disk.capacity_sectors() > 0 => {
                    io::serial::puts("ROSTI: block device present\n");
                    disk.probe_test_owned();
                }
                Ok(()) => io::serial::puts("ROSTI: block device: no 28-bit LBA support\n"),
                Err(e) => {
                    io::serial::puts("ROSTI: block probe: ");
                    use core::fmt::Write;
                    let _ = writeln!(io::serial::SerialWriter, "{}", e);
                }
            }
        } else {
            io::serial::puts("ROSTI: block ports unavailable (already owned)\n");
        }
    } else {
        io::serial::puts("ROSTI: storage gate closed (boot metadata rejected)\n");
    }
    let mut disk = storage::DiskView::new();

    // Filesystem metadata lives in static storage, not the 16 KiB boot stack.
    // Exactly one main-loop owner; IRQ handlers never access this instance.
    static mut FILESYSTEM: fs::MountedFs = fs::MountedFs::new();
    static mut FS_DISK: storage::FsDisk = storage::FsDisk;
    // SAFETY: const initialization gives the backend the sole mutable view of
    // FS_DISK for the entire kernel lifetime. Diagnostics use a different view
    // serialized through storage::DISK; neither view aliases the ATA driver.
    static mut BACKEND: fs::RostiBackend<'static> =
        unsafe { fs::RostiBackend::new(&mut *(&raw mut FS_DISK)) };
    static mut DESCRIPTORS: fd::FdTable = fd::FdTable::new();
    // SAFETY: the boot entry executes once and never returns. These references
    // are the only FILESYSTEM/DESCRIPTORS borrows, retained by the single main
    // loop; no ISR, callback or secondary CPU accesses these static objects.
    // Keep them static to avoid placing their tables on the 16 KiB boot stack.
    let filesystem = unsafe { &mut *(&raw mut FILESYSTEM) };
    let descriptors = unsafe { &mut *(&raw mut DESCRIPTORS) };
    descriptors.init_console();
    let mut cwd = fs::NodeId::ROOT;

    #[cfg(feature = "initramfs-failure-test")]
    let fixture_mode = unsafe { core::ptr::read_volatile(&raw const INITRAMFS_TEST_MODE) };
    #[cfg(feature = "initramfs-failure-test")]
    if fixture_mode == 1 {
        use fs::Vfs;
        // A real pre-existing file must not be hidden or changed by attachment.
        if let Ok(id) = filesystem.create_file(fs::NodeId::ROOT, "/system") {
            let _ = filesystem.replace(id, b"collision sentinel");
        }
    }

    // Authenticate the immutable owned copy before constructing any VFS nodes.
    // Neither rejected content nor a failed mount is needed by the recovery shell.
    match boot_module {
        BootModuleSelection::Absent => {
            io::serial::puts("ROSTI: initramfs absent; RAMFS recovery\n")
        }
        BootModuleSelection::Ambiguous => {
            io::serial::puts("ROSTI: initramfs ambiguous; RAMFS recovery\n")
        }
        BootModuleSelection::Selected(module) => {
            // SAFETY: exact descriptor copied from the accepted inventory;
            // its RAM span was checked against kernel/heap/metadata, reserved
            // before frame allocation, and is still pinned until reboot.
            match unsafe { memory::boot_copy::copy_module(module.range.0, module.range.1) } {
                Ok(bytes) => {
                    {
                        use core::fmt::Write;
                        let indexes =
                            2 * initramfs::MAX_ENTRIES * core::mem::size_of::<initramfs::Entry>();
                        let snapshot = fs::ArchiveFs::maximum_snapshot_heap_bytes();
                        let input = memory::boot_copy::MAX_MODULE_BYTES;
                        let _ = writeln!(
                            io::serial::SerialWriter,
                            "ROSTI: image buffer bound input={} indexes={} snapshot={} total={} excludes_allocator_overhead",
                            input,
                            indexes,
                            snapshot,
                            input + indexes + snapshot
                        );
                    }
                    let verify_started = timer::ticks();
                    let verified = initramfs_trust::verify(&bytes, &system_image::EXPECTED_SHA256);
                    let verify_ticks = timer::ticks().wrapping_sub(verify_started);
                    // PIT observations have 10 ms granularity, not sub-tick precision.
                    // Measure before serial formatting; no guard survives the operation.
                    {
                        use core::fmt::Write;
                        let _ = writeln!(
                            io::serial::SerialWriter,
                            "ROSTI: image timing verify_ticks={} hz={}",
                            verify_ticks,
                            timer::TIMER_HZ
                        );
                    }
                    match verified {
                        Ok(index) => {
                            // SAFETY: initialized in static storage, borrowed once at boot.
                            // On publication MountedFs owns this exclusive borrow until reboot.
                            static mut SYSTEM: fs::ArchiveFs = fs::ArchiveFs::empty();
                            let archive = unsafe { &mut *(&raw mut SYSTEM) };
                            #[cfg(feature = "initramfs-failure-test")]
                            let before_import = allocator::heap_stats();
                            let build_started = timer::ticks();
                            #[cfg(feature = "initramfs-failure-test")]
                            let built = if fixture_mode == 3 {
                                build_under_heap_pressure(archive, &index, &bytes)
                            } else {
                                archive.try_build(&index, &bytes)
                            };
                            #[cfg(not(feature = "initramfs-failure-test"))]
                            let built = archive.try_build(&index, &bytes);
                            let build_ticks = timer::ticks().wrapping_sub(build_started);
                            let mount_attempted = built.is_ok();
                            let mount_started = timer::ticks();
                            let result = built.and_then(|()| {
                                #[cfg(feature = "initramfs-failure-test")]
                                if fixture_mode == 2 {
                                    return filesystem.mount_system_failure_fixture(archive);
                                }
                                filesystem.mount_system(archive)
                            });
                            let mount_ticks = timer::ticks().wrapping_sub(mount_started);
                            {
                                use core::fmt::Write;
                                let _ = writeln!(
                                    io::serial::SerialWriter,
                                    "ROSTI: image timing build_ticks={} hz={}",
                                    build_ticks,
                                    timer::TIMER_HZ
                                );
                                if mount_attempted {
                                    let _ = writeln!(
                                        io::serial::SerialWriter,
                                        "ROSTI: image timing mount_ticks={} hz={}",
                                        mount_ticks,
                                        timer::TIMER_HZ
                                    );
                                }
                            }
                            #[cfg(feature = "initramfs-failure-test")]
                            if matches!(fixture_mode, 1 | 2) && result.is_err() {
                                let after_import = allocator::heap_stats();
                                if after_import.used == before_import.used
                                    && after_import.live_allocs == before_import.live_allocs
                                {
                                    io::serial::puts(
                                        "ROSTI: unpublished initramfs snapshot released\n",
                                    );
                                } else {
                                    io::serial::puts(
                                        "ROSTI: initramfs rollback accounting FAILED\n",
                                    );
                                }
                            }
                            match result {
                                Ok(()) => io::serial::puts(
                                    "ROSTI: initramfs trusted; mounted at /system\n",
                                ),
                                Err(error) => {
                                    use core::fmt::Write;
                                    let _ = writeln!(
                                        io::serial::SerialWriter,
                                        "ROSTI: initramfs publication rejected: {}; RAMFS recovery",
                                        error
                                    );
                                }
                            }
                        }
                        Err(error) => {
                            use core::fmt::Write;
                            let _ = writeln!(
                                io::serial::SerialWriter,
                                "ROSTI: initramfs archive rejected: {:?}; RAMFS recovery",
                                error
                            );
                        }
                    }
                }
                Err(error) => {
                    use core::fmt::Write;
                    let _ = writeln!(
                        io::serial::SerialWriter,
                        "ROSTI: initramfs copy rejected: {:?}; RAMFS recovery",
                        error
                    );
                }
            }
        }
    }

    // Never format at boot. Unknown/corrupt owned media fails closed while the
    // independent RAMFS recovery shell remains available. Unmarked disks are
    // not probed as filesystems and cannot be modified by this kernel. A
    // rejected boot inventory keeps the storage gate closed: no mount attempt
    // runs against media under untrusted metadata.
    if multiboot::inventory::storage_allowed() && disk.test_owned() {
        // SAFETY: BACKEND is borrowed once at boot and, after attachment, only
        // through FILESYSTEM's exclusive reference. A failed mount is not
        // retried through this static; IRQs never access either object.
        let backend = unsafe { &mut *(&raw mut BACKEND) };
        match backend
            .mount_in_place()
            .and_then(|()| filesystem.mount_backend(backend))
        {
            Ok(()) => io::serial::puts("ROSTI: RostiFS mounted at /mnt/rosti\n"),
            Err(error) => {
                use core::fmt::Write;
                let _ = writeln!(
                    io::serial::SerialWriter,
                    "ROSTI: RostiFS mount rejected: {}",
                    error
                );
            }
        }
    }
    io::serial::puts("ROSTI: boot complete\n");
    shell::banner();

    #[cfg(feature = "paging-fault-test")]
    unsafe {
        #[cfg(not(feature = "paging-write-fault-test"))]
        {
            io::serial::puts("ROSTI: fault test trigger (unmapped read)\n");
            core::arch::asm!("mov eax, dword ptr [0xfffff000]", out("eax") _);
        }
        #[cfg(feature = "paging-write-fault-test")]
        {
            io::serial::puts("ROSTI: fault test trigger (null write)\n");
            core::arch::asm!("mov dword ptr [0], 1");
        }
        panic!("page fault test unexpectedly returned");
    }

    // Idle properly: hlt parks the CPU until the next interrupt instead of
    // burning power in an uncontrolled busy loop. Interrupts stay enabled, so
    // keyboard/timer events wake the loop; hlt itself cannot be executed with
    // interrupts disabled (it would halt forever), so we never cli here.
    loop {
        if !shell::poll(filesystem, descriptors, &mut cwd, &mut disk) {
            unsafe {
                core::arch::asm!("hlt");
            }
        }
    }
}
