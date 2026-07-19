use wasmtime::component::ResourceTable;
use wasmtime_wasi::{WasiCtx, WasiCtxView, WasiView};
use wasmtime_wasi_http::{
    WasiHttpCtx,
    p2::{WasiHttpCtxView, WasiHttpView},
};

pub(super) struct HostState {
    http: WasiHttpCtx,
    table: ResourceTable,
    wasi: WasiCtx,
}

impl HostState {
    pub(super) fn new() -> Self {
        Self {
            http: WasiHttpCtx::new(),
            table: ResourceTable::new(),
            wasi: WasiCtx::builder().build(),
        }
    }
}

impl WasiView for HostState {
    fn ctx(&mut self) -> WasiCtxView<'_> {
        WasiCtxView {
            ctx: &mut self.wasi,
            table: &mut self.table,
        }
    }
}

impl WasiHttpView for HostState {
    fn http(&mut self) -> WasiHttpCtxView<'_> {
        WasiHttpCtxView {
            ctx: &mut self.http,
            table: &mut self.table,
            hooks: Default::default(),
        }
    }
}
