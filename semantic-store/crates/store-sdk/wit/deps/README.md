# Vendored WASI WIT dependencies

These seven files are byte-for-byte copies of `wit/deps` from
`wasmtime-wasi-http` **46.0.1**. They define the WASI 0.2.12 package graph
required to parse `../semantic-store.wit` independently.

The sources come from the Bytecode Alliance Wasmtime release and retain their
upstream Apache-2.0 WITH LLVM-exception licensing. They are vendored rather
than discovered in Cargo's registry so Store authors and CI receive the exact
WIT contract selected by the pinned host runtime.

When Wasmtime is intentionally upgraded:

1. Replace every `.wit` file in this directory with the new pinned
   `wasmtime-wasi-http` crate's complete `wit/deps` directory.
2. Update the version above; do not mix dependency snapshots.
3. Build the reference core module for `wasm32-unknown-unknown`, componentize it
   against `../semantic-store.wit`, and run the host conformance tests. Do not
   use a Rust WASI sysroot whose imported WIT version differs from this snapshot.

The SHA-256 checksums for the 46.0.1 snapshot are:

```text
cli.wit         fb6ac5d23fcaf3d231142a3c2f9bb1e9bc1fe5af6f1f329f6b1a5555ce0d3873
clocks.wit      6ed8aa65bb8cbe224a0b2cbac9fc1b3bd25bdb17eda5ae0d23c983ed31c447cc
filesystem.wit  e675f261017bf9b4fa7df5b9701023fe0249ede71021ac1bf978748e62edcda8
http.wit        4bbd58f509700a6637385611f183c5bd5984d81feef85e29dfdc05ebd283045a
io.wit          96e206d00076fa0480df32c5bcf255a3fa4862805ac2f6b8537a781cce54f433
random.wit      48578c40213d5cab6650980905fa146a0be8c39c4433ee5e7e00637b87dbe08f
sockets.wit     ad38dbf3b0bbdf34c0f2b608edcbfee04d71b443a63faff1f5e0053c3f84b377
```
