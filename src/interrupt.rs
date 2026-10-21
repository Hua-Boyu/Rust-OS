use crate::io;
use crate::io::ports::{PortAllocator, lockfree_inb, lockfree_outb};
use crate::println;
use crate::utils::bits::CanManipulateBits;

use core::arch::asm;

const IDT_TABLE_SIZE: usize = 256;
type InterruptServiceRoutine = extern "x86-interrupt" fn(InterruptStackFrame);

static mut INTERRUPT_TABLE: InterruptTable = InterruptTable::new();

// Hardware IRQ vectors after remap: master 0x20-0x27, slave 0x28-0x2F.
const HW_IRQ_BASE: usize = 0x20;
const HW_IRQ_END: usize = 0x30;

// IRQs we actually service: IRQ0 (PIT timer) and IRQ1 (keyboard). Everything
// else on the PIC is masked. The previous build unmasked all 16 IRQs, so every
// spurious/stray line (cascade IRQ2, LINT0/1, unused lines) reached the dummy
// handler and printed on every hit — the "hw irq dummy" flood. Masking the
// unused lines stops the flood at the source; the bounded counters below still
// report any unexpected vector that does arrive.
const MASTER_MASK: u8 = 0xFC; // unmask IRQ0, IRQ1 only
const SLAVE_MASK: u8 = 0xFF; // no slave IRQs serviced

// Bounded diagnostics: print each vector at most once (exceptions 0-31, hw IRQ
// vectors 0x20-0x2F share the same table), and count unexpected hits without
// printing per hit.
static mut EXCEPTION_COUNTS: [u32; 256] = [0; 256];
static UNEXPECTED_TOTAL: core::sync::atomic::AtomicU32 = core::sync::atomic::AtomicU32::new(0);

#[allow(dead_code)]
#[repr(u8)]
pub enum GateType {
    Task = 0b0101,
    Interrupt16Bit = 0b0110,
    Trap16Bit = 0b0111,
    Interrupt32Bit = 0b1110,
    Trap32Bit = 0b1111,
}

#[allow(dead_code)] // we are not reading the interior of the Entry struct.
#[derive(Clone, Copy)]
pub struct Entry(pub u64);

impl Entry {
    pub const fn new_invalid() -> Self {
        Entry(0)
    }

    // create a new initialised interrupt table entry:
    // dpl refers to the cpu priv level which is able to trigger this
    // the cast to u32 is intentional: IDT gate offsets are 32-bit fields.
    #[allow(clippy::fn_to_numeric_cast)]
    pub fn new(
        isr: InterruptServiceRoutine,
        segment_selector: u16,
        gate_type: GateType,
        dpl: u8,
    ) -> Self {
        // write the isr address
        let isr_offset = isr as u32;
        Entry(
            0u64.set_bits(0, 16, u64::from(isr_offset))
                .set_bits(48, 16, u64::from(isr_offset >> 16))
                .set_bits(16, 16, u64::from(segment_selector))
                .set_bits(40, 4, u64::from(gate_type as u8))
                .set_bits(45, 2, u64::from(dpl))
                .set_one_bit(47, true), // enable bit
        )
    }
}

struct InterruptTable {
    inner: [Entry; IDT_TABLE_SIZE],
}

impl InterruptTable {
    const fn new() -> Self {
        Self {
            inner: [Entry::new_invalid(); IDT_TABLE_SIZE],
        }
    }

    fn set_interrupt(&mut self, entry_id: usize, isr: InterruptServiceRoutine) {
        let entry = Entry::new(isr, 0x08, GateType::Interrupt32Bit, 0);
        self.inner[entry_id] = entry;
    }

    /// Entry for an ISR with a different stack-frame shape (e.g. the page
    /// fault handler, which receives the CPU-pushed error code). The gate
    /// encoding is identical; only the handler signature differs, so we pass
    /// the code offset directly.
    #[allow(clippy::fn_to_numeric_cast)]
    fn set_interrupt_offset(&mut self, entry_id: usize, isr_offset: u32) {
        let entry = Entry(
            0u64.set_bits(0, 16, u64::from(isr_offset))
                .set_bits(48, 16, u64::from(isr_offset >> 16))
                .set_bits(16, 16, 0x08)
                .set_bits(40, 4, u64::from(GateType::Interrupt32Bit as u8))
                .set_bits(45, 2, 0)
                .set_one_bit(47, true),
        );
        self.inner[entry_id] = entry;
    }

    fn load(&mut self) {
        // Fill unfilled entries: CPU exception range gets the per-vector
        // exception handlers (never send PIC EOI — exceptions are not PIC
        // IRQs), hardware IRQ range gets the EOI-sending variant, everything
        // else a plain dummy.
        let hw_handlers: [InterruptServiceRoutine; 16] = [
            isr_irq20, isr_irq21, isr_irq22, isr_irq23, isr_irq24, isr_irq25, isr_irq26, isr_irq27,
            isr_irq28, isr_irq29, isr_irq2A, isr_irq2B, isr_irq2C, isr_irq2D, isr_irq2E, isr_irq2F,
        ];
        let plain_entry = Entry::new(isr_dummy_handler, 0x08, GateType::Interrupt32Bit, 0);
        // CPU vectors were installed explicitly before load; never substitute
        // an IRQ/compiler-ABI handler for the normalized fatal-only entries.
        for (i, entry) in self.inner.iter_mut().enumerate().skip(32) {
            let c = entry.0;
            if c.get_bits(0, 16) == 0 && c.get_bits(48, 16) == 0 {
                *entry = if (HW_IRQ_BASE..HW_IRQ_END).contains(&i) {
                    Entry::new(
                        hw_handlers[i - HW_IRQ_BASE],
                        0x08,
                        GateType::Interrupt32Bit,
                        0,
                    )
                } else {
                    plain_entry
                };
            }
        }

        let idtr = Idtr {
            limit: (IDT_TABLE_SIZE * 8 - 1) as u16,
            base: self.inner.as_ptr() as u32,
        };

        #[cfg(not(test))]
        unsafe {
            asm!(r#"
                lidt ({idtr})
                sti
            "#, idtr = in (reg) &idtr, options(att_syntax));
        }
    }
}

#[derive(Debug)]
#[repr(C, packed)]
struct Idtr {
    limit: u16,
    base: u32,
}

// F3 only: the caller has retained/validated both TSSes and loaded TR18.
// Do not reuse InterruptTable::load: it enables interrupts and rewrites gates.
const DOUBLE_FAULT_TASK_GATE: u64 = 0x0000_8500_0020_0000;

#[cfg(not(test))]
pub(crate) fn install_double_fault_task_gate() -> bool {
    let flags: u32;
    unsafe {
        asm!("pushfd", "pop {flags:e}", flags = out(reg) flags, options(preserves_flags));
    }
    if flags & (1 << 9) != 0 {
        return false;
    }
    let idtr = get_idtr();
    let base = core::ptr::addr_of!(INTERRUPT_TABLE).cast::<u8>() as u32;
    if idtr.base != base || idtr.limit != (IDT_TABLE_SIZE * 8 - 1) as u16 {
        return false;
    }
    // Validate the complete table's actual writable supervisor identity mapping
    // before touching the gate. IF remains clear throughout the two wire stores.
    if !crate::gdt_tss::writable_kernel_identity(base, IDT_TABLE_SIZE * 8) {
        return false;
    }
    unsafe {
        let gate = (base as *mut u32).add(8 * 2);
        core::ptr::write_volatile(gate, DOUBLE_FAULT_TASK_GATE as u32);
        core::ptr::write_volatile(gate.add(1), (DOUBLE_FAULT_TASK_GATE >> 32) as u32);
    }
    double_fault_task_gate_installed()
}

/// Actual SIDT plus raw gate readback, not a cached software-ready flag.
#[cfg(not(test))]
pub(crate) fn double_fault_task_gate_installed() -> bool {
    let idtr = get_idtr();
    let base = core::ptr::addr_of!(INTERRUPT_TABLE).cast::<u8>() as u32;
    if idtr.base != base || idtr.limit != (IDT_TABLE_SIZE * 8 - 1) as u16 {
        return false;
    }
    if !crate::gdt_tss::writable_kernel_identity(base, IDT_TABLE_SIZE * 8) {
        return false;
    }
    unsafe {
        let gate = (base as *const u32).add(8 * 2);
        core::ptr::read_volatile(gate) == DOUBLE_FAULT_TASK_GATE as u32
            && core::ptr::read_volatile(gate.add(1)) == (DOUBLE_FAULT_TASK_GATE >> 32) as u32
    }
}

#[derive(Debug, Clone, Copy)]
#[repr(C, packed)]
pub struct InterruptStackFrame {
    _unimplemented: [u8; 48],
    // pub instruction_ptr: _,
    // pub code_segment: _,
    // _reserved: [u8; 6],
    // pub cpu_flags: _,
    // pub stack_ptr: _,
    // pub stack_segment: _,
    // _reserved2: [u8; 6],
}

fn remap_pic(palloc: &mut PortAllocator) {
    let mut pic1_command = palloc.allocate(0x20).expect("Master PIC command port");
    let mut pic1_data = palloc.allocate(0x21).expect("Master PIC data port");
    let mut pic2_command = palloc.allocate(0xA0).expect("Slave PIC command port");
    let mut pic2_data = palloc.allocate(0xA1).expect("Slave PIC data port");

    // initialise PIC with ICW4. ICW sequence requires an I/O delay between
    // writes (the PIC latches one ICW at a time); without it, back-to-back
    // outs on fast emulated hardware can merge and corrupt the sequence.
    pic1_command.outb(0x11);
    io_wait();
    pic2_command.outb(0x11);
    io_wait();

    // remap master PIC to 0x20, slave to 0x28
    pic1_data.outb(0x20);
    io_wait();
    pic2_data.outb(0x28);
    io_wait();

    pic1_data.outb(0x04);
    io_wait(); // tell master PIC there is a slave at IRQ2
    pic2_data.outb(0x02);
    io_wait(); // cascade ident

    // use 8086 mode
    pic1_data.outb(0x01);
    io_wait();
    pic2_data.outb(0x01);
    io_wait();

    // mask everything except the IRQs we service (see MASTER_MASK above).
    // Bit set = masked. IRQ1 (keyboard) and IRQ0 (PIT) unmasked on master.
    pic1_data.outb(MASTER_MASK);
    io_wait();
    pic2_data.outb(SLAVE_MASK);
    io_wait();
}

fn io_wait() {
    unsafe { crate::io::ports::io_wait() }
}

/// EOI for a hardware IRQ vector. Slave vectors (0x28-0x2F) must acknowledge
/// the slave PIC AND the cascade line on the master; master vectors only the
/// master. Sending EOI to the wrong PIC leaves the other latched.
unsafe fn pic_send_eoi(vector: usize) {
    unsafe {
        if (0x28..0x30).contains(&vector) {
            lockfree_outb(0xA0, 0x20); // slave
            lockfree_outb(0x20, 0x20); // master (cascade IRQ2)
        } else {
            lockfree_outb(0x20, 0x20); // master
        }
    }
}

pub fn init_idt(palloc: &mut PortAllocator) {
    println!("old idtr: {:?}", get_idtr());

    remap_pic(palloc);

    // load IDT
    unsafe {
        let t = (&raw mut INTERRUPT_TABLE)
            .as_mut()
            .expect("interrupt table is free");

        // All CPU vectors use the explicit fatal-only F2 assembly ABI.
        // This table includes frame-independent unsupported-vector stubs.
        for vector in 0..32 {
            t.set_interrupt_offset(vector, crate::exception_fatal::f2_exception_entries[vector]);
        }
        t.set_interrupt(0x20, isr_timer_handler);
        t.set_interrupt(0x21, isr_keyboard_handler);
        t.load();
    }

    println!("new idtr: {:?}", get_idtr());
}

pub fn page_fault_count() -> u32 {
    crate::exception_fatal::page_fault_count()
}

pub fn last_page_fault() -> Option<crate::memory::paging::PageFaultInfo> {
    crate::exception_fatal::last_page_fault()
}

fn get_idtr() -> Idtr {
    #[cfg(test)]
    return Idtr { limit: 0, base: 0 }; // host tests cannot execute sidt
    #[allow(unreachable_code)]
    {
        let mut r = core::mem::MaybeUninit::uninit();
        unsafe {
            asm!("sidt ({})", in (reg) r.as_mut_ptr(), options(att_syntax, nostack, preserves_flags));
            r.assume_init()
        }
    }
}

extern "x86-interrupt" fn isr_keyboard_handler(_isf: InterruptStackFrame) {
    unsafe {
        // Short ISR: read the scancode, enqueue a compact event, acknowledge.
        // Decoding/console logic happens in the main loop (src/shell.rs).
        // No println!, no allocation, no mutex-backed writer here.
        let sc = lockfree_inb(0x60);
        crate::kbd::RING.push(sc);
        pic_send_eoi(0x21);
    }
}

extern "x86-interrupt" fn isr_timer_handler(_isf: InterruptStackFrame) {
    unsafe {
        crate::timer::isr_timer(); // atomic increment only, never prints
        pic_send_eoi(0x20);
    }
}

macro_rules! hw_irq_handler {
    ($name:ident, $vector:expr) => {
        extern "x86-interrupt" fn $name(_isf: InterruptStackFrame) {
            // Unexpected hardware IRQ on a vector we don't service. The line
            // is masked at the PIC, so this only fires if something re-enabled
            // it. Acknowledge with EOI to the correct PIC (slave vectors need
            // the cascade EOI on the master too), count it, print at most once
            // per vector so a stray line cannot flood the log.
            unsafe {
                use core::fmt::Write;
                if EXCEPTION_COUNTS[$vector] == 0 {
                    let _ = writeln!(
                        io::serial::SerialWriter,
                        "unexpected hw irq vector {:#04x}",
                        $vector
                    );
                }
                EXCEPTION_COUNTS[$vector] += 1;
                pic_send_eoi($vector);
            }
        }
    };
}

hw_irq_handler!(isr_irq20, 0x20);
hw_irq_handler!(isr_irq21, 0x21);
hw_irq_handler!(isr_irq22, 0x22);
hw_irq_handler!(isr_irq23, 0x23);
hw_irq_handler!(isr_irq24, 0x24);
hw_irq_handler!(isr_irq25, 0x25);
hw_irq_handler!(isr_irq26, 0x26);
hw_irq_handler!(isr_irq27, 0x27);
hw_irq_handler!(isr_irq28, 0x28);
hw_irq_handler!(isr_irq29, 0x29);
hw_irq_handler!(isr_irq2A, 0x2A);
hw_irq_handler!(isr_irq2B, 0x2B);
hw_irq_handler!(isr_irq2C, 0x2C);
hw_irq_handler!(isr_irq2D, 0x2D);
hw_irq_handler!(isr_irq2E, 0x2E);
hw_irq_handler!(isr_irq2F, 0x2F);

extern "x86-interrupt" fn isr_dummy_handler(_isf: InterruptStackFrame) {
    unsafe {
        UNEXPECTED_TOTAL.fetch_add(1, core::sync::atomic::Ordering::Relaxed);
        halt_forever();
    }
}

fn halt_forever() -> ! {
    unsafe {
        asm!("cli", options(att_syntax));
        loop {
            asm!("hlt", options(att_syntax));
        }
    }
}

pub fn unexpected_irq_total() -> u32 {
    UNEXPECTED_TOTAL.load(core::sync::atomic::Ordering::Relaxed)
}
