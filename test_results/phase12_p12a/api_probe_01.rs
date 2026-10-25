#![no_std]
#[path = "../../src/p12a_policy.rs"]
mod policy;
use policy::{Context, Error, Policy, Slot, Snapshot, State, TaskKind};
const INITIAL: Policy = Policy::new();
fn eq_bound<T: Eq>() {}
pub fn verify() {
    eq_bound::<State>();
    eq_bound::<Context>();
    eq_bound::<TaskKind>();
    eq_bound::<Error>();
    eq_bound::<Slot>();
    eq_bound::<Snapshot>();
    let s = INITIAL.snapshot();
    assert!(
        s.slots
            == [Slot {
                id: 0,
                state: State::Unused
            }; 2]
    );
    assert!(s.queue == [0, 0]);
    assert!(s.queue_len == 0);
    assert!(s.current == Context::Idle);
    assert!(s.inhibit_depth == 0);
    assert!(!s.pending);
}
