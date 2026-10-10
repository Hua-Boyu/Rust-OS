use crate::{
    multiboot::{BootInfo, find_usable_block},
    println,
    utils::mutex::SpinMutex,
};
use core::alloc::{GlobalAlloc, Layout};
use core::ptr::null_mut;

unsafe extern "C" {
    #[cfg(not(test))]
    static KERNEL_START: u32;
    #[cfg(not(test))]
    static KERNEL_END: u32;
}

// Host tests can't link against linker.ld symbols, so provide dummies.
#[cfg(test)]
static KERNEL_START: u32 = 0;
#[cfg(test)]
static KERNEL_END: u32 = 0;

/// Align a given address upward to the `align` boundary
///
/// `align` must be a power of 2.
pub fn align_up(addr: usize, align: usize) -> usize {
    (addr + align - 1) & !(align - 1)
}

pub struct BumpAlloc {
    pub start: usize,
    pub end: usize,
    pub next: usize,
    pub allocs: usize,
}

impl BumpAlloc {
    pub const fn new() -> Self {
        BumpAlloc {
            start: 0,
            end: 0,
            next: 0,
            allocs: 0,
        }
    }

    pub unsafe fn init(&mut self, info: *const BootInfo) {
        let block;
        let kstart;
        let kend;

        unsafe {
            // Use the allocation-free parser: we are inside the global
            // allocator's own init, so allocating a Vec here would deadlock
            // the SpinMutex<BumpAlloc>.
            let bytes = core::slice::from_raw_parts(
                (*info).mmap_addr as *const u8,
                (*info).mmap_length as usize,
            );
            block = find_usable_block(bytes).expect("Usable memory required");

            kstart = &KERNEL_START as *const u32;
            kend = &KERNEL_END as *const u32;
        }

        let mut end = block.base_addr + block.length;
        let mut start = block.base_addr;

        if block.base_addr == 0 {
            start = kend as u64 + 4;
            end = start + block.length;
        } else {
            if end < kstart as u64 {
                end = kstart as u64 - 4;
            }

            if start < kend as u64 {
                start = kend as u64 + 4;
            }

            assert!(end >= start, "Bad! No memory other than kernel memory.");
        }

        println!(
            "bumpalloc start segment: {:#4x}, end segment: {:#4x}",
            start, end
        );

        self.start = usize::try_from(start).expect("fit within u64");
        self.end = usize::try_from(end).expect("fit within u64");
        self.next = usize::try_from(start).expect("fit within u64");
        self.allocs = 0;
    }
}

unsafe impl GlobalAlloc for SpinMutex<BumpAlloc> {
    unsafe fn alloc(&self, layout: Layout) -> *mut u8 {
        let mut bump = self.lock();

        let alloc_start = align_up(bump.next, layout.align());
        let alloc_end = alloc_start + layout.size();

        if alloc_end > bump.end {
            println!(
                "ran out of memory! required {}, end {:#4x}, next {:#4x}",
                layout.size(),
                bump.end,
                bump.next
            );
            return null_mut();
        }

        bump.next = alloc_end;
        bump.allocs += 1;

        alloc_start as *mut u8
    }

    /// deallocs the whole thing - it a bump allocator
    unsafe fn dealloc(&self, _ptr: *mut u8, _layout: Layout) {
        let mut bump = self.lock();

        bump.allocs -= 1;

        if bump.allocs == 0 {
            bump.next = bump.start;
            bump.allocs = 0;
        }
    }
}
