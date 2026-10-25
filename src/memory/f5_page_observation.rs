//! Opt-in host transport and fixed-capacity observation of real arena writes.
//! No callbacks, allocation, or permissions bypass during installation.
use super::*;
use std::cell::RefCell;

pub(crate) struct Observation {
    pub code_address: u64,
    pub stack_address: u64,
    pub code: [u8; PAGE_SIZE],
    pub stack: [u8; PAGE_SIZE],
    pub initialized_code: [u8; PAGE_SIZE],
    pub initialized_stack: [u8; PAGE_SIZE],
    pub events: [[u32; 11]; 8],
    pub prepublication_code: [u8; PAGE_SIZE],
    pub prepublication_stack: [u8; PAGE_SIZE],
    pub count: usize,
}

std::thread_local! {
    static OBSERVATION: RefCell<Option<Box<Observation>>> = const { RefCell::new(None) };
}

/// Allocate all backing before taking production guards or admission.
pub(crate) fn enable() {
    OBSERVATION.with(|slot| {
        assert!(slot.borrow().is_none());
        *slot.borrow_mut() = Some(Box::new(Observation {
            code_address: 0,
            stack_address: 0,
            code: [0xa5; PAGE_SIZE],
            stack: [0xa5; PAGE_SIZE],
            initialized_code: [0; PAGE_SIZE],
            initialized_stack: [0; PAGE_SIZE],
            events: [[0; 11]; 8],
            prepublication_code: [0; PAGE_SIZE],
            prepublication_stack: [0; PAGE_SIZE],
            count: 0,
        }));
    });
}

pub(super) fn initialize(code: u64, stack: u64, image: Image) -> bool {
    OBSERVATION.with(|slot| {
        let mut borrow = slot.borrow_mut();
        let Some(o) = borrow.as_mut() else {
            return image == Image::F4;
        };
        if o.code_address != 0 || o.stack_address != 0 || code == stack {
            return false;
        }
        o.code_address = code;
        o.stack_address = stack;
        // Only transport changes. This is the same private production initializer.
        unsafe {
            initialize_pages(o.code.as_mut_ptr(), o.stack.as_mut_ptr(), image);
        }
        o.initialized_code.copy_from_slice(&o.code);
        o.initialized_stack.copy_from_slice(&o.stack);
        true
    })
}

pub(super) fn event(
    stage: u32,
    owner: &RetainedOwner,
    pm: &PageMap,
    fa: &FrameAllocator,
    code: u64,
    stack: u64,
    table: u64,
) {
    OBSERVATION.with(|slot| {
        let mut borrow = slot.borrow_mut();
        if let Some(o) = borrow.as_mut() {
            assert!(o.count < o.events.len());
            assert_eq!((o.code_address, o.stack_address), (code, stack));
            o.events[o.count] = [
                stage,
                read_entry(pm.directory, 256),
                read_entry(table, 0),
                read_entry(table, 1023),
                fa.runtime_pinned(code) as u32,
                fa.runtime_pinned(stack) as u32,
                fa.structure_pinned(table) as u32,
                payload_bit(&pm.payload_bitmap, code) as u32,
                payload_bit(&pm.payload_bitmap, stack) as u32,
                distinct(owner, fa) as u32,
                owner.capture[1],
            ];
            if stage == 8 {
                o.prepublication_code.copy_from_slice(&o.code);
                o.prepublication_stack.copy_from_slice(&o.stack);
            }
            o.count += 1;
        }
    });
}

pub(super) fn valid_image(code: u64, stack: u64) -> bool {
    OBSERVATION.with(|slot| {
        let borrow = slot.borrow();
        let Some(o) = borrow.as_ref() else {
            return false;
        };
        o.code_address == code
            && o.stack_address == stack
            && unsafe { image_matches(o.code.as_ptr(), o.stack.as_ptr(), Image::F5) }
    })
}

/// Move preallocated observations out after all production guards are dropped.
pub(crate) fn take() -> Box<Observation> {
    OBSERVATION.with(|slot| slot.borrow_mut().take().expect("observation enabled"))
}
