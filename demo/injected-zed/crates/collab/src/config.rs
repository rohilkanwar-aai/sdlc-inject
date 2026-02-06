/// Configuration constants for the collab service

/// Maximum time to wait for buffer lock acquisition
pub const BUFFER_LOCK_TIMEOUT_MS: u64 = 100;

/// Maximum number of concurrent connections per user
pub const MAX_CONNECTIONS_PER_USER: usize = 10;

/// Heartbeat interval for presence updates
pub const PRESENCE_HEARTBEAT_MS: u64 = 30000;

/// Maximum buffer size in bytes
pub const MAX_BUFFER_SIZE: usize = 10 * 1024 * 1024; // 10MB
