# Connection Pool Behavior Documentation

## Overview

The application uses asyncpg connection pooling to efficiently manage database connections. Understanding the normal behavior of connection pools is important to avoid false alarms about "connection leaks".

## Connection Pool Configuration

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

## Normal Pool Behavior

1. **Initial State**: Pool starts with `min_size=3` connections
2. **Growth**: Pool grows as needed up to `max_size=10` connections
3. **Reuse**: Connections are reused for multiple queries
4. **Idle Cleanup**: Unused connections are closed after 5 minutes

## What's NOT a Connection Leak

The following scenarios are NORMAL and not connection leaks:

1. **Pool Size Growth**: Going from 1 → 2 → 3 connections is normal startup behavior
2. **Concurrent Requests**: Multiple simultaneous requests may temporarily increase pool size
3. **Size Fluctuation**: Pool size varying between 3-10 is expected

## What IS a Connection Leak

Real connection leaks would show:

1. Pool size exceeding `max_size` (>10)
2. Connections not being returned after queries complete
3. Gradual increase over time without decrease
4. Application hanging when trying to acquire connections

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