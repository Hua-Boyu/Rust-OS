// P12-A pure scheduling-policy model (host-only, Class T).
//
// This module is a *policy model*: it decides which abstract task should run
// next, but it never switches to it, never touches hardware, and is never
// linked into the production kernel. All state is per-instance; there is no
// global mutable state, no allocation, no I/O, no time, no unsafe, no
// recursion, no unbounded loops, and no panics-by-design.
//
// Contract: test_results/phase12_p12a/p12a_contract.md (v01, approved).
// Semantics: two permanently consumed task slots (ids 1..=254; 0 reserved
// unused, 255 reserved invalid), a FIFO queue of Ready ids in admission
// order, exactly one Running worker iff current is a matching Worker,
// checked u8 inhibit depth (max 255), coalesced pending reschedule drained
// only by the final leave_inhibit. Every error return is non-mutating.
// This source deliberately has no #![no_std] attribute: the standalone
// no_std verification wrapper supplies it via #[path] (see contract).

#[derive(Clone, Copy, Debug, PartialEq)]
pub enum State {
    Unused,
    Ready,
    Running,
    Retired,
}

#[derive(Clone, Copy, Debug, PartialEq)]
pub enum Context {
    Idle,
    Worker(u8),
}

#[derive(Clone, Copy, Debug, PartialEq)]
pub enum TaskKind {
    KernelProbe,
    Cpl3,
    F5,
}

#[derive(Clone, Copy, Debug, PartialEq)]
pub enum Error {
    InvalidId,
    UnknownId,
    DuplicateId,
    RetiredId,
    Capacity,
    InvalidTransition,
    UnsupportedKind,
    Inhibited,
    InhibitOverflow,
    InhibitUnderflow,
}

#[derive(Clone, Copy, Debug, PartialEq)]
pub struct Slot {
    pub id: u8,
    pub state: State,
}

#[derive(Clone, Copy, Debug, PartialEq)]
pub struct Snapshot {
    pub slots: [Slot; 2],
    pub queue: [u8; 2],
    pub queue_len: u8,
    pub current: Context,
    pub inhibit_depth: u8,
    pub pending: bool,
}

pub struct Policy {
    snap: Snapshot,
}

impl Policy {
    pub fn new() -> Policy {
        return Policy {
            snap: Snapshot {
                slots: [
                    Slot { id: 0, state: State::Unused },
                    Slot { id: 0, state: State::Unused },
                ],
                queue: [0, 0],
                queue_len: 0,
                current: Context::Idle,
                inhibit_depth: 0,
                pending: false,
            },
        };
    }

    pub fn snapshot(self: &Policy) -> Snapshot {
        return self.snap;
    }

    pub fn state(self: &Policy, id: u8) -> Result<State, Error> {
        if id == 0 || id == 255 {
            return Err(Error::InvalidId);
        }
        let i = find_slot(self.snap.slots, id);
        if i == 2 {
            return Err(Error::UnknownId);
        }
        return Ok(self.snap.slots[i].state);
    }

    pub fn admit(self: &mut Policy, id: u8, kind: TaskKind) -> Result<(), Error> {
        if id == 0 || id == 255 {
            return Err(Error::InvalidId);
        }
        if kind != TaskKind::KernelProbe {
            return Err(Error::UnsupportedKind);
        }
        let i = find_slot(self.snap.slots, id);
        if i != 2 {
            if self.snap.slots[i].state == State::Retired {
                return Err(Error::RetiredId);
            }
            return Err(Error::DuplicateId);
        }
        if self.snap.inhibit_depth > 0 {
            return Err(Error::Inhibited);
        }
        let free = first_unused(self.snap.slots);
        if free == 2 {
            return Err(Error::Capacity);
        }
        self.snap.slots[free] = Slot { id: id, state: State::Ready };
        self.snap.queue[self.snap.queue_len as usize] = id;
        self.snap.queue_len = self.snap.queue_len + 1;
        return Ok(());
    }

    pub fn request_reschedule(self: &mut Policy) -> Context {
        if self.snap.inhibit_depth > 0 {
            self.snap.pending = true;
            return self.snap.current;
        }
        return do_reschedule(self);
    }

    pub fn complete(self: &mut Policy, id: u8) -> Result<Context, Error> {
        if id == 0 || id == 255 {
            return Err(Error::InvalidId);
        }
        let i = find_slot(self.snap.slots, id);
        if i == 2 {
            return Err(Error::UnknownId);
        }
        if self.snap.slots[i].state == State::Retired {
            return Err(Error::RetiredId);
        }
        if self.snap.slots[i].state != State::Running {
            return Err(Error::InvalidTransition);
        }
        if !current_matches(self.snap.current, id) {
            return Err(Error::InvalidTransition);
        }
        if self.snap.inhibit_depth > 0 {
            return Err(Error::Inhibited);
        }
        self.snap.slots[i].state = State::Retired;
        return Ok(select_after_retire(self));
    }

    pub fn enter_inhibit(self: &mut Policy) -> Result<(), Error> {
        if self.snap.inhibit_depth == 255 {
            return Err(Error::InhibitOverflow);
        }
        self.snap.inhibit_depth = self.snap.inhibit_depth + 1;
        return Ok(());
    }

    pub fn leave_inhibit(self: &mut Policy) -> Result<Context, Error> {
        if self.snap.inhibit_depth == 0 {
            return Err(Error::InhibitUnderflow);
        }
        self.snap.inhibit_depth = self.snap.inhibit_depth - 1;
        if self.snap.inhibit_depth > 0 {
            return Ok(self.snap.current);
        }
        if self.snap.pending {
            self.snap.pending = false;
            return Ok(do_reschedule(self));
        }
        return Ok(self.snap.current);
    }
}

fn find_slot(slots: [Slot; 2], id: u8) -> usize {
    for i in 0..2 {
        if slots[i].id == id && slots[i].state != State::Unused {
            return i;
        }
    }
    return 2;
}

fn first_unused(slots: [Slot; 2]) -> usize {
    for i in 0..2 {
        if slots[i].state == State::Unused {
            return i;
        }
    }
    return 2;
}

fn current_matches(current: Context, id: u8) -> bool {
    match current {
        Context::Worker(c) => {
            return c == id;
        }
        Context::Idle => {
            return false;
        }
    }
}

// Ordinary reschedule at depth 0: yield the current Running worker to the
// FIFO tail (it is never already queued), then dequeue the head. Index
// bounds: an appended id is never in the queue, and at most two slots exist,
// so queue_len <= 1 whenever an append happens; the append index is checked.
fn do_reschedule(p: &mut Policy) -> Context {
    match p.snap.current {
        Context::Worker(id) => {
            let i = find_slot(p.snap.slots, id);
            if i != 2 && p.snap.slots[i].state == State::Running {
                p.snap.slots[i].state = State::Ready;
                if p.snap.queue_len < 2 {
                    p.snap.queue[p.snap.queue_len as usize] = id;
                    p.snap.queue_len = p.snap.queue_len + 1;
                }
            }
        }
        Context::Idle => {}
    }
    return dequeue_and_run(p);
}

fn dequeue_and_run(p: &mut Policy) -> Context {
    if p.snap.queue_len == 0 {
        p.snap.current = Context::Idle;
        return Context::Idle;
    }
    let head = p.snap.queue[0];
    p.snap.queue[0] = p.snap.queue[1];
    p.snap.queue[1] = 0;
    p.snap.queue_len = p.snap.queue_len - 1;
    let i = find_slot(p.snap.slots, head);
    if i != 2 && p.snap.slots[i].state == State::Ready {
        p.snap.slots[i].state = State::Running;
    }
    p.snap.current = Context::Worker(head);
    return Context::Worker(head);
}

// After logical retirement the retired worker is never requeued; select the
// next Ready head, or Idle when none remains.
fn select_after_retire(p: &mut Policy) -> Context {
    return dequeue_and_run(p);
}
