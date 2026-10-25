use crate::p12a_policy::{Context, Error, Policy, Slot, Snapshot, State, TaskKind};

fn fresh() -> Policy {
    Policy::new()
}

fn unused() -> Slot {
    Slot {
        id: 0,
        state: State::Unused,
    }
}

fn ready(id: u8) -> Slot {
    Slot {
        id,
        state: State::Ready,
    }
}

fn running(id: u8) -> Slot {
    Slot {
        id,
        state: State::Running,
    }
}

fn retired(id: u8) -> Slot {
    Slot {
        id,
        state: State::Retired,
    }
}

#[test]
fn empty_policy_selects_idle() {
    fn eq_bound<T: Eq>() {}
    eq_bound::<State>();
    eq_bound::<Context>();
    eq_bound::<TaskKind>();
    eq_bound::<Error>();
    eq_bound::<Slot>();
    eq_bound::<Snapshot>();
    const INITIAL: Policy = Policy::new();
    let mut p = INITIAL;
    assert_eq!(
        p.snapshot(),
        Snapshot {
            slots: [unused(), unused()],
            queue: [0, 0],
            queue_len: 0,
            current: Context::Idle,
            inhibit_depth: 0,
            pending: false,
        }
    );
    assert_eq!(p.request_reschedule(), Context::Idle);
    let s = p.snapshot();
    assert_eq!(s.current, Context::Idle);
    assert_eq!(s.slots, [unused(), unused()]);
    assert_eq!(s.queue_len, 0);
    assert_eq!(s.inhibit_depth, 0);
    assert!(!s.pending);
}

#[test]
fn admission_does_not_switch_idle() {
    let mut p = fresh();
    assert_eq!(p.admit(7, TaskKind::KernelProbe), Ok(()));
    let s = p.snapshot();
    assert_eq!(s.slots[0], ready(7));
    assert_eq!(s.slots[1], unused());
    assert_eq!(s.current, Context::Idle);
    assert_eq!(s.queue_len, 1);
    assert_eq!(s.queue[0], 7);
}

#[test]
fn single_worker_repeated_yield() {
    let mut p = fresh();
    assert_eq!(p.admit(7, TaskKind::KernelProbe), Ok(()));
    assert_eq!(p.request_reschedule(), Context::Worker(7));
    let s = p.snapshot();
    assert_eq!(s.slots[0], running(7));
    assert_eq!(s.current, Context::Worker(7));
    assert_eq!(p.request_reschedule(), Context::Worker(7));
    let s = p.snapshot();
    assert_eq!(s.slots[0], running(7));
    assert_eq!(s.current, Context::Worker(7));
}

#[test]
fn two_workers_fifo_round_robin() {
    let mut p = fresh();
    assert_eq!(p.admit(7, TaskKind::KernelProbe), Ok(()));
    assert_eq!(p.admit(5, TaskKind::KernelProbe), Ok(()));
    assert_eq!(p.request_reschedule(), Context::Worker(7));
    assert_eq!(p.request_reschedule(), Context::Worker(5));
    assert_eq!(p.request_reschedule(), Context::Worker(7));
    assert_eq!(p.request_reschedule(), Context::Worker(5));
}

#[test]
fn admission_order_breaks_ties() {
    let mut p = fresh();
    assert_eq!(p.admit(5, TaskKind::KernelProbe), Ok(()));
    assert_eq!(p.admit(7, TaskKind::KernelProbe), Ok(()));
    let s = p.snapshot();
    assert_eq!(s.queue[0..2], [5, 7]);
    assert_eq!(s.queue_len, 2);
}

#[test]
fn last_worker_completion_returns_idle() {
    let mut p = fresh();
    assert_eq!(p.admit(7, TaskKind::KernelProbe), Ok(()));
    assert_eq!(p.request_reschedule(), Context::Worker(7));
    assert_eq!(p.complete(7), Ok(Context::Idle));
    let s = p.snapshot();
    assert_eq!(s.current, Context::Idle);
    assert_eq!(s.slots[0], retired(7));
    assert_eq!(s.slots[1], unused());
}

#[test]
fn completion_selects_next_ready() {
    let mut p = fresh();
    assert_eq!(p.admit(7, TaskKind::KernelProbe), Ok(()));
    assert_eq!(p.admit(5, TaskKind::KernelProbe), Ok(()));
    assert_eq!(p.request_reschedule(), Context::Worker(7));
    assert_eq!(p.complete(7), Ok(Context::Worker(5)));
    let s = p.snapshot();
    assert_eq!(s.slots[0], retired(7));
    assert_eq!(s.slots[1], running(5));
    assert_eq!(s.current, Context::Worker(5));
}

#[test]
fn retired_identity_never_reused() {
    let mut p = fresh();
    assert_eq!(p.admit(7, TaskKind::KernelProbe), Ok(()));
    assert_eq!(p.request_reschedule(), Context::Worker(7));
    assert_eq!(p.complete(7), Ok(Context::Idle));
    let before = p.snapshot();
    assert_eq!(p.admit(7, TaskKind::KernelProbe), Err(Error::RetiredId));
    assert_eq!(p.snapshot(), before);
}

#[test]
fn capacity_exhaustion_is_nonmutating() {
    let mut p = fresh();
    assert_eq!(p.admit(7, TaskKind::KernelProbe), Ok(()));
    assert_eq!(p.admit(5, TaskKind::KernelProbe), Ok(()));
    let before = p.snapshot();
    assert_eq!(p.admit(11, TaskKind::KernelProbe), Err(Error::Capacity));
    assert_eq!(p.snapshot(), before);
}

#[test]
fn invalid_identifiers_are_nonmutating() {
    let mut p = fresh();
    let before = p.snapshot();
    assert_eq!(p.admit(0, TaskKind::KernelProbe), Err(Error::InvalidId));
    assert_eq!(p.admit(255, TaskKind::KernelProbe), Err(Error::InvalidId));
    assert_eq!(p.state(0), Err(Error::InvalidId));
    assert_eq!(p.complete(255), Err(Error::InvalidId));
    assert_eq!(p.snapshot(), before);
}

#[test]
fn unknown_identifiers_are_nonmutating() {
    let mut p = fresh();
    assert_eq!(p.state(99), Err(Error::UnknownId));
    let before = p.snapshot();
    assert_eq!(p.complete(99), Err(Error::UnknownId));
    assert_eq!(p.snapshot(), before);
}

#[test]
fn duplicate_admission_is_nonmutating() {
    let mut p = fresh();
    assert_eq!(p.admit(7, TaskKind::KernelProbe), Ok(()));
    let before = p.snapshot();
    assert_eq!(p.admit(7, TaskKind::KernelProbe), Err(Error::DuplicateId));
    assert_eq!(p.snapshot(), before);
}

#[test]
fn invalid_completion_is_nonmutating() {
    let mut p = fresh();
    let before = p.snapshot();
    assert_eq!(p.complete(7), Err(Error::UnknownId));
    assert_eq!(p.snapshot(), before);
    assert_eq!(p.admit(7, TaskKind::KernelProbe), Ok(()));
    let before = p.snapshot();
    assert_eq!(p.complete(7), Err(Error::InvalidTransition));
    assert_eq!(p.snapshot(), before);
}

#[test]
fn unsupported_kinds_are_nonmutating() {
    let mut p = fresh();
    let before = p.snapshot();
    assert_eq!(p.admit(7, TaskKind::Cpl3), Err(Error::UnsupportedKind));
    assert_eq!(p.admit(7, TaskKind::F5), Err(Error::UnsupportedKind));
    assert_eq!(p.snapshot(), before);
}

#[test]
fn inhibit_latches_without_switching() {
    let mut p = fresh();
    assert_eq!(p.admit(7, TaskKind::KernelProbe), Ok(()));
    assert_eq!(p.request_reschedule(), Context::Worker(7));
    assert_eq!(p.enter_inhibit(), Ok(()));
    let before = p.snapshot();
    assert_eq!(p.request_reschedule(), Context::Worker(7));
    let after = p.snapshot();
    assert_eq!(after.current, Context::Worker(7));
    assert!(after.pending);
    assert_eq!(after.inhibit_depth, 1);
    assert_eq!(after.slots, before.slots);
    assert_eq!(after.queue, before.queue);
    assert_eq!(after.queue_len, before.queue_len);
}

#[test]
fn nested_inhibit_drains_only_at_zero() {
    let mut p = fresh();
    assert_eq!(p.admit(7, TaskKind::KernelProbe), Ok(()));
    assert_eq!(p.admit(5, TaskKind::KernelProbe), Ok(()));
    assert_eq!(p.request_reschedule(), Context::Worker(7));
    assert_eq!(p.enter_inhibit(), Ok(()));
    assert_eq!(p.enter_inhibit(), Ok(()));
    assert_eq!(p.request_reschedule(), Context::Worker(7));
    let s = p.snapshot();
    assert_eq!(s.inhibit_depth, 2);
    assert!(s.pending);
    assert_eq!(p.leave_inhibit(), Ok(Context::Worker(7)));
    let s = p.snapshot();
    assert_eq!(s.inhibit_depth, 1);
    assert!(s.pending);
    assert_eq!(s.current, Context::Worker(7));
    assert_eq!(p.leave_inhibit(), Ok(Context::Worker(5)));
    let s = p.snapshot();
    assert_eq!(s.inhibit_depth, 0);
    assert!(!s.pending);
    assert_eq!(s.current, Context::Worker(5));
}

#[test]
fn inhibit_overflow_is_nonmutating() {
    let mut p = fresh();
    for _ in 0..255 {
        assert_eq!(p.enter_inhibit(), Ok(()));
    }
    let before = p.snapshot();
    assert_eq!(p.enter_inhibit(), Err(Error::InhibitOverflow));
    assert_eq!(p.snapshot(), before);
}

#[test]
fn inhibit_underflow_is_nonmutating() {
    let mut p = fresh();
    let before = p.snapshot();
    assert_eq!(p.leave_inhibit(), Err(Error::InhibitUnderflow));
    assert_eq!(p.snapshot(), before);
}

#[test]
fn inhibited_completion_and_admission_refuse() {
    let mut p = fresh();
    assert_eq!(p.admit(7, TaskKind::KernelProbe), Ok(()));
    assert_eq!(p.request_reschedule(), Context::Worker(7));
    assert_eq!(p.enter_inhibit(), Ok(()));
    let before = p.snapshot();
    assert_eq!(p.complete(7), Err(Error::Inhibited));
    assert_eq!(p.snapshot(), before);
    assert_eq!(p.admit(11, TaskKind::KernelProbe), Err(Error::Inhibited));
    assert_eq!(p.snapshot(), before);
}

#[test]
fn pending_requests_coalesce_once() {
    let mut p = fresh();
    assert_eq!(p.admit(7, TaskKind::KernelProbe), Ok(()));
    assert_eq!(p.admit(5, TaskKind::KernelProbe), Ok(()));
    assert_eq!(p.request_reschedule(), Context::Worker(7));
    assert_eq!(p.enter_inhibit(), Ok(()));
    p.request_reschedule();
    p.request_reschedule();
    p.request_reschedule();
    let mid = p.snapshot();
    assert!(mid.pending);
    assert_eq!(mid.inhibit_depth, 1);
    assert_eq!(mid.current, Context::Worker(7));
    assert_eq!(p.leave_inhibit(), Ok(Context::Worker(5)));
    let s = p.snapshot();
    assert_eq!(s.current, Context::Worker(5));
    assert!(!s.pending);
    assert_eq!(s.inhibit_depth, 0);
}

#[test]
fn fresh_instances_are_isolated() {
    let mut p1 = fresh();
    assert_eq!(p1.admit(7, TaskKind::KernelProbe), Ok(()));
    let p2 = fresh();
    assert_eq!(p2.snapshot(), fresh().snapshot());
    assert_eq!(p1.snapshot().slots[0], ready(7));
}

#[test]
fn metadata_budget_and_bounded_trace() {
    assert!(core::mem::size_of::<Policy>() <= 1024);
    assert!(core::mem::size_of::<Snapshot>() <= 64);
}

#[derive(Clone, Copy, Debug)]
enum Op {
    Admit1,
    Admit2,
    Admit3,
    Reschedule,
    Complete1,
    Complete2,
    EnterInhibit,
    LeaveInhibit,
}

fn apply_op(p: &mut Policy, op: Op) -> Result<(), Error> {
    match op {
        Op::Admit1 => p.admit(1, TaskKind::KernelProbe),
        Op::Admit2 => p.admit(2, TaskKind::KernelProbe),
        Op::Admit3 => p.admit(3, TaskKind::KernelProbe),
        Op::Reschedule => {
            p.request_reschedule();
            Ok(())
        }
        Op::Complete1 => {
            p.complete(1)?;
            Ok(())
        }
        Op::Complete2 => {
            p.complete(2)?;
            Ok(())
        }
        Op::EnterInhibit => p.enter_inhibit(),
        Op::LeaveInhibit => {
            p.leave_inhibit()?;
            Ok(())
        }
    }
}

fn assert_invariants(s: Snapshot) {
    // IDs 0..=2 are the only valid task IDs used in the exhaustive trace;
    // 0 is reserved as unused.
    assert!(s.queue_len <= 2);
    let mut seen = [false; 256];
    for i in 0..s.queue_len {
        let id = s.queue[i as usize];
        assert!(id == 1 || id == 2 || id == 3);
        assert!(!seen[id as usize], "duplicate queue entry");
        seen[id as usize] = true;
        // queued id must be Ready in some slot
        let mut found = false;
        for slot in &s.slots {
            if slot.id == id && slot.state == State::Ready {
                found = true;
            }
        }
        assert!(found, "queued id {} not Ready", id);
    }
    // tail cells are zero
    for i in s.queue_len..2 {
        assert_eq!(s.queue[i as usize], 0);
    }
    // exactly one Running slot iff current is a matching Worker
    let running_count = s
        .slots
        .iter()
        .filter(|slot| slot.state == State::Running)
        .count();
    match s.current {
        Context::Idle => assert_eq!(running_count, 0),
        Context::Worker(id) => {
            assert_eq!(running_count, 1);
            assert!(
                s.slots
                    .iter()
                    .any(|slot| slot.id == id && slot.state == State::Running)
            );
        }
    }
    // occupied slots have distinct non-zero ids; Unused slots have id 0
    let mut ids = [false; 256];
    for slot in &s.slots {
        if slot.state == State::Unused {
            assert_eq!(slot.id, 0);
        } else {
            assert!(slot.id >= 1 && slot.id <= 254);
            assert!(!ids[slot.id as usize], "duplicate slot id");
            ids[slot.id as usize] = true;
        }
    }
    // Every Ready slot is queued exactly once; no other occupied slot is queued.
    for slot in &s.slots {
        if slot.state == State::Ready {
            assert_eq!(
                s.queue[..s.queue_len as usize]
                    .iter()
                    .filter(|&&id| id == slot.id)
                    .count(),
                1
            );
        } else if slot.state != State::Unused {
            assert!(!seen[slot.id as usize]);
        }
    }
    // Retired slots are not Ready/Running and not queued
    for slot in &s.slots {
        if slot.state == State::Retired {
            assert!(!s.queue.iter().any(|&q| q == slot.id));
        }
    }
    // pending implies inhibited
    if s.pending {
        assert!(s.inhibit_depth > 0);
    }
}

#[test]
fn exhaustive_short_traces_preserve_invariants() {
    let ops = [
        Op::Admit1,
        Op::Admit2,
        Op::Admit3,
        Op::Reschedule,
        Op::Complete1,
        Op::Complete2,
        Op::EnterInhibit,
        Op::LeaveInhibit,
    ];
    for a in ops {
        for b in ops {
            for c in ops {
                for d in ops {
                    let mut p = fresh();
                    for op in [a, b, c, d] {
                        let before = p.snapshot();
                        let r = apply_op(&mut p, op);
                        let after = p.snapshot();
                        assert_invariants(after);
                        if r.is_err() {
                            assert_eq!(before, after, "error op {:?} mutated the snapshot", op);
                        }
                    }
                }
            }
        }
    }
}

#[test]
fn deterministic_replay_and_no_starvation() {
    // Compare every operation, not only a final snapshot. Literal selections
    // independently specify FIFO fairness through a sustained legal trace.
    let mut a = fresh();
    let mut b = fresh();
    for id in [1, 2] {
        assert_eq!(a.admit(id, TaskKind::KernelProbe), Ok(()));
        assert_eq!(b.admit(id, TaskKind::KernelProbe), Ok(()));
        assert_eq!(a.snapshot(), b.snapshot());
        assert_invariants(a.snapshot());
    }
    for turn in 0..128 {
        let expected = Context::Worker(if turn % 2 == 0 { 1 } else { 2 });
        assert_eq!(a.request_reschedule(), expected);
        assert_eq!(b.request_reschedule(), expected);
        assert_eq!(a.snapshot(), b.snapshot());
        assert_invariants(a.snapshot());
    }
    // Current is Worker(2); inhibited requests coalesce and final leave
    // performs exactly one ordinary decision, selecting Worker(1).
    for _ in 0..2 {
        assert_eq!(a.enter_inhibit(), Ok(()));
        assert_eq!(b.enter_inhibit(), Ok(()));
        assert_eq!(a.snapshot(), b.snapshot());
        assert_invariants(a.snapshot());
    }
    for _ in 0..32 {
        assert_eq!(a.request_reschedule(), Context::Worker(2));
        assert_eq!(b.request_reschedule(), Context::Worker(2));
        assert_eq!(a.snapshot(), b.snapshot());
        assert_invariants(a.snapshot());
    }
    for expected in [Context::Worker(2), Context::Worker(1)] {
        assert_eq!(a.leave_inhibit(), Ok(expected));
        assert_eq!(b.leave_inhibit(), Ok(expected));
        assert_eq!(a.snapshot(), b.snapshot());
        assert_invariants(a.snapshot());
    }
    for (id, expected) in [(1, Context::Worker(2)), (2, Context::Idle)] {
        assert_eq!(a.complete(id), Ok(expected));
        assert_eq!(b.complete(id), Ok(expected));
        assert_eq!(a.snapshot(), b.snapshot());
        assert_invariants(a.snapshot());
    }
    assert_eq!(a.snapshot().slots, [retired(1), retired(2)]);
    assert!(!a.snapshot().pending);
    assert_eq!(a.snapshot().inhibit_depth, 0);
}
