# Connection Pool Behavior Documentation

## Overview

The application uses asyncpg connection pooling to efficiently manage database connections. Understanding the normal behavior of connection pools is important to avoid false alarms about "connection leaks".

## Connection Pool Configuration

The application uses a **dual-pool architecture** for better resource management:

### Frontend Pool (API requests)
From `podcast_outreach/database/connection.py`:

```python
DB_POOL = await asyncpg.create_pool(
    dsn=dsn,
    min_size=3,         # Minimum connections to maintain
    max_size=10,        # Maximum connections allowed
    command_timeout=60,
    timeout=10,         # Connection acquire timeout
    max_queries=10000,
    max_inactive_connection_lifetime=300  # 5 minutes
)
```

### Background Task Pool (Long-running operations)
```python
BACKGROUND_TASK_POOL = await asyncpg.create_pool(
    dsn=dsn,
    min_size=2,         # Lower minimum for background tasks
    max_size=8,         # Separate limit from frontend
    command_timeout=1800,  # 30 minutes for long operations
    timeout=60,         # Longer acquire timeout
    max_queries=10000,
    max_inactive_connection_lifetime=300
)
```

## Normal Pool Behavior

1. **Initial State**: Frontend pool starts with `min_size=3` connections, background pool with 2
2. **Growth**: Pools grow as needed up to their respective `max_size` limits
3. **Reuse**: Connections are reused for multiple queries
4. **Idle Cleanup**: Unused connections are closed after 5 minutes
5. **Separation**: Frontend and background tasks use separate pools to prevent interference

## What's NOT a Connection Leak

The following scenarios are NORMAL and not connection leaks:

1. **Pool Size Growth**: Going from 1 → 2 → 3 connections is normal startup behavior
2. **Concurrent Requests**: Multiple simultaneous requests may temporarily increase pool size
3. **Size Fluctuation**: Frontend pool varying between 3-10 and background pool between 2-8 is expected
4. **Dual Pool Usage**: Seeing connections from both pools active simultaneously is normal

## What IS a Connection Leak

Real connection leaks would show:

1. Frontend pool size exceeding `max_size` (>10) or background pool (>8)
2. Connections not being returned after queries complete
3. Gradual increase over time without decrease
4. Application hanging when trying to acquire connections
5. Total connections across both pools exceeding 18 (10+8)

## Monitoring Connection Pool

The middleware now only warns when:
- Pool size exceeds max_size (>10)
- Sudden increase of >3 connections in one request

To enable detailed debugging:
```python
# Set log level to DEBUG to see pool statistics
logger.setLevel(logging.DEBUG)
```

## Best Practices

1. **Always use context managers**:
   ```python
   async with pool.acquire() as conn:
       # Your queries here
   ```

2. **Avoid manual connection management**:
   ```python
   # Bad
   conn = await pool.acquire()
   # ... forgot to release
   
   # Good
   async with pool.acquire() as conn:
       # Automatically released
   ```

3. **Use transactions properly**:
   ```python
   async with pool.acquire() as conn:
       async with conn.transaction():
           # All queries in transaction
   ```

## Dashboard Endpoints

The dashboard endpoints make multiple queries but properly release connections:
- `/dashboard/stats` - Multiple COUNT queries
- `/dashboard/recent-placements` - JOIN queries
- `/dashboard/recommended-podcasts` - Media queries

These are all using proper connection management with context managers.