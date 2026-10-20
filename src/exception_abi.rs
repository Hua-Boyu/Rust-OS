//! Fixed mandatory prefix for fatal 32-bit exception entry. Never a return ABI.
//! Optional privilege-transition words are deliberately absent from this type.
use core::sync::atomic::{AtomicBool, Ordering};

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum FrameKind {
    NoError,
    HardwareError,
    Unsupported,
}

pub const fn frame_kind(vector: u32) -> FrameKind {
    match vector {
        8 | 10 | 11 | 12 | 13 | 14 | 17 => FrameKind::HardwareError,
        21 | 29 | 30 => FrameKind::Unsupported,
        0..=31 => FrameKind::NoError,
        _ => FrameKind::Unsupported,
    }
}

#[derive(Debug, Clone, Copy, Default, PartialEq, Eq)]
#[repr(C)]
pub struct ExceptionFrame {
    pub gs: u32,
    pub fs: u32,
    pub es: u32,
    pub ds: u32,
    pub edi: u32,
    pub esi: u32,
    pub ebp: u32,
    /// PUSHAD input ESP: address of the normalized vector, not interrupted ESP.
    pub pushad_esp: u32,
    pub ebx: u32,
    pub edx: u32,
    pub ecx: u32,
    pub eax: u32,
    pub vector: u32,
    pub error: u32,
    pub eip: u32,
    pub cs: u32,
    pub eflags: u32,
}

pub const FRAME_SIZE: usize = 68;
pub const VECTOR_OFFSET: usize = 48;
const _: () = {
    assert!(core::mem::size_of::<ExceptionFrame>() == FRAME_SIZE);
    assert!(core::mem::align_of::<ExceptionFrame>() == 4);
    assert!(core::mem::offset_of!(ExceptionFrame, gs) == 0);
    assert!(core::mem::offset_of!(ExceptionFrame, fs) == 4);
    assert!(core::mem::offset_of!(ExceptionFrame, es) == 8);
    assert!(core::mem::offset_of!(ExceptionFrame, ds) == 12);
    assert!(core::mem::offset_of!(ExceptionFrame, edi) == 16);
    assert!(core::mem::offset_of!(ExceptionFrame, esi) == 20);
    assert!(core::mem::offset_of!(ExceptionFrame, ebp) == 24);
    assert!(core::mem::offset_of!(ExceptionFrame, pushad_esp) == 28);
    assert!(core::mem::offset_of!(ExceptionFrame, ebx) == 32);
    assert!(core::mem::offset_of!(ExceptionFrame, edx) == 36);
    assert!(core::mem::offset_of!(ExceptionFrame, ecx) == 40);
    assert!(core::mem::offset_of!(ExceptionFrame, eax) == 44);
    assert!(core::mem::offset_of!(ExceptionFrame, vector) == VECTOR_OFFSET);
    assert!(core::mem::offset_of!(ExceptionFrame, error) == 52);
    assert!(core::mem::offset_of!(ExceptionFrame, eip) == 56);
    assert!(core::mem::offset_of!(ExceptionFrame, cs) == 60);
    assert!(core::mem::offset_of!(ExceptionFrame, eflags) == 64);
};

impl ExceptionFrame {
    /// #DF saved CS/EIP are architecturally undefined. Never report its origin.
    pub fn origin(&self) -> Option<u32> {
        if self.vector == 8 || frame_kind(self.vector) == FrameKind::Unsupported {
            None
        } else {
            Some(self.cs & 3)
        }
    }

    /// Scalar address arithmetic only; never dereference nonexistent SS/ESP.
    pub fn same_ring_esp(&self, prefix_address: u32) -> Option<u32> {
        if self.origin() == Some(0) {
            prefix_address.checked_add(FRAME_SIZE as u32)
        } else {
            None
        }
    }

    /// Synthetic decoder ONLY. Production fatal entry never calls this API.
    #[allow(dead_code)]
    pub fn synthetic_transition_tail(&self, words: &[u32]) -> Option<(u32, u32)> {
        if self.origin()? != 0 && words.len() == 2 {
            Some((words[0], words[1] & 0xffff))
        } else {
            None
        }
    }
}

/// Observed profile, not CPU feature discovery or authorization for CPL3.
pub fn supported_profile(cr0: u32, cr4: u32, eflags: u32, cs: u32, ss: u32) -> bool {
    cr0 & 0x8001_0001 == 0x8001_0001
        && cr4 & ((1 << 5) | (1 << 23)) == 0
        && eflags & (1 << 17) == 0
        && cs == 8
        && ss == 16
}

pub struct FatalLatch(AtomicBool);
impl FatalLatch {
    pub const fn new() -> Self {
        Self(AtomicBool::new(false))
    }
    pub fn enter(&self) -> bool {
        !self.0.swap(true, Ordering::SeqCst)
    }
}

#[cfg(test)]
#[path = "exception_abi_tests.rs"]
mod tests;
