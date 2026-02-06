use sqlx::PgPool;
use crate::{BufferId, UserId, Error, Result};

pub struct BufferManager {
    pool: PgPool,
}

impl BufferManager {
    pub fn new(pool: PgPool) -> Self {
        Self { pool }
    }

    /// Acquires a lock on a buffer for editing
    pub async fn acquire_buffer_lock(
        &self,
        buffer_id: BufferId,
        user_id: UserId,
    ) -> Result<bool> {
        // Attempt to acquire the lock atomically
        let lock_acquired = self.try_acquire_lock(buffer_id).await?;

        if !lock_acquired {
            return Err(Error::BufferLocked);
        }

        // Record the lock holder
        sqlx::query!(
            "UPDATE buffers SET locked_by = $1, locked_at = NOW() WHERE id = $2",
            user_id.0,
            buffer_id.0
        )
        .execute(&self.pool)
        .await?;

        Ok(true)
    }

    async fn try_acquire_lock(&self, buffer_id: BufferId) -> Result<bool> {
        let result = sqlx::query!(
            "UPDATE buffers SET locked_by = NULL
             WHERE id = $1 AND locked_by IS NULL
             RETURNING id",
            buffer_id.0
        )
        .fetch_optional(&self.pool)
        .await?;

        Ok(result.is_some())
    }

    pub async fn release_buffer_lock(
        &self,
        buffer_id: BufferId,
        user_id: UserId,
    ) -> Result<()> {
        sqlx::query!(
            "UPDATE buffers SET locked_by = NULL, locked_at = NULL
             WHERE id = $1 AND locked_by = $2",
            buffer_id.0,
            user_id.0
        )
        .execute(&self.pool)
        .await?;

        Ok(())
    }
}
