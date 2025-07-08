# Additional Memory Fixes Required

## Current Situation
The initial memory fixes have been implemented but the service is still exceeding 2GB memory limit on Render. The logs show multiple 80+ MB files being downloaded and processed concurrently.

## Immediate Actions Required

### 1. Update Environment Variables (CRITICAL)
Based on the logs, multiple large files are being processed. Update these values in your Render environment:

```env
# Reduce all concurrency limits
CHUNK_CONCURRENCY=1              # Was 2
GEMINI_API_CONCURRENCY=1          # Was 2  
MAX_BATCH_SIZE=1                  # Was 3-5
GLOBAL_TRANSCRIPTION_LIMIT=1      # Was 3
MAX_FILE_SIZE_MB=200              # Was 300-500

# Add new memory-specific limits
MAX_CONCURRENT_DOWNLOADS=1        # New - limit downloads
MEMORY_CHECK_INTERVAL_MB=50       # New - check memory every 50MB
```

### 2. Add Download Queue Management
The logs show multiple downloads happening simultaneously. We need to queue them:

```python
# In transcriber.py, add at module level:
DOWNLOAD_SEMAPHORE = asyncio.Semaphore(int(os.getenv("MAX_CONCURRENT_DOWNLOADS", "1")))

# Wrap download_audio method:
async def download_audio(self, url: str, episode_id: Optional[int] = None) -> Optional[str]:
    async with DOWNLOAD_SEMAPHORE:
        return await asyncio.to_thread(self._download_audio_sync, url)
```

### 3. Force Garbage Collection After Each Episode
Add aggressive memory cleanup in `transcribe_episodes.py`:

```python
# After each episode processing:
import gc
gc.collect()
cleanup_memory()
await asyncio.sleep(1)  # Give OS time to reclaim memory
```

### 4. Add Memory Monitoring to Batch Processing
In `batch_transcriber.py`, check memory before each episode:

```python
# In _process_sub_batch, before processing each episode:
memory_info = get_memory_info()
if memory_info["process_percent"] > 40:
    logger.warning(f"Memory usage high ({memory_info['process_percent']:.1f}%), waiting...")
    await asyncio.sleep(5)
    gc.collect()
    cleanup_memory()
```

### 5. Implement File Streaming for Large Files
For files over 50MB, stream directly to Gemini without loading into memory:

```python
# In transcriber.py _process_long_audio:
@memory_guard(threshold_percent=40.0)  # Lower from 60%
async def _process_long_audio(self, file_path: str, episode_name: Optional[str] = None) -> str:
    # Add file size check
    file_size_mb = os.path.getsize(file_path) / (1024 * 1024)
    if file_size_mb > 100:
        logger.warning(f"Very large file ({file_size_mb:.1f} MB), using minimal memory mode")
        # Process in smaller chunks or skip
```

### 6. Add Emergency Memory Release
Create a memory pressure handler:

```python
# In memory_monitor.py:
async def emergency_memory_release():
    """Emergency memory release when approaching limits."""
    import gc
    import tracemalloc
    
    # Force multiple GC passes
    for _ in range(3):
        gc.collect()
    
    # Clear any caches
    if hasattr(asyncio, '_get_running_loop'):
        loop = asyncio._get_running_loop()
        if loop and hasattr(loop, '_ready'):
            loop._ready.clear()
    
    logger.warning("Emergency memory release completed")
```

## Root Cause Analysis

The logs reveal the actual problem:
1. **Episode 8670** is being processed multiple times (appears in multiple restart logs)
2. Each restart tries to process the same 20 episodes
3. Multiple 80+ MB files are being downloaded and held in memory
4. The scheduler is triggering multiple pipelines simultaneously on startup

## Recommended Architecture Changes

1. **Single Task Processing**: Only process ONE episode at a time
2. **Checkpoint System**: Track which episodes have been processed to avoid reprocessing
3. **Memory Budget**: Allocate specific memory budgets per operation
4. **Streaming Processing**: Never load entire audio files into memory

## Quick Fix for Immediate Relief

Add this to your `main.py` startup to delay task scheduling:

```python
# In main.py after scheduler initialization:
if IS_PRODUCTION:
    logger.info("Production mode: Delaying task scheduler start by 30 seconds")
    await asyncio.sleep(30)  # Give the service time to stabilize
```

## Monitoring Commands

Run these on your Render instance:
```bash
# Check memory usage
ps aux | grep python
free -m

# Check temp files
ls -la /tmp | grep -E "(mp3|wav|m4a)" | wc -l

# Check open file descriptors
lsof | grep python | wc -l
```

## Expected Outcome

With these changes:
- Only 1 file processed at a time
- Maximum 200MB file size
- Memory usage should stay under 1GB
- No concurrent operations competing for memory