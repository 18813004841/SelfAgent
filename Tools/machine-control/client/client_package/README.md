# Central server client package

This package is the runtime payload for a user's local machine. Install or
download it as one `central-client` directory. It contains only the worker
client, shared protocol models, and the local process manager. The central
server implementation is intentionally excluded.

The package version is stored in `VERSION` at the package root. Update that
file before building a new archive on the server.
