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
mod interrupt;
mod io;
mod kbd;
mod memory;
mod multiboot;
mod reboot;
mod shell;
mod storage;
mod timer;
mod utils;

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

#[cfg(not(test))]
#[unsafe(no_mangle)]
/// # Safety
/// Must only be entered by a multiboot-compliant bootloader in 32-bit
/// protected mode. `info` must be a valid pointer to a multiboot info struct
/// (guaranteed by the multiboot spec when `magic == 0x2badb002`).
pub unsafe extern "C" fn kernel_main(magic: u32, info: *const multiboot::BootInfo) -> ! {
    io::serial::init();
    io::serial::puts("ROSTI: entered kernel_main\n");

    io::vga::init_writer();
    if magic != 0x2badb002 {
        panic!("Not booted from multiboot")
    }

    unsafe {
        // init the allocator BEFORE printing the mmap: print_mmap_entries
        // allocates a Vec, which requires a working global allocator.
        io::serial::puts("DBG: alloc init\n");
        allocator::ALLOC.lock().init(info);
        io::serial::puts("DBG: mmap print\n");
        (*info).print_mmap_entries();
        io::serial::puts("DBG: mmap printed\n");
        // capture validated memory info for the shell's `mem` command
        let mut entries = (*info).get_mmap_entries();
        // Reserved entries override usable coverage in the frame allocator.
        // Include the actual mmap buffer, boot modules and optional metadata,
        // not just one page surrounding the BootInfo header.
        for (start, end) in (*info).reserved_ranges() {
            entries.push(multiboot::MmapEntry {
                size: 20,
                base_addr: start,
                length: end - start,
                type_: 2,
            });
        }
        io::serial::puts("DBG: mmap parsed\n");
        let total_kb: u64 = entries
            .iter()
            .filter(|e| e.type_ == 1)
            .map(|e| e.length / 1024)
            .sum();
        shell::set_mem_info(total_kb, allocator::bootstrap_heap_bounds().0 as u64);
        io::serial::puts("DBG: mem info set\n");

        // Capture bump bounds once. SpinMutex is NOT reentrant: locking ALLOC
        // again inside prepare()'s arguments while the set_mem_info guard is
        // still alive deadlocks the boot (this was the Phase 4 hang).
        let (bump_start, bump_end) = {
            let _bump = allocator::ALLOC.lock();
            let (s, e) = allocator::bootstrap_heap_bounds();
            (s as u64, e as u64)
        };

        // Physical frame allocator + page tables. Paging is NOT enabled yet:
        // the IDT must be loaded first so vector 14 can handle any fault.
        match memory::prepare(&entries, info as u64, bump_start, bump_end) {
            Ok(window) => {
                // Copy stats under one guard: multiple lock() temporaries in
                // the same println! live until the call returns and deadlock.
                let (total_frames, reserved_frames, free_frames) = {
                    let fa = memory::FRAME_ALLOC.lock();
                    let stats = fa.stats();
                    (stats.total_frames, stats.reserved_frames, stats.free_frames)
                };
                println!(
                    "frame allocator: {} frames total, {} reserved, {} free",
                    total_frames, reserved_frames, free_frames
                );
                println!(
                    "paging window: {:#010x} (page tables built, validated)",
                    window
                );
            }
            Err(missing) => {
                io::serial::puts("paging validation FAILED, paging left disabled:\n");
                for m in &missing {
                    io::serial::puts(m);
                    io::serial::putc(b'\n');
                }
            }
        }
    }
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

    // Never format at boot. Unknown/corrupt owned media fails closed while the
    // independent RAMFS recovery shell remains available. Unmarked disks are
    // not probed as filesystems and cannot be modified by this kernel.
    if disk.test_owned() {
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
