//! RostiFS v0.1 — portable `no_std` storage engine shared by the kernel and
//! host tools. Modules: format (on-disk wire format), block (device trait),
//! checksum (CRC32C), vfs (contract), engine (transactional filesystem).

#![no_std]

pub mod block;
pub mod checksum;
pub mod engine;
pub mod format;
pub mod vfs;

#[cfg(test)]
mod crash_tests;
