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
