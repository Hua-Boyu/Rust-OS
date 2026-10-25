//! Shared fixed F5 image/scalar contracts; no hardware or owner authority.
// ---- F5-only GDT extension (design section 2) ----
// Slots 0-4 are copied byte-for-byte from the accepted F3 five-entry table at
// install time; slots 5/6 are the F5-only DPL3 additions. Values here are the
// contract for the new descriptors only.
pub const F5_USER_CODE: u64 = 0x00cf_fb00_0000_ffff;
pub const F5_USER_DATA: u64 = 0x00cf_f300_0000_ffff;
pub const F5_GDT_ENTRIES: usize = 7;
pub const F5_GDTR_LIMIT: u16 = 55;
pub const F5_USER_CS: u16 = 0x2b;
pub const F5_USER_DS: u16 = 0x33;
pub const F5_KERNEL_CS: u16 = 0x08;
pub const F5_KERNEL_SS: u16 = 0x10;
pub const F5_TR: u16 = 0x18;
pub const F5_TSS_ESP0: u32 = 0x07c0_5000;
pub const F5_TSS_SS0: u16 = 0x10;

// ---- Fixed kernel-embedded payload (design section 3) ----
// 384-byte block at code physical offset 0x100; six 64-byte slots.
pub const F5_PAYLOAD_OFFSET: u32 = 0x100;
pub const F5_PAYLOAD_BYTES: usize = 384;
pub const F5_SLOT_BYTES: usize = 64;
pub const F5_PROLOGUE: [u8; 12] = [
    0x31, 0xc0, 0x66, 0x8c, 0xc8, 0x68, 0xde, 0xc0, 0x17, 0x5a, 0x5b, 0xfd,
];
pub const F5_RO_DATA_OFFSET: u32 = 2048; // 'F' = 0x46 must stay unchanged
pub const F5_RO_DATA_BYTE: u8 = 0x46;

// Per scenario: entry EIP, fault EIP, full slot bytes before zero padding,
// expected vector, expected error code, expected CR2 (PF only).
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct F5ScenarioRow {
    pub id: u8, // 1..6 == A..F
    pub entry: u32,
    pub fault_eip: u32,
    pub bytes: [u8; 24], // actual slot prefix; remainder of slot is zero
    pub vector: u32,
    pub error: u32,
    pub cr2: u32, // meaningful for vector 14 only
}

pub const F5_ROWS: [F5ScenarioRow; 6] = [
    F5ScenarioRow {
        id: 1,
        entry: 0x4000_0100,
        fault_eip: 0x4000_010c,
        bytes: [
            0x31, 0xc0, 0x66, 0x8c, 0xc8, 0x68, 0xde, 0xc0, 0x17, 0x5a, 0x5b, 0xfd, 0x0f, 0x0b,
            0x0f, 0x0b, 0, 0, 0, 0, 0, 0, 0, 0,
        ],
        vector: 6,
        error: 0,
        cr2: 0,
    },
    F5ScenarioRow {
        id: 2,
        entry: 0x4000_0140,
        fault_eip: 0x4000_014c,
        bytes: [
            0x31, 0xc0, 0x66, 0x8c, 0xc8, 0x68, 0xde, 0xc0, 0x17, 0x5a, 0x5b, 0xfd, 0xc6, 0x05,
            0x00, 0x08, 0x00, 0x40, 0x7e, 0x0f, 0x0b, 0, 0, 0,
        ],
        vector: 14,
        error: 7,
        cr2: 0x4000_0800,
    },
    F5ScenarioRow {
        id: 3,
        entry: 0x4000_0180,
        fault_eip: 0x4000_018c,
        bytes: [
            0x31, 0xc0, 0x66, 0x8c, 0xc8, 0x68, 0xde, 0xc0, 0x17, 0x5a, 0x5b, 0xfd, 0x8b, 0x0d,
            0x00, 0x10, 0xc0, 0x07, 0x0f, 0x0b, 0, 0, 0, 0,
        ],
        vector: 14,
        error: 5,
        cr2: 0x07c0_1000,
    },
    F5ScenarioRow {
        id: 4,
        entry: 0x4000_01c0,
        fault_eip: 0x4000_01cc,
        bytes: [
            0x31, 0xc0, 0x66, 0x8c, 0xc8, 0x68, 0xde, 0xc0, 0x17, 0x5a, 0x5b, 0xfd, 0xf4, 0x0f,
            0x0b, 0, 0, 0, 0, 0, 0, 0, 0, 0,
        ],
        vector: 13,
        error: 0,
        cr2: 0,
    },
    F5ScenarioRow {
        id: 5,
        entry: 0x4000_0200,
        fault_eip: 0x4000_020c,
        bytes: [
            0x31, 0xc0, 0x66, 0x8c, 0xc8, 0x68, 0xde, 0xc0, 0x17, 0x5a, 0x5b, 0xfd, 0xe6, 0x80,
            0x0f, 0x0b, 0, 0, 0, 0, 0, 0, 0, 0,
        ],
        vector: 13,
        error: 0,
        cr2: 0,
    },
    F5ScenarioRow {
        id: 6,
        entry: 0x4000_0240,
        fault_eip: 0x4000_024c,
        bytes: [
            0x31, 0xc0, 0x66, 0x8c, 0xc8, 0x68, 0xde, 0xc0, 0x17, 0x5a, 0x5b, 0xfd, 0x8b, 0x0d,
            0x00, 0xe0, 0x3f, 0x40, 0x0f, 0x0b, 0, 0, 0, 0,
        ],
        vector: 14,
        error: 4,
        cr2: 0x403f_e000,
    },
];

pub const F5_ENTRY_EFLAGS: u32 = 0x0000_0002; // bit1 only; RF/IF/IOPL/DF clear
pub const F5_USER_ESP: u32 = 0x4040_0000; // page-end; first PUSH writes 0x403f_fffc
pub const F5_SENTINEL_EBX: u32 = 0x5a17_c0de;

// ---- Derived cross-ring frame (design section 5) ----
// CPU pushes old SS, old ESP, EFLAGS, CS, EIP, (error) onto TSS SS0:ESP0, then
// the constrained F2-derived expansion pushes vector (and zero for no-error),
// PUSHAD (32) and the four software-saved selectors (16). Prefix stays 68 bytes.
pub const F5_PREFIX_BYTES: usize = 68; // unchanged F2 FRAME_SIZE
pub const F5_FRAME_BYTES: usize = 76; // prefix + old ESP + old SS tail
pub const F5_VECTOR_OFFSET: usize = 48; // unchanged F2 VECTOR_OFFSET
pub const F5_EIP_OFFSET: usize = 56;
pub const F5_CS_OFFSET: usize = 60;
pub const F5_EFLAGS_OFFSET: usize = 64;
pub const F5_OLD_ESP_OFFSET: usize = 68;
pub const F5_OLD_SS_OFFSET: usize = 72;
pub const F5_PUSHAD_ESP_OFFSET: usize = 28;
pub const F5_FRAME_FROM_ESP0: usize = 76; // first CPL3 frame at ESP0-76

// Saved-EFLAGS oracle: fault-class RF=1 (Intel SDM Vol3 17.3.1.1), DF=1 from
// STD, ZF/PF=1 from XOR EAX,EAX, bit1=1; AF masked (undefined after the
// prologue). The only two admissible values differ solely in AF (bit 4).
pub const F5_SAVED_EFLAGS_AF0: u32 = 0x0001_0446;
pub const F5_SAVED_EFLAGS_AF1: u32 = 0x0001_0456;
pub const F5_EFLAGS_AF_MASK: u32 = 0x10;

pub fn f5_admissible(scenario: u32) -> bool {
    scenario >= 1 && scenario <= 6
}

pub fn f5_row(scenario: u32) -> Option<&'static F5ScenarioRow> {
    if f5_admissible(scenario) {
        Some(&F5_ROWS[(scenario - 1) as usize])
    } else {
        None
    }
}
