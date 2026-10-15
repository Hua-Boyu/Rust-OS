// See: <https://www.gnu.org/software/grub/manual/multiboot/multiboot.html>
//
// Struct members are named the same as in the multiboot spec, howeer those
// names that are reserved in Rust are postfixed with an underscore.
// Structs look contrived but they are directly from the multiboot spec.

#![allow(dead_code)]

#[cfg(test)]
use crate::println;
extern crate alloc;
use alloc::vec::Vec;

#[path = "boot_inventory.rs"]
pub mod inventory;

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
    vbe_mode: u16,
    vbe_interface_seg: u16,
    vbe_interface_off: u16,
    vbe_interface_len: u16,

    framebuffer_addr: u64,
    framebuffer_pitch: u32,
    framebuffer_width: u32,
    framebuffer_height: u32,
    framebuffer_bpp: u8,
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

#[cfg(test)]
impl BootInfo {
    /// Bootloader-owned regions, copied before page tables can reuse frames.
    /// # Safety
    /// This must be a valid Multiboot structure, including any module table.
    pub unsafe fn reserved_ranges(&self) -> Vec<(u64, u64)> {
        let mut ranges = Vec::new();
        let mut add = |start: u64, length: u64| {
            if length != 0 {
                let end = start.checked_add(length).expect("boot region overflow");
                ranges.push((start, end));
            }
        };
        add(
            self as *const Self as u64,
            core::mem::size_of::<Self>() as u64,
        );
        let flags = self.flags;
        if flags & (1 << 6) != 0 {
            add(self.mmap_addr as u64, self.mmap_length as u64);
        }
        // Conservatively keep one maximum supported string buffer (4 KiB).
        if flags & (1 << 2) != 0 && self.cmdline != 0 {
            add(self.cmdline as u64, 4096);
        }
        if flags & (1 << 9) != 0 && self.boot_loader_name != 0 {
            add(self.boot_loader_name as u64, 4096);
        }
        if flags & (1 << 3) != 0 {
            let count = self.mods_count;
            assert!(count <= 1024, "too many boot modules");
            add(self.mods_addr as u64, count as u64 * 16);
            for i in 0..count {
                let addr = (self.mods_addr as u64 + i as u64 * 16) as *const [u32; 4];
                let module = unsafe { addr.read_unaligned() };
                assert!(module[1] >= module[0], "invalid boot module range");
                add(module[0] as u64, (module[1] - module[0]) as u64);
                if module[2] != 0 {
                    add(module[2] as u64, 4096);
                }
            }
        }
        let syms = self.syms;
        if flags & (1 << 4) != 0 {
            add(syms[2] as u64, syms[0] as u64 + syms[1] as u64);
        } else if flags & (1 << 5) != 0 {
            add(syms[2] as u64, syms[0] as u64 * syms[1] as u64);
        }
        if flags & (1 << 7) != 0 {
            add(self.drives_addr as u64, self.drives_length as u64);
        }
        if flags & (1 << 8) != 0 {
            add(self.config_table as u64, 4096);
        }
        if flags & (1 << 10) != 0 {
            add(self.apm_table as u64, 20);
        }
        if flags & (1 << 11) != 0 {
            add(self.vbe_control_info as u64, 512);
            add(self.vbe_mode_info as u64, 256);
        }
        if flags & (1 << 12) != 0 {
            add(
                self.framebuffer_addr,
                self.framebuffer_pitch as u64 * self.framebuffer_height as u64,
            );
        }
        ranges
    }

    /// Parse the memory map per the multiboot spec: entries are
    /// variable-length. Each entry's `size` field counts everything AFTER
    /// itself, so a full entry occupies `size + 4` bytes. Dividing
    /// `mmap_length` by a fixed struct size is wrong for non-standard
    /// entry sizes (and for trailing partial entries).
    pub unsafe fn get_mmap_entries(&self) -> Vec<MmapEntry> {
        assert!(self.flags & (1 << 6) != 0, "Multiboot memory map required");
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
#[cfg(test)]
pub fn parse_mmap(bytes: &[u8]) -> Vec<MmapEntry> {
    let mut entries = Vec::new();
    let mut off = 0usize;
    while off + 4 <= bytes.len() {
        let size = u32::from_le_bytes(bytes[off..off + 4].try_into().unwrap()) as usize;
        // spec minimum: base(8) + length(8) + type(4) = 20 bytes after size
        if size < 20 || size > bytes.len() - off - 4 {
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
#[cfg(test)]
pub fn find_usable_block(bytes: &[u8]) -> Option<MmapEntry> {
    // Legacy allocation-free query: reject truncated wire records before
    // searching; individual unusable/overflowing ranges are still skipped.
    // Boot initialization uses inventory::parse, which rejects the entire
    // malformed inventory, including overflowing physical ranges.
    let mut checked = 0usize;
    while checked < bytes.len() {
        if bytes.len() - checked < 4 {
            return None;
        }
        let size = u32::from_le_bytes(bytes[checked..checked + 4].try_into().unwrap()) as usize;
        if size < 20 || size > bytes.len() - checked - 4 {
            return None;
        }
        checked += size + 4;
    }
    let mut off = 0usize;
    while off + 4 <= bytes.len() {
        let size = u32::from_le_bytes(bytes[off..off + 4].try_into().unwrap()) as usize;
        if size < 20 || size > bytes.len() - off - 4 {
            break;
        }
        let base_addr = u64::from_le_bytes(bytes[off + 4..off + 12].try_into().unwrap());
        let length = u64::from_le_bytes(bytes[off + 12..off + 20].try_into().unwrap());
        let type_ = u32::from_le_bytes(bytes[off + 20..off + 24].try_into().unwrap());
        if type_ == 1 && base_addr != 0 && length != 0 && base_addr.checked_add(length).is_some() {
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

#[cfg(test)]
mod phase4_tests {
    use super::*;

    #[test]
    fn usable_discovery_rejects_malformed_tail_instead_of_trusting_prefix() {
        let mut bytes = Vec::new();
        bytes.extend(20u32.to_le_bytes());
        bytes.extend(0x100000u64.to_le_bytes());
        bytes.extend(0x100000u64.to_le_bytes());
        bytes.extend(1u32.to_le_bytes());
        bytes.push(0xff);
        assert!(find_usable_block(&bytes).is_none());
    }

    #[test]
    fn bootinfo_layout_matches_multiboot_wire_format() {
        assert_eq!(core::mem::size_of::<BootInfo>(), 116);
        assert_eq!(core::mem::offset_of!(BootInfo, framebuffer_pitch), 96);
        assert_eq!(core::mem::offset_of!(BootInfo, framebuffer_bpp), 108);
    }

    #[test]
    fn bootloader_metadata_is_reserved_by_flags() {
        let mut info: BootInfo = unsafe { core::mem::zeroed() };
        info.flags = (1 << 6) | (1 << 2) | (1 << 9);
        info.mmap_addr = 0x10000;
        info.mmap_length = 5000;
        info.cmdline = 0x20000;
        info.boot_loader_name = 0x30000;
        let ranges = unsafe { info.reserved_ranges() };
        assert!(ranges.contains(&(0x10000, 0x10000 + 5000)));
        assert!(ranges.contains(&(0x20000, 0x21000)));
        assert!(ranges.contains(&(0x30000, 0x31000)));
        assert!(ranges.contains(&(
            (&info as *const BootInfo as u64),
            (&info as *const BootInfo as u64) + 116
        )));
    }
}
