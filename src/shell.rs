//! Minimal interactive text console. Consumes raw scan codes from the
//! keyboard ring buffer (filled by the ISR), decodes them, echoes, and runs
//! fixed-size-line commands. No allocation, no locks — main-path only.

use crate::io;
use crate::kbd::{self, KEY_BACKSPACE, KEY_ENTER, Modifiers};
use crate::{print, println};

const LINE_MAX: usize = 128;

static mut LINE: [u8; LINE_MAX] = [0; LINE_MAX];
static mut LINE_LEN: usize = 0;
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
pub fn poll() -> bool {
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
            run_command();
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
            }
            // overflow: silently drop further input on this line
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

fn run_command() {
    let line = unsafe { (&raw mut LINE).as_mut().expect("line buffer") };
    let len = unsafe { LINE_LEN };
    // Reset on every dispatch, including an empty/whitespace-only command.
    // Otherwise the next Backspace can erase the freshly printed prompt.
    unsafe { LINE_LEN = 0 };
    let line = &line[..len];
    let cmd = core::str::from_utf8(line).unwrap_or("");
    let trimmed = cmd.trim();
    if trimmed.is_empty() {
        return;
    }

    let (name, rest) = match trimmed.find(' ') {
        Some(i) => (&trimmed[..i], trimmed[i + 1..].trim()),
        None => (trimmed, ""),
    };

    match name {
        "help" => {
            say("commands: help clear version mem cpu uptime echo reboot");
        }
        "clear" => {
            crate::io::vga::clear_console();
        }
        "version" => {
            say("Rosti kernel v0.1.0 (i686, multiboot v1)");
        }
        "mem" => {
            if unsafe { MEM_TOTAL_KB } == 0 {
                println!("no validated memory map captured");
            } else {
                println!("usable memory: {} KB", unsafe { MEM_TOTAL_KB });
                println!("allocator block base: {:#08x}", unsafe { MEM_BLOCK_BASE });
                let fa = crate::memory::FRAME_ALLOC.lock();
                if fa.is_initialized() {
                    let s = fa.stats();
                    println!(
                        "frames: total {} reserved {} free {} allocated {}",
                        s.total_frames, s.reserved_frames, s.free_frames, s.allocated_frames
                    );
                    println!(
                        "frame rejects: double frees {} invalid frees {}",
                        s.double_frees, s.invalid_frees
                    );
                    println!("page size: {} bytes", crate::memory::paging::PAGE_SIZE);
                    println!(
                        "paging: {}",
                        if crate::memory::paging_enabled() {
                            "enabled"
                        } else {
                            "disabled"
                        }
                    );
                } else {
                    println!("frame allocator: not initialized");
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
        "reboot" => {
            println!("rebooting...");
            crate::reboot::reboot();
        }
        _ => {
            println!("unknown command: {} (try 'help')", name);
        }
    }
}
