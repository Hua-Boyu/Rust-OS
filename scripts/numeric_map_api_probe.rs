//! Metadata-only production API probe: compile WITHOUT cfg(test).
#![allow(dead_code, unused_imports, asm_sub_register)]
extern crate alloc;
#[macro_export]
macro_rules! println {
    ($($arg:tt)*) => { let _ = ::core::format_args!($($arg)*); };
}
mod utils {
    pub mod bits {
        include!("../src/utils/bits.rs");
    }
    pub mod mutex {
        include!("../src/utils/mutex.rs");
    }
}
mod io {
    pub mod serial {
        // Metadata-only harness boundary; hardware I/O is never executed.
        pub fn puts(_: &str) {}
    }
}
mod multiboot {
    #[derive(Clone, Copy)]
    #[repr(C, packed)]
    pub struct MmapEntry {
        pub size: u32,
        pub base_addr: u64,
        pub length: u64,
        pub type_: u32,
    }
}
#[path = "../src/memory/mod.rs"]
mod memory;
use memory::{
    frame::{FrameAllocator, FrameLease},
    paging::{KERNEL_PERMS, PageMap},
};

#[cfg(base_control)]
fn control(pm: &PageMap, addr: u64) -> Option<u64> {
    pm.translate(addr)
}

#[cfg(raw_numeric)]
fn unauthorized_numeric(pm: &mut PageMap, fa: &mut FrameAllocator, addr: u64) -> bool {
    pm.map(fa, memory::GROWTH_START as u64, addr, &KERNEL_PERMS)
}

#[cfg(owned_control)]
fn authorized_owned(pm: &mut PageMap, fa: &mut FrameAllocator, lease: &FrameLease) -> bool {
    pm.map_owned(fa, memory::GROWTH_START as u64, lease, &KERNEL_PERMS)
}

#[cfg(private_core)]
fn unauthorized_core(pm: &mut PageMap, fa: &mut FrameAllocator, addr: u64) -> bool {
    pm.map_authorized(fa, memory::GROWTH_START as u64, addr, &KERNEL_PERMS)
}

#[cfg(numeric_owned)]
fn unauthorized_owned(pm: &mut PageMap, fa: &mut FrameAllocator, addr: u64) -> bool {
    pm.map_owned(fa, memory::GROWTH_START as u64, addr, &KERNEL_PERMS)
}
