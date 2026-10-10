// See: <https://www.gnu.org/software/grub/manual/multiboot/multiboot.html>
//
// Struct members are named the same as in the multiboot spec, howeer those
// names that are reserved in Rust are postfixed with an underscore.
// Structs look contrived but they are directly from the multiboot spec.

#![allow(dead_code)]

use crate::println;
extern crate alloc;
use alloc::vec::Vec;

#[repr(C, packed)]
pub struct BootInfo {
    flags: u32,

    mem_lower: u32,
    mem_upper: u32,

    boot_device: u32,

    cmdline: u32,

    mods_count: u32,
    mods_addr: u32,

    syms: [u32; 4],

    pub mmap_length: u32,
    pub mmap_addr: u32,
    drives_length: u32,
    drives_addr: u32,

    config_table: u32,

    boot_loader_name: u32,

    apm_table: u32,

    vbe_control_info: u32,
    vbe_mode_info: u32,
    vbe_mode: u32,
    vbe_interface_seg: u16,
    vbe_interface_off: u16,
    vbe_interface_len: u16,

    framebuffer_addr: u64,
    framebuffer_pitch: u64,
    framebuffer_width: u32,
    framebuffer_height: u32,
    framebuffer_bpp: u32,
    framebuffer_type: u8,
    color_info: [u8; 6],
}

#[derive(Clone, Copy)]
#[repr(C, packed)]
pub struct MmapEntry {
    pub size: u32,
    pub base_addr: u64,
    pub length: u64,
    pub type_: u32, // name conflicts with rust keyword
}

impl BootInfo {
    /// Parse the memory map per the multiboot spec: entries are
    /// variable-length. Each entry's `size` field counts everything AFTER
    /// itself, so a full entry occupies `size + 4` bytes. Dividing
    /// `mmap_length` by a fixed struct size is wrong for non-standard
    /// entry sizes (and for trailing partial entries).
    pub unsafe fn get_mmap_entries(&self) -> Vec<MmapEntry> {
        unsafe {
            parse_mmap(core::slice::from_raw_parts(
                self.mmap_addr as *const u8,
                self.mmap_length as usize,
            ))
        }
    }

    #[allow(clippy::cast_precision_loss)]
    pub unsafe fn print_mmap_entries(&self) {
        println!("----- multiboot mmap -----");
        let mmap_entries = unsafe { self.get_mmap_entries() };
        println!("num entries: {}", mmap_entries.len());

        let mut total_sz: u64 = 0;
        for entry in &mmap_entries {
            println!(
                "size: {}, len: {}K, addr: {:#04x}, typ: {}",
                { entry.size },
                { entry.length } as f64 / 1024.0,
                { entry.base_addr },
                { entry.type_ }
            );
            if entry.type_ == 1 {
                total_sz += entry.length;
            }
        }
        println!("total size: {}K", total_sz as f64 / 1024.0);
    }
}

/// Pure, host-testable parser: `bytes` is the raw mmap region.
pub fn parse_mmap(bytes: &[u8]) -> Vec<MmapEntry> {
    let mut entries = Vec::new();
    let mut off = 0usize;
    while off + 4 <= bytes.len() {
        let size = u32::from_le_bytes(bytes[off..off + 4].try_into().unwrap()) as usize;
        // spec minimum: base(8) + length(8) + type(4) = 20 bytes after size
        if size < 20 || off + 4 + size > bytes.len() {
            break; // malformed or truncated entry: stop, don't read OOB
        }
        let base_addr = u64::from_le_bytes(bytes[off + 4..off + 12].try_into().unwrap());
        let length = u64::from_le_bytes(bytes[off + 12..off + 20].try_into().unwrap());
        let type_ = u32::from_le_bytes(bytes[off + 20..off + 24].try_into().unwrap());
        entries.push(MmapEntry {
            size: size as u32,
            base_addr,
            length,
            type_,
        });
        off += 4 + size;
    }
    entries
}

/// Allocation-free variant used by the allocator itself: parse_mmap needs a
/// working global allocator, which is exactly what init() is trying to set up
/// (SpinMutex is not reentrant, so calling parse_mmap from inside init()
/// would deadlock).
pub fn find_usable_block(bytes: &[u8]) -> Option<MmapEntry> {
    let mut off = 0usize;
    while off + 4 <= bytes.len() {
        let size = u32::from_le_bytes(bytes[off..off + 4].try_into().unwrap()) as usize;
        if size < 20 || off + 4 + size > bytes.len() {
            break;
        }
        let base_addr = u64::from_le_bytes(bytes[off + 4..off + 12].try_into().unwrap());
        let length = u64::from_le_bytes(bytes[off + 12..off + 20].try_into().unwrap());
        let type_ = u32::from_le_bytes(bytes[off + 20..off + 24].try_into().unwrap());
        if type_ == 1 && base_addr != 0 {
            return Some(MmapEntry {
                size: size as u32,
                base_addr,
                length,
                type_,
            });
        }
        off += 4 + size;
    }
    None
}
