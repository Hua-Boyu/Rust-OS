#![warn(clippy::all)]
#![cfg_attr(not(test), no_std)]
#![cfg_attr(not(test), no_main)]
#![feature(abi_x86_interrupt)]

use core::arch::global_asm;
use core::panic::PanicInfo;

extern crate alloc;

mod allocator;
mod cpu;
mod gdt;
mod interrupt;
mod io;
mod kbd;
mod multiboot;
mod reboot;
mod shell;
mod timer;
mod utils;

#[cfg(not(test))]
global_asm!(include_str!("boot.s"), options(att_syntax));

#[cfg(not(test))]
#[global_allocator]
static ALLOC: utils::mutex::SpinMutex<allocator::BumpAlloc> =
    utils::mutex::SpinMutex::new(allocator::BumpAlloc::new());

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
        ALLOC.lock().init(info);
        (*info).print_mmap_entries();
        // capture validated memory info for the shell's `mem` command
        let entries = (*info).get_mmap_entries();
        let total_kb: u64 = entries
            .iter()
            .filter(|e| e.type_ == 1)
            .map(|e| e.length / 1024)
            .sum();
        shell::set_mem_info(total_kb, ALLOC.lock().start as u64);
    }
    println!("hi");

    gdt::init_gdt();
    interrupt::init_idt(&mut PORT_MANAGER.lock());

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

    // Idle properly: hlt parks the CPU until the next interrupt instead of
    // burning power in an uncontrolled busy loop. Interrupts stay enabled, so
    // keyboard/timer events wake the loop; hlt itself cannot be executed with
    // interrupts disabled (it would halt forever), so we never cli here.
    loop {
        if !shell::poll() {
            unsafe {
                core::arch::asm!("hlt");
            }
        }
    }
}
