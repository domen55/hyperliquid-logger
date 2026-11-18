## Context

`make_handler` calls `load_config` at the top of `do_GET`, before the `try` that turns failures into HTTP 500
and events. A parse error therefore raises inside the handler thread and the connection is dropped.

## Decisions

- A small `ConfigHolder(path)` with `get()`: tries `load_config`, remembers the last good result and returns
  it when loading fails. It remembers the file's mtime of the last reported failure so the ERROR event is
  emitted once per file change, not once per request. It is thread-safe (lock), because the server is threaded.
- The first `get()` happens in `main()`, so an invalid file at startup fails fast with the original exception.
- The handler gets the holder instead of the path. The collector keeps its own per-round loading (it already
  keeps the previous config and reports the error) so its behaviour does not change.
- Alternative considered: wrapping `load_config` in the existing `try` and answering 500. Rejected: the page
  would still show nothing while data is being collected.
