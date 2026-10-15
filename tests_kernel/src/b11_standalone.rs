//! Isolated B11 frame-policy runner, independent of concurrent boot/paging edits.
//! rustc +nightly --edition=2024 --test tests_kernel/src/b11_standalone.rs -o <exe>
#![allow(dead_code)]
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
mod memory {
    pub fn dbg(_: &str) {}
    pub mod paging {
        pub const GROWTH_START: usize = 0x800_000;
        pub const GROWTH_END: usize = 0xE00_000;
    }
    #[path = "../../../src/memory/frame.rs"]
    pub mod frame;
}
