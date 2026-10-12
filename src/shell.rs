//! Minimal interactive text console. Consumes raw scan codes from the
//! keyboard ring buffer (filled by the ISR), decodes them, echoes, and runs
//! fixed-size-line commands. Filesystem allocations are main-context only.

use crate::io;
use crate::kbd::{self, KEY_BACKSPACE, KEY_ENTER, Modifiers};
use crate::{print, println};

// Main-context, allocation-free dual console output. Never used in an ISR.
macro_rules! report {
    ($($arg:tt)*) => {{
        use core::fmt::Write;
        println!($($arg)*);
        let _ = writeln!(io::serial::SerialWriter, $($arg)*);
    }};
}

const LINE_MAX: usize = 128;

static mut LINE: [u8; LINE_MAX] = [0; LINE_MAX];
static mut LINE_LEN: usize = 0;
static mut LINE_OVERFLOW: bool = false;
static mut INPUT_LOST: bool = false;
static mut MODS: Modifiers = Modifiers::new();

// Set by kernel_main from the multiboot mmap (validated memory info).
static mut MEM_TOTAL_KB: u64 = 0;
static mut MEM_BLOCK_BASE: u64 = 0;

pub fn set_mem_info(total_kb: u64, block_base: u64) {
    unsafe {
        MEM_TOTAL_KB = total_kb;
        MEM_BLOCK_BASE = block_base;
    }
}

pub fn banner() {
    println!("ROSTI OS");
    println!("32-bit Rust Experimental Kernel");
    println!();
    println!("Memory initialization: OK");
    println!("GDT: OK");
    println!("IDT: OK");
    println!("PIC: OK");
    println!("Keyboard: Ready");
    println!();
    // Serial mirror so the Proxmox serial console can observe the shell.
    io::serial::puts("ROSTI OS\n32-bit Rust Experimental Kernel\n\n");
    io::serial::puts("Memory initialization: OK\nGDT: OK\nIDT: OK\nPIC: OK\nKeyboard: Ready\n\n");
    print_prompt();
}

fn print_prompt() {
    print!("rosti>");
    io::serial::puts("rosti>");
}

/// Process one pending keyboard event. Returns true if work was done.
pub fn poll(
    fs: &mut impl crate::fs::Vfs,
    table: &mut crate::fd::FdTable,
    cwd: &mut crate::fs::NodeId,
) -> bool {
    if kbd::RING.recover_overflow() {
        unsafe {
            LINE_OVERFLOW = true;
            INPUT_LOST = true;
            MODS = Modifiers::new(); // lost key releases must not stick Shift
        }
    }
    let Some(sc) = kbd::RING.pop() else {
        return false;
    };

    let mods = unsafe { (&raw mut MODS).as_mut().expect("modifiers") };
    if mods.apply(sc) {
        return true;
    }
    let (shift, caps) = (mods.shift, mods.caps);

    match sc {
        KEY_BACKSPACE => {
            unsafe {
                if LINE_LEN > 0 {
                    LINE_LEN -= 1;
                    LINE[LINE_LEN] = 0;
                    io::vga::erase_previous();
                    // Terminal backspace moves left; blank and move left
                    // again so serial consoles match the VGA edit.
                    io::serial::puts("\x08 \x08");
                }
            }
            return true;
        }
        KEY_ENTER => {
            println!();
            // Mirror the line-ending to serial so echoed input and command
            // output have consistent line boundaries on the serial console.
            io::serial::putc(b'\n');
            run_command(fs, table, cwd);
            print_prompt();
            return true;
        }
        _ => {}
    }

    if let Some(ch) = kbd::decode_set1(sc, shift, caps) {
        unsafe {
            if LINE_LEN < LINE_MAX {
                LINE[LINE_LEN] = ch as u8;
                LINE_LEN += 1;
                print!("{}", ch);
                // Mirror the echo to serial so the harness can observe the
                // decode stage (VGA writes are not visible on the serial log).
                io::serial::putc(ch as u8);
            } else {
                // Latch until Enter: never execute a truncated destructive
                // command, even if the user backspaces after overflow.
                LINE_OVERFLOW = true;
            }
        }
        return true;
    }
    false
}

fn say(s: &str) {
    println!("{}", s);
    io::serial::puts(s);
    io::serial::puts("\n");
}

fn run_command(
    fs: &mut impl crate::fs::Vfs,
    table: &mut crate::fd::FdTable,
    cwd: &mut crate::fs::NodeId,
) {
    let line = unsafe { (&raw mut LINE).as_mut().expect("line buffer") };
    let len = unsafe { LINE_LEN };
    // Reset on every dispatch, including an empty/whitespace-only command.
    // Otherwise the next Backspace can erase the freshly printed prompt.
    let overflow = unsafe {
        LINE_LEN = 0;
        core::mem::replace(&mut *(&raw mut LINE_OVERFLOW), false)
    };
    let input_lost = unsafe { core::mem::replace(&mut *(&raw mut INPUT_LOST), false) };
    if overflow {
        say(if input_lost {
            "shell: keyboard input lost; command not executed"
        } else {
            "shell: line too long; command not executed"
        });
        return;
    }
    let line = &line[..len];
    let cmd = core::str::from_utf8(line).unwrap_or("");
    let (name, rest) = crate::fs_commands::split_word(cmd);
    if name.is_empty() {
        return;
    }
    if crate::fs_commands::run(fs, table, cwd, name, rest, &mut |args| {
        use core::fmt::Write;
        io::vga::print_(args);
        let _ = io::serial::SerialWriter.write_fmt(args);
    }) {
        return;
    }

    match name {
        "help" => {
            say(
                "commands: help clear version mem cpu uptime echo reboot pwd ls cd mkdir touch cat write append rm rmdir stat fsstress fdlist",
            );
        }
        "clear" => {
            crate::io::vga::clear_console();
        }
        "version" => {
            say("Rosti kernel v0.1.0 (i686, multiboot v1)");
        }
        "mem" => {
            if unsafe { MEM_TOTAL_KB } == 0 {
                report!("no validated memory map captured");
            } else {
                report!("usable memory: {} KB", unsafe { MEM_TOTAL_KB });
                report!("allocator block base: {:#08x}", unsafe { MEM_BLOCK_BASE });

                // Copy frame stats under one guard, then release before the
                // heap guard: nested locks on the same mutex deadlock, and
                // heap allocation during printing could re-enter the heap.
                let fa_stats = {
                    let fa = crate::memory::FRAME_ALLOC.lock();
                    if fa.is_initialized() {
                        Some(*fa.stats())
                    } else {
                        None
                    }
                };
                let fs_stats = fs.stats();
                report!("FS nodes: {}", fs_stats.nodes);
                report!("FS storage: {} bytes", fs_stats.allocated_bytes);
                report!("FS logical bytes: {}", fs_stats.logical_bytes);
                report!("FS metadata: {} bytes (fixed)", fs_stats.metadata_bytes);
                let fd_stats = table.stats();
                report!(
                    "Descriptors: open {} records {} opens {} closes {} denials {} stale {}",
                    fd_stats.open_slots,
                    fd_stats.open_records,
                    fd_stats.opens,
                    fd_stats.closes,
                    fd_stats.denials,
                    fd_stats.stale_rejections
                );
                report!("Physical memory:");
                if let Some(s) = fa_stats {
                    report!("Total frames: {}", s.total_frames);
                    report!("Free frames: {}", s.free_frames);
                    report!("Allocated frames: {}", s.allocated_frames);
                    report!("Reserved frames: {}", s.reserved_frames);
                    report!(
                        "Frame rejects: double frees {} invalid frees {}",
                        s.double_frees,
                        s.invalid_frees
                    );
                } else {
                    report!("frame allocator: not initialized");
                }

                report!();
                report!("Virtual memory:");
                report!(
                    "Paging: {}",
                    if crate::memory::paging_enabled() {
                        "enabled"
                    } else {
                        "disabled"
                    }
                );
                report!(
                    "Page directory: {:#010x}",
                    crate::memory::page_directory().unwrap_or(0)
                );
                report!("Mapped pages: {}", crate::memory::mapped_pages());
                report!("Page size: {} bytes", crate::memory::paging::PAGE_SIZE);

                report!();
                report!("Kernel heap:");
                let hs = crate::allocator::heap_stats();
                report!("Current capacity: {} bytes", hs.capacity);
                report!("Used: {} bytes", hs.used);
                report!("Free: {} bytes", hs.free);
                report!("Failed allocations: {}", hs.failed_allocs);
                report!("Live allocations: {}", hs.live_allocs);
                report!("Invalid deallocs: {}", hs.invalid_deallocs);
                report!(
                    "Free blocks: {} (largest {} bytes)",
                    hs.free_blocks,
                    hs.largest_free
                );
                report!("Alignment waste: {} bytes", hs.waste);
                report!("Growth pages: {}", hs.growth_pages);

                report!();
                report!("Page faults: {}", crate::interrupt::page_fault_count());
                if let Some(f) = crate::interrupt::last_page_fault() {
                    report!(
                        "Last fault: cr2={:#010x} present={} write={} user={} fetch={}",
                        f.cr2,
                        f.present,
                        f.write,
                        f.user,
                        f.fetch
                    );
                }
            }
        }
        "cpu" => match crate::cpu::vendor() {
            Some(v) => println!("cpu: {}", v),
            None => println!("cpu: CPUID not available on this target"),
        },
        "uptime" => {
            say(&::alloc::format!(
                "ticks: {}, uptime: {} s (PIT {} Hz)",
                crate::timer::ticks(),
                crate::timer::uptime_secs(),
                crate::timer::TIMER_HZ
            ));
        }
        "echo" => {
            say(rest);
        }
        "fsstress" => {
            if rest.trim().is_empty() {
                crate::fs_stress::run(fs, &mut |args| {
                    use core::fmt::Write;
                    io::vga::print_(args);
                    let _ = io::serial::SerialWriter.write_fmt(args);
                });
            } else {
                say("fs: invalid path");
            }
        }
        "reboot" => {
            println!("rebooting...");
            crate::reboot::reboot();
        }
        _ => {
            println!("unknown command: {} (try 'help')", name);
        }
    }
}
