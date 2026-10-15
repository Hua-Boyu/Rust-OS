//! Boot-only bounded copy; no references to loader memory escape.
use alloc::vec::Vec;

pub(crate) const MAX_MODULE_BYTES: usize = 256 * 1024;

#[derive(Debug, Copy, Clone, PartialEq, Eq)]
pub(crate) enum CopyError {
    Span,
    Paging,
    Allocation,
    Mapping,
}

/// Kept separate to test rejection ordering without dereferencing physical RAM.
fn copy_checked(
    start: u64,
    end: u64,
    paging: bool,
    check: impl FnOnce(u64, u64) -> bool,
    read: impl FnOnce(u64, &mut [u8]),
) -> Result<Vec<u8>, CopyError> {
    let length = end.checked_sub(start).ok_or(CopyError::Span)?;
    if start < 4096 || length == 0 || length > MAX_MODULE_BYTES as u64 || end > (1u64 << 32) {
        return Err(CopyError::Span);
    }
    if !paging {
        return Err(CopyError::Paging);
    }
    // Check returns a scalar: no PageMap borrow spans allocation/heap growth.
    if !check(start, end) {
        return Err(CopyError::Mapping);
    }
    let mut bytes = Vec::new();
    bytes
        .try_reserve_exact(length as usize)
        .map_err(|_| CopyError::Allocation)?;
    bytes.resize(length as usize, 0);
    read(start, &mut bytes);
    Ok(bytes)
}

/// # Safety
/// Boot entry only, after accepted inventory and paging activation. `start/end`
/// must be the exact selected module span from that inventory, backed by the
/// loader's RAM contract and disjoint from kernel/heap/page structures. This
/// function verifies permanent pins/identity mappings but cannot authenticate
/// provenance of arbitrary numeric addresses. No IRQ or second CPU may mutate
/// mappings or loader bytes during the copy. Heap growth touches only the
/// disjoint growth window, never these boot-pinned pages.
#[cfg(not(test))]
pub(crate) unsafe fn copy_module(start: u64, end: u64) -> Result<Vec<u8>, CopyError> {
    copy_checked(
        start,
        end,
        super::paging_enabled(),
        |a, b| super::page_map_ref().is_some_and(|pm| pm.pinned_identity_span(a, b)),
        |addr, out| unsafe {
            core::ptr::copy_nonoverlapping(addr as *const u8, out.as_mut_ptr(), out.len());
        },
    )
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn copy_checks_before_read_and_owns_bytes() {
        let source = alloc::vec![1, 2, 3];
        let result = copy_checked(
            0x40001,
            0x40004,
            true,
            |a, b| {
                assert_eq!((a, b), (0x40001, 0x40004));
                true
            },
            |a, out| {
                assert_eq!(a, 0x40001);
                out.copy_from_slice(&source);
            },
        )
        .unwrap();
        drop(source);
        assert_eq!(result, [1, 2, 3]);
    }

    #[test]
    fn rejects_span_paging_and_mapping_before_source_access() {
        for (a, b) in [
            (0, 1),
            (4096, 4096),
            (8192, 4096),
            (4096, u64::MAX),
            (4096, 4096 + MAX_MODULE_BYTES as u64 + 1),
            ((1u64 << 32) - 1, (1u64 << 32) + 1),
        ] {
            assert_eq!(
                copy_checked(
                    a,
                    b,
                    true,
                    |_, _| panic!("check on invalid span"),
                    |_, _| panic!("read on invalid span")
                ),
                Err(CopyError::Span)
            );
        }
        assert_eq!(
            copy_checked(
                4096,
                4097,
                false,
                |_, _| panic!("check without paging"),
                |_, _| panic!("read without paging")
            ),
            Err(CopyError::Paging)
        );
        assert_eq!(
            copy_checked(
                4096,
                4097,
                true,
                |_, _| false,
                |_, _| panic!("read without pin")
            ),
            Err(CopyError::Mapping)
        );
    }
}
