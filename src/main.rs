#![warn(clippy::all)]
#![cfg_attr(not(test), no_std)]
#![cfg_attr(not(test), no_main)]
#![feature(abi_x86_interrupt)]

use core::arch::global_asm;
use core::panic::PanicInfo;

extern crate alloc;

mod allocator;
mod cpu;
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

    println!("ps2 init enable");
    timer::init();
    io::serial::puts("ROSTI: boot complete\n");

    shell::banner();

    // Filesystem metadata lives in static storage, not the 16 KiB boot stack.
    // Exactly one main-loop owner; IRQ handlers never access this instance.
    static mut FILESYSTEM: fs::RamFs = fs::RamFs::new();
    let filesystem = unsafe { &mut *(&raw mut FILESYSTEM) };
    let mut cwd = fs::NodeId::ROOT;

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
        if !shell::poll(filesystem, &mut cwd) {
            unsafe {
                core::arch::asm!("hlt");
            }
        }
    }
}
