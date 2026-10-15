//! Bounded Multiboot inventory. No borrowed bootloader pointers escape parsing.
//! Bootstrap header/mmap must be in conventional RAM [4 KiB, 640 KiB).
//! After the map is checked, other metadata must be in described RAM, outside
//! the kernel and growth window. Unsupported placements fail closed, never probe
//! MMIO. All metadata and module buffers remain pinned until reboot.
use super::MmapEntry;
use alloc::vec::Vec;

pub const MAGIC: u32 = 0x2badb002;
const MAX_MMAP: usize = 128;
const MAX_MODULES: usize = 32;
const MAX_STRING: u64 = 4096;
const LOW_END: u64 = 0xa0000;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum BootError {
    Magic,
    Flags,
    Address,
    Truncated,
    Map,
    Limit,
    Allocation,
    Module,
    String,
}

/// Maximum retained label bytes (excluding NUL). Physical metadata validation
/// still scans through the original 4096-byte bound, even for ineligible names.
pub const MAX_MODULE_NAME: usize = 63;
pub const INITRAMFS_LABEL: &str = "rosti.initramfs";

/// Owned printable ASCII only; never a truncated prefix or bootloader pointer.
/// Empty, oversized, non-ASCII and control-containing strings are ineligible.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct ModuleName {
    bytes: [u8; MAX_MODULE_NAME],
    len: u8,
}

impl ModuleName {
    const EMPTY: Self = Self {
        bytes: [0; MAX_MODULE_NAME],
        len: 0,
    };

    pub fn as_str(&self) -> Option<&str> {
        if self.len == 0 {
            None
        } else {
            core::str::from_utf8(&self.bytes[..self.len as usize]).ok()
        }
    }
}

/// Sanitized metadata, not permission to dereference physical memory. Consumers
/// must separately prove mapping/pinning before accessing any payload bytes.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct ModuleDescriptor {
    pub range: (u64, u64),
    pub name: ModuleName,
}

pub struct Inventory {
    pub entries: Vec<MmapEntry>,
    pub reservations: Vec<(u64, u64)>,
    /// Compatibility ranges in loader order.
    pub modules: Vec<(u64, u64)>,
    /// Parallel owned descriptors, also in loader order; one bounded Vec backing,
    /// no allocation per name and no MAX_MODULES-sized boot-stack array.
    pub module_descriptors: Vec<ModuleDescriptor>,
}

impl Inventory {
    /// Exact whole-label selection only. Missing/ineligible/other names are
    /// ignored; two exact matches always fail, independently of loader order.
    /// No physical reads, allocation, reservation release or global outcome
    /// mutation occurs here. The caller must handle ambiguity as a rejection.
    pub fn select_initramfs(&self) -> Result<Option<&ModuleDescriptor>, BootError> {
        let mut selected = None;
        for module in &self.module_descriptors {
            if module.name.as_str() == Some(INITRAMFS_LABEL) {
                if selected.is_some() {
                    return Err(BootError::Module);
                }
                selected = Some(module);
            }
        }
        Ok(selected)
    }
}

/// First-rejection-wins boot outcome, recorded by every parse attempt. The
/// shell/storage paths gate persistent-media work on this before dispatch, so
/// a rejected inventory cannot reach ATA writes through later code paths.
/// Single-owner boot context; host tests isolate it through a child process.
static BOOT_OUTCOME: core::sync::atomic::AtomicU8 = core::sync::atomic::AtomicU8::new(0);

pub fn outcome() -> Option<BootError> {
    use core::sync::atomic::Ordering;
    match BOOT_OUTCOME.load(Ordering::Acquire) {
        0 => None,
        1 => Some(BootError::Magic),
        2 => Some(BootError::Flags),
        3 => Some(BootError::Address),
        4 => Some(BootError::Truncated),
        5 => Some(BootError::Map),
        6 => Some(BootError::Limit),
        7 => Some(BootError::Allocation),
        8 => Some(BootError::Module),
        _ => Some(BootError::String),
    }
}

pub(crate) fn record(error: BootError) -> BootError {
    use core::sync::atomic::Ordering;
    let code = match error {
        BootError::Magic => 1,
        BootError::Flags => 2,
        BootError::Address => 3,
        BootError::Truncated => 4,
        BootError::Map => 5,
        BootError::Limit => 6,
        BootError::Allocation => 7,
        BootError::Module => 8,
        BootError::String => 9,
    };
    let _ = BOOT_OUTCOME.compare_exchange(0, code, Ordering::AcqRel, Ordering::Acquire);
    error
}

/// Persistent-storage gate: a rejected boot inventory must not reach ATA
/// probing, RostiFS mount, or raw shell disk writes. Boot context records the
/// outcome before shell dispatch; the gate is read-only afterwards.
pub fn storage_allowed() -> bool {
    outcome().is_none()
}

fn vector<T>(capacity: usize) -> Result<Vec<T>, BootError> {
    let mut v = Vec::new();
    v.try_reserve_exact(capacity)
        .map_err(|_| BootError::Allocation)?;
    Ok(v)
}

pub fn checked_mmap(bytes: &[u8]) -> Result<Vec<MmapEntry>, BootError> {
    if bytes.is_empty() || bytes.len() > MAX_MMAP * 256 {
        return Err(BootError::Limit);
    }
    let mut result = vector(MAX_MMAP)?;
    let mut off = 0;
    while off < bytes.len() {
        if bytes.len() - off < 4 {
            return Err(BootError::Truncated);
        }
        let size = word(bytes, off) as usize;
        if size < 20 || size > bytes.len() - off - 4 {
            return Err(BootError::Map);
        }
        if result.len() == MAX_MMAP {
            return Err(BootError::Limit);
        }
        let base_addr = u64::from_le_bytes(bytes[off + 4..off + 12].try_into().unwrap());
        let length = u64::from_le_bytes(bytes[off + 12..off + 20].try_into().unwrap());
        if base_addr.checked_add(length).is_none() {
            return Err(BootError::Address);
        }
        result.push(MmapEntry {
            size: size as u32,
            base_addr,
            length,
            type_: word(bytes, off + 20),
        });
        off += size + 4;
    }
    if !result.iter().any(|e| e.type_ == 1 && e.length != 0) {
        return Err(BootError::Map);
    }
    Ok(result)
}

fn word(bytes: &[u8], off: usize) -> u32 {
    u32::from_le_bytes(bytes[off..off + 4].try_into().unwrap())
}

fn span(start: u64, len: u64) -> Result<(u64, u64), BootError> {
    let end = start.checked_add(len).ok_or(BootError::Address)?;
    if start < 4096 || len == 0 || end > (1u64 << 32) {
        return Err(BootError::Address);
    }
    Ok((start, end))
}

fn overlaps(a: (u64, u64), b: (u64, u64)) -> bool {
    a.0 < a.1 && b.0 < b.1 && a.0 < b.1 && b.0 < a.1
}

fn ram(entries: &[MmapEntry], range: (u64, u64)) -> bool {
    // One complete usable record is required. Reserved records always win.
    entries
        .iter()
        .any(|e| e.type_ == 1 && e.base_addr <= range.0 && e.base_addr + e.length >= range.1)
        && !entries
            .iter()
            .any(|e| e.type_ != 1 && overlaps(range, (e.base_addr, e.base_addr + e.length)))
}

fn address(entries: &[MmapEntry], range: (u64, u64), kernel: (u64, u64)) -> Result<(), BootError> {
    if overlaps(range, kernel)
        || overlaps(
            range,
            (
                crate::memory::GROWTH_START as u64,
                crate::memory::GROWTH_END as u64,
            ),
        )
        || !ram(entries, range)
    {
        return Err(BootError::Address);
    }
    Ok(())
}

/// `read` is a bounded source abstraction: host fixtures refuse missing bytes.
/// The physical adapter below additionally relies on the trusted loader's flat
/// protected-mode RAM contract, NOT on a temporary early paging identity map
/// (CR0.PG is clear at this point). Bounds are proven before every callback.
pub fn parse<F>(magic: u32, info: u64, kernel: (u64, u64), read: F) -> Result<Inventory, BootError>
where
    F: FnMut(u64, &mut [u8]) -> Result<(), BootError>,
{
    parse_inner(magic, info, kernel, read).map_err(record)
}

fn parse_inner<F>(
    magic: u32,
    info: u64,
    kernel: (u64, u64),
    mut read: F,
) -> Result<Inventory, BootError>
where
    F: FnMut(u64, &mut [u8]) -> Result<(), BootError>,
{
    if magic != MAGIC {
        return Err(BootError::Magic);
    }
    let header_range = span(info, 88)?;
    if header_range.1 > LOW_END || overlaps(header_range, kernel) {
        return Err(BootError::Address);
    }
    let mut header = [0u8; 88];
    read(info, &mut header)?;
    let flags = word(&header, 0);
    if flags & (1 << 6) == 0 || flags & !0x1fff != 0 || flags & (3 << 4) == (3 << 4) {
        return Err(BootError::Flags);
    }
    // Obsolete BIOS config tables have no bounded length contract we support.
    if flags & (1 << 8) != 0 {
        return Err(BootError::Flags);
    }
    let mmap_len = word(&header, 44) as usize;
    if mmap_len == 0 || mmap_len > MAX_MMAP * 256 {
        return Err(BootError::Limit);
    }
    let mmap_range = span(word(&header, 48) as u64, mmap_len as u64)?;
    if mmap_range.1 > LOW_END || overlaps(mmap_range, kernel) {
        return Err(BootError::Address);
    }
    let mut bytes = vector(mmap_len)?;
    bytes.resize(mmap_len, 0);
    read(mmap_range.0, &mut bytes)?;
    let entries = checked_mmap(&bytes)?;
    // The loader's header/map may lie in low RAM marked reserved by firmware;
    // no other pointer gets this bootstrap exception.
    let mut inv = Inventory {
        entries,
        reservations: vector(128)?,
        modules: vector(MAX_MODULES)?,
        module_descriptors: vector(MAX_MODULES)?,
    };
    inv.reservations.push(header_range);
    inv.reservations.push(mmap_range);
    for (bit, off) in [(2, 16), (9, 64)] {
        if flags & (1 << bit) != 0 {
            string(&mut inv, word(&header, off) as u64, kernel, &mut read)?;
        }
    }
    if flags & (1 << 3) != 0 {
        let count = word(&header, 20) as usize;
        if count > MAX_MODULES {
            return Err(BootError::Limit);
        }
        if count != 0 {
            let table = span(word(&header, 24) as u64, (count * 16) as u64)?;
            address(&inv.entries, table, kernel)?;
            inv.reservations.push(table);
            for i in 0..count {
                let mut descriptor = [0u8; 16];
                read(table.0 + (i * 16) as u64, &mut descriptor)?;
                let range = (word(&descriptor, 0) as u64, word(&descriptor, 4) as u64);
                if range.1 <= range.0 || word(&descriptor, 12) != 0 {
                    return Err(BootError::Module);
                }
                address(&inv.entries, span(range.0, range.1 - range.0)?, kernel)?;
                if inv.modules.iter().any(|&r| overlaps(r, range))
                    || inv.reservations.iter().any(|&r| overlaps(r, range))
                {
                    return Err(BootError::Module);
                }
                inv.modules.push(range);
                inv.reservations.push(range);
                let name = word(&descriptor, 8) as u64;
                let name = if name != 0 {
                    string(&mut inv, name, kernel, &mut read)?
                } else {
                    ModuleName::EMPTY
                };
                inv.module_descriptors
                    .push(ModuleDescriptor { range, name });
            }
        }
    }
    for (bit, off, len_off) in [(7, 56, 52)] {
        if flags & (1 << bit) != 0 {
            let len = word(&header, len_off) as u64;
            if len != 0 {
                reserve(&mut inv, word(&header, off) as u64, len, kernel)?;
            }
        }
    }
    if flags & (3 << 4) != 0 {
        let a = word(&header, 28) as u64;
        let b = word(&header, 32) as u64;
        let len = if flags & (1 << 4) != 0 {
            if word(&header, 40) != 0 {
                return Err(BootError::Flags);
            }
            // addr includes the leading symbol-array size word. strsize
            // already includes its own size word; tabsize excludes this one.
            a.checked_add(b).and_then(|size| size.checked_add(4))
        } else {
            a.checked_mul(b)
        }
        .ok_or(BootError::Address)?;
        if len != 0 {
            reserve(&mut inv, word(&header, 36) as u64, len, kernel)?;
        }
    }
    if flags & (1 << 10) != 0 {
        reserve(&mut inv, word(&header, 68) as u64, 20, kernel)?;
    }
    if flags & (1 << 11) != 0 {
        reserve(&mut inv, word(&header, 72) as u64, 512, kernel)?;
        reserve(&mut inv, word(&header, 76) as u64, 256, kernel)?;
        let segment = u16::from_le_bytes(header[82..84].try_into().unwrap()) as u64;
        let offset = u16::from_le_bytes(header[84..86].try_into().unwrap()) as u64;
        let length = u16::from_le_bytes(header[86..88].try_into().unwrap()) as u64;
        if length != 0 {
            reserve(&mut inv, (segment << 4) + offset, length, kernel)?;
        }
    }
    // GRUB advertises the current VGA text framebuffer even when no graphics
    // mode was requested. Only the known VGA aperture is supported; arbitrary
    // linear framebuffer/MMIO pointers are never probed or made allocatable.
    if flags & (1 << 12) != 0 {
        let full_header = span(info, 116)?;
        if full_header.1 > LOW_END || overlaps(full_header, kernel) {
            return Err(BootError::Address);
        }
        let mut fb = [0u8; 28];
        read(info + 88, &mut fb).map_err(|_| BootError::Flags)?;
        let start = u64::from_le_bytes(fb[0..8].try_into().unwrap());
        let pitch = word(&fb, 8) as u64;
        let width = word(&fb, 12) as u64;
        let height = word(&fb, 16) as u64;
        if fb[21] != 2 || fb[20] != 16 || width == 0 || height == 0 || pitch != width * 2 {
            return Err(BootError::Flags);
        }
        let range = span(start, pitch.checked_mul(height).ok_or(BootError::Address)?)?;
        if range.0 < 0xb8000 || range.1 > 0xbc000 {
            return Err(BootError::Address);
        }
        inv.reservations[0] = full_header;
        inv.reservations.push(range);
    }
    // Catch modules overlapping strings or metadata discovered later too.
    for &module in &inv.modules {
        if inv
            .reservations
            .iter()
            .filter(|&&r| overlaps(r, module))
            .count()
            != 1
        {
            return Err(BootError::Module);
        }
    }
    Ok(inv)
}

fn reserve(inv: &mut Inventory, start: u64, len: u64, kernel: (u64, u64)) -> Result<(), BootError> {
    let range = span(start, len)?;
    address(&inv.entries, range, kernel)?;
    // Fixed pre-reserved capacity: never silently grow the bounded inventory.
    if inv.reservations.len() == inv.reservations.capacity() {
        return Err(BootError::Limit);
    }
    inv.reservations.push(range);
    Ok(())
}

fn string<F>(
    inv: &mut Inventory,
    start: u64,
    kernel: (u64, u64),
    read: &mut F,
) -> Result<ModuleName, BootError>
where
    F: FnMut(u64, &mut [u8]) -> Result<(), BootError>,
{
    let mut name = ModuleName::EMPTY;
    let mut eligible = true;
    for i in 0..MAX_STRING {
        let range = span(start, i + 1)?;
        address(&inv.entries, range, kernel)?;
        let mut byte = [0];
        read(start + i, &mut byte)?;
        if byte[0] == 0 {
            reserve(inv, start, i + 1, kernel)?;
            return Ok(if eligible { name } else { ModuleName::EMPTY });
        }
        if i < MAX_MODULE_NAME as u64 && (0x20..=0x7e).contains(&byte[0]) {
            name.bytes[i as usize] = byte[0];
            name.len = (i + 1) as u8;
        } else {
            eligible = false;
        }
    }
    Err(BootError::String)
}

#[cfg(not(test))]
/// # Safety
/// Entered once with paging disabled, flat data segments, and the loader's
/// conventional RAM backed by readable physical memory. Malicious firmware
/// lying about RAM is outside the Multiboot trust boundary.
pub unsafe fn from_physical(magic: u32, info: u64) -> Result<Inventory, BootError> {
    parse(
        magic,
        info,
        crate::memory::frame::kernel_bounds(),
        |addr, out| {
            unsafe {
                core::ptr::copy_nonoverlapping(addr as *const u8, out.as_mut_ptr(), out.len());
            }
            Ok(())
        },
    )
}
