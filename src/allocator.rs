use crate::{multiboot::BootInfo, utils::mutex::SpinMutex};
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

// ---- Phase 5: dynamic reclaiming kernel heap ----
//
// Design:
// - Singly-linked free list, sorted by address, with adjacent-block
//   coalescing on dealloc. Block layout: [size: u32][next: u32][payload...];
//   `size` counts the whole block including the 8-byte header.
// - Initial region: the 1 MiB bootstrap heap (kernel BSS, identity-mapped).
//   Growth adds one page at a time in the virtual growth window
//   [GROWTH_START, GROWTH_END): each growth allocates a physical frame from
//   the frame allocator, maps it at the next growth slot, and appends a free
//   block covering the page. The growth window is excluded from the boot
//   identity map so runtime mapping cannot conflict with boot mappings.
// - Lock order: heap lock -> frame allocator lock (growth path only). The
//   frame allocator never calls back into the heap, so no cycle exists.
// - No allocation, printing, or recursion inside alloc/dealloc; header reads
//   and writes are raw pointer ops on memory the heap owns.
// - Alignment waste (prefix before an aligned payload) is counted in stats.
// - OOM returns null and increments failed_allocs; no panic, no wraparound.

pub const HEADER_SIZE: usize = 8;
pub const MIN_BLOCK: usize = HEADER_SIZE;

#[derive(Debug, Clone, Copy)]
pub struct HeapStats {
    pub capacity: usize,
    pub used: usize,
    pub free: usize,
    pub live_allocs: usize,
    pub failed_allocs: usize,
    pub invalid_deallocs: usize,
    pub free_blocks: usize,
    pub largest_free: usize,
    pub waste: usize,
    pub growth_pages: usize,
}

pub struct KernelHeap {
    head: usize,
    pub stats: HeapStats,
    initialized: bool,
    grow_next: usize, // 0 disables growth (host tests)
}

impl KernelHeap {
    pub const fn new() -> Self {
        KernelHeap {
            head: 0,
            stats: HeapStats {
                capacity: 0,
                used: 0,
                free: 0,
                live_allocs: 0,
                failed_allocs: 0,
                invalid_deallocs: 0,
                free_blocks: 0,
                largest_free: 0,
                waste: 0,
                growth_pages: 0,
            },
            initialized: false,
            grow_next: 0,
        }
    }

    /// Initialize over the bootstrap heap (kernel BSS). Growth is enabled in
    /// kernel builds only; host tests add regions explicitly.
    pub unsafe fn init(&mut self, _info: *const BootInfo) {
        let (start, end) = bootstrap_heap_bounds();
        self.head = 0;
        self.stats = HeapStats {
            capacity: 0,
            used: 0,
            free: 0,
            live_allocs: 0,
            failed_allocs: 0,
            invalid_deallocs: 0,
            free_blocks: 0,
            largest_free: 0,
            waste: 0,
            growth_pages: 0,
        };
        self.initialized = true;
        self.grow_next = if cfg!(test) {
            0
        } else {
            crate::memory::GROWTH_START
        };
        self.add_region(start, end);
    }

    /// Add a region as one free block (growth pages and host tests).
    pub fn add_region(&mut self, start: usize, end: usize) {
        if end <= start || end - start < MIN_BLOCK {
            return;
        }
        self.initialized = true;
        self.stats.capacity += end - start;
        unsafe { self.insert_free(start, end - start) };
    }

    unsafe fn read_u32(&self, addr: usize) -> u32 {
        #[cfg(test)]
        {
            return MIRROR.with(|m| m.borrow().get(&addr).copied().unwrap_or(0));
        }
        #[allow(unreachable_code)]
        unsafe {
            (addr as *const u32).read_unaligned()
        }
    }

    unsafe fn write_u32(&self, addr: usize, value: u32) {
        #[cfg(test)]
        MIRROR.with(|m| {
            m.borrow_mut().insert(addr, value);
        });
        #[cfg(not(test))]
        unsafe {
            (addr as *mut u32).write_unaligned(value);
        }
    }

    /// Insert a free block into the sorted free list, coalescing with the
    /// predecessor and successor when adjacent.
    unsafe fn insert_free(&mut self, block: usize, size: usize) {
        if size < MIN_BLOCK {
            return;
        }
        unsafe {
            self.write_u32(block, size as u32);
            self.write_u32(block + 4, 0);

            let mut prev = 0usize;
            let mut cur = self.head;
            while cur != 0 && cur < block {
                prev = cur;
                cur = self.read_u32(cur + 4) as usize;
            }
            if prev != 0 && prev + self.read_u32(prev) as usize == block {
                let merged = self.read_u32(prev) as usize + size;
                if cur != 0 && block + size == cur {
                    self.write_u32(prev, (merged + self.read_u32(cur) as usize) as u32);
                    self.write_u32(prev + 4, self.read_u32(cur + 4));
                } else {
                    self.write_u32(prev, merged as u32);
                    self.write_u32(prev + 4, cur as u32);
                }
                self.recount();
                return;
            }
            if cur != 0 && block + size == cur {
                self.write_u32(block, (size + self.read_u32(cur) as usize) as u32);
                self.write_u32(block + 4, self.read_u32(cur + 4));
                if prev != 0 {
                    self.write_u32(prev + 4, block as u32);
                } else {
                    self.head = block;
                }
                self.recount();
                return;
            }
            self.write_u32(block + 4, cur as u32);
            if prev != 0 {
                self.write_u32(prev + 4, block as u32);
            } else {
                self.head = block;
            }
            self.recount();
        }
    }

    unsafe fn recount(&mut self) {
        unsafe {
            self.stats.free = 0;
            self.stats.free_blocks = 0;
            self.stats.largest_free = 0;
            let mut cur = self.head;
            while cur != 0 {
                let size = self.read_u32(cur) as usize;
                self.stats.free += size;
                self.stats.free_blocks += 1;
                if size > self.stats.largest_free {
                    self.stats.largest_free = size;
                }
                cur = self.read_u32(cur + 4) as usize;
            }
        }
    }

    unsafe fn remove_block(&mut self, block: usize) {
        unsafe {
            let mut prev = 0usize;
            let mut cur = self.head;
            while cur != 0 && cur != block {
                prev = cur;
                cur = self.read_u32(cur + 4) as usize;
            }
            if cur == 0 {
                return;
            }
            let next = self.read_u32(cur + 4) as usize;
            if prev == 0 {
                self.head = next;
            } else {
                self.write_u32(prev + 4, next as u32);
            }
        }
    }

    /// First-fit allocation. Returns null on OOM. Iterative (no recursion):
    /// growth adds one page, then the same loop retries the free list.
    unsafe fn alloc_inner(&mut self, layout: Layout) -> *mut u8 {
        unsafe {
            if !self.initialized {
                self.stats.failed_allocs += 1;
                return null_mut();
            }
            let need = layout.size().max(1) + HEADER_SIZE;
            loop {
                let mut cur = self.head;
                while cur != 0 {
                    let size = self.read_u32(cur) as usize;
                    let payload = align_up(cur + HEADER_SIZE, layout.align());
                    let waste = payload - (cur + HEADER_SIZE);
                    if size >= waste + need {
                        let block = payload - HEADER_SIZE;
                        let rem = size - (block - cur) - need;
                        self.stats.waste += waste;
                        self.remove_block(cur);
                        if rem >= MIN_BLOCK {
                            self.insert_free(block + need, rem);
                        }
                        self.write_u32(block, need as u32);
                        self.stats.used += need;
                        self.stats.live_allocs += 1;
                        self.recount();
                        return payload as *mut u8;
                    }
                    cur = self.read_u32(cur + 4) as usize;
                }
                // Growth: one page at a time from the frame allocator.
                if self.grow_next != 0 && self.grow_next < crate::memory::GROWTH_END {
                    let slot = self.grow_next;
                    if let Some(frame) = crate::memory::heap_grow_frame(slot) {
                        self.grow_next += 4096;
                        self.stats.growth_pages += 1;
                        #[cfg(not(test))]
                        core::ptr::write_bytes(frame as *mut u8, 0, 4096);
                        self.add_region(slot, slot + 4096);
                        continue;
                    }
                }
                self.stats.failed_allocs += 1;
                return null_mut();
            }
        }
    }

    unsafe fn dealloc_inner(&mut self, ptr: *mut u8, layout: Layout) {
        unsafe {
            if !self.initialized {
                return;
            }
            let block = ptr as usize - HEADER_SIZE;
            let size = self.read_u32(block) as usize;
            // A live block must be at least header + payload. A foreign or
            // corrupted header (size below the layout or larger than the
            // whole heap) is rejected rather than corrupting the free list.
            if size < HEADER_SIZE + layout.size() || size > self.stats.capacity {
                self.stats.invalid_deallocs += 1;
                return;
            }
            self.stats.used -= size;
            self.stats.live_allocs -= 1;
            self.insert_free(block, size);
        }
    }
}

unsafe impl GlobalAlloc for SpinMutex<KernelHeap> {
    unsafe fn alloc(&self, layout: Layout) -> *mut u8 {
        let mut heap = self.lock();
        unsafe { heap.alloc_inner(layout) }
    }

    unsafe fn dealloc(&self, ptr: *mut u8, layout: Layout) {
        let mut heap = self.lock();
        unsafe { heap.dealloc_inner(ptr, layout) }
    }
}

#[cfg(not(test))]
#[global_allocator]
pub static ALLOC: SpinMutex<KernelHeap> = SpinMutex::new(KernelHeap::new());

/// Snapshot of heap stats. Callers must not hold the heap lock here.
#[cfg(not(test))]
pub fn heap_stats() -> HeapStats {
    ALLOC.lock().stats
}

#[cfg(test)]
thread_local! {
    static MIRROR: core::cell::RefCell<std::collections::HashMap<usize, u32>> =
        core::cell::RefCell::new(std::collections::HashMap::new());
}

// ---- Bootstrap bump allocator (kept for early boot + regression tests) ----

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
}

// Regression-tested arithmetic (checked, boundary rejection). The kernel's
// live global allocator is KernelHeap; this impl remains for host tests and
// as the documented early-boot fallback.
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
            return null_mut();
        }

        bump.next = alloc_end;
        bump.allocs += 1;

        alloc_start as *mut u8
    }

    unsafe fn dealloc(&self, _ptr: *mut u8, _layout: Layout) {
        let mut bump = self.lock();

        bump.allocs -= 1;

        if bump.allocs == 0 {
            bump.next = bump.start;
            bump.allocs = 0;
        }
    }
}
