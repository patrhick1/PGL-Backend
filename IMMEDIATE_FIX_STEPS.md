# Immediate Fix Without Environment Variable Changes

## The Problem
- Changing environment variables causes redeployment
- Redeployment triggers the memory spike issue again
- Creates an endless loop

## Solution: Deploy Code Changes Only

I've made these changes to your code:

### 1. Automatic Startup Delay (main.py)
- Added 60-second delay before scheduler starts in production
- No environment variable needed - it's hardcoded

### 2. Reduced Batch Size (transcribe_episodes.py)
- Changed default batch size from 20 to 1
- Will only process 1 episode at a time

### 3. Memory Cleanup After Each Episode
- Added garbage collection and memory cleanup
- Added memory checks before processing

### 4. Limited Downloads
- Added download semaphore to allow only 1 download at a time
- Added file size checks before downloading

## Deploy Instructions

1. **Commit and push these changes**:
   ```bash
   git add .
   git commit -m "fix: Implement memory optimizations to prevent OOM errors"
   git push
   ```

2. **Let Render auto-deploy** these code changes

3. **Monitor the logs** - You should see:
   - "Production mode: Implementing 60-second startup delay..."
   - Only 1 episode being processed at a time
   - Memory cleanup messages

## What Will Happen

1. Service starts
2. Waits 60 seconds before any tasks run
3. Tasks start one at a time with delays
4. Each episode is processed individually with memory cleanup
5. Memory usage should stay well under 1GB

## If Still Having Issues

The memory graph showing ~1GB usage but Render reporting 2GB+ suggests:

1. **Memory measurement difference** - Add this to see actual usage:
   ```python
   import resource
   # Log this periodically:
   usage = resource.getrusage(resource.RUSAGE_SELF)
   logger.info(f"Max RSS: {usage.ru_maxrss / 1024}MB")
   ```

2. **Consider upgrading temporarily** to 4GB instance to diagnose

3. **Check for zombie processes**:
   - The service might be leaving child processes
   - These count toward memory but don't show in main process metrics

## No Environment Variables Needed!

All fixes are in the code. Just deploy and the service will:
- Start slowly
- Process one thing at a time
- Clean up memory aggressively
- Stay within limits