mod buffers;

use sqlx::PgPool;
use crate::{BufferId, Result};

pub use buffers::BufferManager;

pub struct Database {
    pool: PgPool,
    pub buffers: BufferManager,
}

impl Database {
    pub fn new(pool: PgPool) -> Self {
        Self {
            buffers: BufferManager::new(pool.clone()),
            pool,
        }
    }

    pub fn pool(&self) -> &PgPool {
        &self.pool
    }
}
// Helper for buffer availability check (introduces race window)
impl Database {
    pub async fn check_buffer_available(&self, buffer_id: BufferId) -> Result<bool> {
        let row = sqlx::query_scalar!(
            "SELECT locked_by IS NULL as available FROM buffers WHERE id = $1",
            buffer_id.0
        )
        .fetch_optional(&self.pool)
        .await?;
        Ok(row.unwrap_or(true))
    }
}
