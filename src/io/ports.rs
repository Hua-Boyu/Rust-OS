use core::arch::asm;

/// This struct HAS to be 'static OR guaranteed to outlive ANY Port instance it creates.
pub struct PortAllocator {
    used: [bool; 0x10000],
}

impl PortAllocator {
    pub const fn new() -> PortAllocator {
        PortAllocator {
            used: [false; 0x10000],
        }
    }

    pub fn allocate(&mut self, port_id: u16) -> Option<Port> {
        if !self.used[port_id as usize] {
            self.used[port_id as usize] = true;
            return Some(Port {
                addr: port_id,
                parent_allocator: self as *const _ as *mut _,
            });
        }

        None
    }

    /// Validate the whole set before reserving kernel-lifetime ports.
    pub fn reserve_permanent(&mut self, ports: &[u16]) -> bool {
        for (i, &port) in ports.iter().enumerate() {
            if self.used[port as usize] || ports[..i].contains(&port) {
                return false;
            }
        }
        for &port in ports {
            self.used[port as usize] = true;
        }
        true
    }

    pub fn release(&mut self, port_id: u16) {
        self.used[port_id as usize] = false;
    }
}

pub struct Port {
    pub addr: u16,
    parent_allocator: *mut PortAllocator,
}

impl Port {
    pub fn inb(&mut self) -> u8 {
        let mut ret;
        unsafe {
            asm!("in %dx, %al", in("dx") self.addr, out("al") ret, options(att_syntax));
        }
        ret
    }

    pub fn outb(&mut self, b: u8) {
        unsafe {
            asm!("out %al, %dx", in("dx") self.addr, in("al") b, options(att_syntax));
        }
    }
}

impl Drop for Port {
    fn drop(&mut self) {
        unsafe { (*self.parent_allocator).release(self.addr) }
    }
}

pub unsafe fn lockfree_inb(port_in: u16) -> u8 {
    #[cfg(test)]
    return 0; // host tests cannot execute privileged `in` instructions
    #[allow(unreachable_code)]
    {
        let mut ret;
        unsafe {
            asm!("in %dx, %al", in("dx") port_in, out("al") ret, options(att_syntax));
        }
        ret
    }
}

pub unsafe fn lockfree_inw(port_in: u16) -> u16 {
    #[cfg(test)]
    return 0; // host tests cannot execute privileged `in` instructions
    #[allow(unreachable_code)]
    {
        let mut ret;
        unsafe {
            asm!("in %dx, %ax", in("dx") port_in, out("ax") ret, options(att_syntax));
        }
        ret
    }
}

/// Short I/O delay (~1 microsecond) via an unused ISA port. Needed after PIC
/// commands and the reboot command, where the hardware requires a delay
/// between writes.
pub unsafe fn io_wait() {
    #[cfg(test)]
    return;
    #[allow(unreachable_code)]
    unsafe {
        asm!("out %al, %dx", in("dx") 0x80u16, in("al") 0u8, options(att_syntax, nomem));
    }
}

pub unsafe fn lockfree_outb(port_out: u16, val: u8) {
    #[cfg(test)]
    return; // host tests cannot execute privileged `out` instructions
    #[allow(unreachable_code)]
    unsafe {
        asm!("out %al, %dx", in("dx") port_out, in("al") val, options(att_syntax));
    }
}

pub unsafe fn lockfree_outw(port_out: u16, val: u16) {
    #[cfg(test)]
    return; // host tests cannot execute privileged `out` instructions
    #[allow(unreachable_code)]
    unsafe {
        asm!("out %ax, %dx", in("dx") port_out, in("ax") val, options(att_syntax));
    }
}
