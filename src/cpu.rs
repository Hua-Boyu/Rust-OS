//! CPUID vendor identification. The string assembly is pure and host-testable;
//! the cpuid instruction itself is gated out under test builds.

/// CPUID leaf 0 vendor string: bytes come from EBX, EDX, ECX in that order,
/// four bytes each, little-endian within each register.
pub fn vendor_string(ebx: u32, edx: u32, ecx: u32) -> ::alloc::string::String {
    let mut out = ::alloc::string::String::new();
    for reg in [ebx, edx, ecx] {
        for i in 0..4 {
            let b = ((reg >> (i * 8)) & 0xFF) as u8;
            if b == 0 {
                break;
            }
            out.push(b as char);
        }
    }
    out
}

pub fn vendor() -> Option<::alloc::string::String> {
    // The cpuid instruction itself only compiles for the 32-bit kernel target;
    // host test builds (x86_64) cannot use rbx as an asm operand, so the asm
    // block is cfg-gated out and only the pure string assembly is tested.
    #[cfg(all(not(test), target_arch = "x86"))]
    unsafe {
        let ebx: u32;
        let edx: u32;
        let ecx: u32;
        core::arch::asm!(
            "cpuid",
            inout("eax") 0 => _,
            out("ebx") ebx,
            out("ecx") ecx,
            out("edx") edx,
            options(att_syntax, nomem, preserves_flags)
        );
        if ebx == 0 && edx == 0 && ecx == 0 {
            return None; // CPUID unsupported / zeroed
        }
        return Some(vendor_string(ebx, edx, ecx));
    }
    #[allow(unreachable_code)]
    None
}
