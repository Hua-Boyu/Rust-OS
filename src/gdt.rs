use core::arch::asm;

#[cfg(test)]
#[path = "phase11_gdt_tests.rs"]
mod phase11_gdt_tests;

#[repr(C, packed)]
struct GdtTable {
    limit: u16,
    base: u32,
}

#[allow(dead_code)]
#[repr(u8)]
pub enum AccessByte {
    Accessed = 1,
    ReadWrite = 2,
    Direction = 4,
    Executable = 8,
    NotSystemDescriptor = 16,
    Present = 128,
    Privilege0 = 0,
    Privilege1 = 32,
    Privilege2 = 64,
    Privilege3 = 96,
}

pub struct GdtSegment {
    pub access_byte: u8,
    pub flag: u8, // higher nibble is used
    pub base: u32,
    pub limit: u32,
}

// allow dead code because there's a lot of variants that we explicitly do not
// initialise, but we still include them for the sake of following the spec
// (and maybe if we choose to actually implement this in the future).
//
// Unused variants include: AccessByte::Direction, Privilege0 through 3
// and the set_long_mode method.
#[allow(dead_code)]
impl GdtSegment {
    pub fn new(base: u32, limit: u32) -> Self {
        Self {
            access_byte: 0,
            flag: 0,
            base,
            limit,
        }
    }

    /// modified from: osdev wiki
    /// https://wiki.osdev.org/GDT_Tutorial
    fn as_u64(&self) -> u64 {
        let mut desc = (self.limit & 0x000f_0000) as u64;
        desc |= (self.flag as u64) << 16 & 0x00f0_0000;
        desc |= (self.access_byte as u64) << 8 & 0x0000_ff00;
        desc |= (self.base as u64) >> 16 & 0x0000_00ff;
        desc |= self.base as u64 & 0xff00_0000;

        desc <<= 32;
        desc |= ((self.base & 0x0000_ffff) as u64) << 16;
        desc |= (self.limit & 0x0000_ffff) as u64;

        desc
    }

    pub fn with_access_byte(mut self, item: AccessByte) -> Self {
        // OR, not XOR: XOR would toggle off a bit that is already set
        // (e.g. ReadWrite=2 vs Accessed=1 collide when combined).
        self.access_byte |= item as u8;
        self
    }

    fn set_privilege(mut self, privilege_level: u8) -> Result<Self, &'static str> {
        if privilege_level > 3 {
            return Err("invalid privilege_level");
        }

        self.access_byte &= !0b0110_0000; // zero privilege level
        self.access_byte |= privilege_level << 5;
        Ok(self)
    }

    fn set_page_granularity(mut self, enable: bool) -> Self {
        const MASK: u8 = 0b1000_0000;
        if enable {
            self.flag |= MASK;
        } else {
            self.flag &= !MASK;
        }

        self
    }

    fn set_32bit_segment_size(mut self, enable: bool) -> Self {
        const MASK: u8 = 0b0100_0000;
        if enable {
            self.flag |= MASK;
        } else {
            self.flag &= !MASK;
        }

        self
    }

    fn set_long_mode(mut self, enable: bool) -> Result<Self, &'static str> {
        const MASK: u8 = 0b0010_0000;
        if enable {
            if self.flag & 0b0100 > 0 {
                return Err("cannot set long mode with 32 bit segment");
            }

            // from osdev wiki:
            // "For any other type of segment (other code types or any data segment), it should be clear (0)."
            // What does "any other type of segment" mean? There are other code types??
            if self.access_byte & (AccessByte::Executable as u8) == 0 {
                return Err("cannot set long mode on non-executable segment");
            }

            self.flag |= MASK;
        } else {
            self.flag &= !MASK;
        }

        Ok(self)
    }
}

pub fn create_gdt_entries() -> [u64; 3] {
    let code = GdtSegment::new(0, 0xffff_ffff)
        .with_access_byte(AccessByte::Present)
        .with_access_byte(AccessByte::NotSystemDescriptor)
        .with_access_byte(AccessByte::Executable)
        .with_access_byte(AccessByte::Accessed)
        .set_32bit_segment_size(true)
        .set_page_granularity(true)
        .as_u64();

    let data = GdtSegment::new(0, 0xffff_ffff)
        .with_access_byte(AccessByte::Present)
        .with_access_byte(AccessByte::NotSystemDescriptor)
        .with_access_byte(AccessByte::ReadWrite)
        .with_access_byte(AccessByte::Accessed)
        .set_32bit_segment_size(true)
        .set_page_granularity(true)
        .as_u64();

    let blank = GdtSegment::new(0, 0).as_u64();

    [blank, code, data]
}

pub fn init_gdt() {
    let entries = create_gdt_entries().to_vec().leak();
    let ptr = entries.as_ptr();
    // each GDT descriptor is 8 bytes on the wire, not size_of::<GdtSegment>()
    let size = entries.len() * 8;

    let gdt: GdtTable = GdtTable {
        // lgdt expects limit = size - 1
        limit: (size - 1) as u16,
        base: ptr as u32,
    };

    // disable interrupts and load gdt
    unsafe {
        asm!(r#"
            cli
            lgdt ({gdt})
        "#, gdt = in (reg) &gdt, options(att_syntax));
    }

    // reload segments
    #[cfg(not(test))]
    unsafe {
        asm!(r#"
            jmp $0x08, $1f
            1:
            mov $0x10, {r}
            mov {r}, %ds
            mov {r}, %es
            mov {r}, %fs
            mov {r}, %ss
            mov {r}, %gs
        "#, r = out (reg) _, options(att_syntax));
    }
}
