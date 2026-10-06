//! crowsetup-core: everything CrowSetup.exe does, without a window (#196 phase 2).
//!
//! Owners (parallel crew): T1 `fetch`, `state`, `verify`; T2 `stack`, `plan`,
//! `preflight`; T3 `layout`, `python`, `convert`, `check`, `finish`; T4 `run`.
//! `api` is the shared contract and changes only through the lead.

pub mod api;

pub mod fetch;
pub mod state;
pub mod verify;

pub mod plan;
pub mod preflight;
pub mod stack;

pub mod check;
pub mod convert;
pub mod finish;
pub mod layout;
pub mod python;
/// NVIDIA's CUDA libraries, from NVIDIA's own wheels.
pub mod nvidia;
/// #340: the video server's runtime (ComfyUI's portable 7z).
pub mod runtime;

pub mod run;

/// The stack manifest this installer version ships (`manifests/stack.json`).
pub const STACK_JSON: &str = include_str!("../../../manifests/stack.json");
