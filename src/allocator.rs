use crate::{multiboot::BootInfo, println, utils::mutex::SpinMutex};
use core::alloc::{GlobalAlloc, Layout};
use core::ptr::null_mut;

// A bounded bootstrap heap inside the kernel's .bss. Reserving the kernel
// image therefore reserves this heap too; it cannot consume a boot module,
// stretch across a mmap hole, or reserve all RAM from the frame allocator.
const BOOT_HEAP_SIZE: usize = 1024 * 1024;
#[repr(align(4096))]
struct BootHeap {
    _bytes: [u8; BOOT_HEAP_SIZE],
}
static mut BOOT_HEAP: BootHeap = BootHeap {
    _bytes: [0; BOOT_HEAP_SIZE],
};

pub fn bootstrap_heap_bounds() -> (usize, usize) {
    let start = (&raw mut BOOT_HEAP) as usize;
    (start, start + BOOT_HEAP_SIZE)
}

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

    pub unsafe fn init(&mut self, _info: *const BootInfo) {
        let (start, end) = bootstrap_heap_bounds();
        println!(
            "bumpalloc start segment: {:#4x}, end segment: {:#4x}",
            start, end
        );

        self.start = start;
        self.end = end;
        self.next = start;
        self.allocs = 0;
    }
}

unsafe impl GlobalAlloc for SpinMutex<BumpAlloc> {
    unsafe fn alloc(&self, layout: Layout) -> *mut u8 {
        let mut bump = self.lock();

        let Some(aligned) = bump.next.checked_add(layout.align() - 1) else {
            return null_mut();
        };
        let alloc_start = aligned & !(layout.align() - 1);
        let Some(alloc_end) = alloc_start.checked_add(layout.size()) else {
            return null_mut();
        };

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
