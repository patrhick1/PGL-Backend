# Audio Compression Configuration

## Overview
The system now supports automatic audio compression for large podcast episodes that exceed size thresholds. This allows processing of episodes that would otherwise be rejected due to file size limits.

## Environment Variables

### File Size Limits

```bash
# Maximum file size for processing without compression (default: 500MB)
MAX_FILE_SIZE_MB=500

# Threshold for triggering compression (default: 500MB)
# Files larger than this will be compressed before processing
COMPRESS_THRESHOLD_MB=500

# Absolute maximum file size that can be downloaded (default: 2000MB / 2GB)
# Files larger than this are rejected even with compression
MAX_DOWNLOAD_SIZE_MB=2000
```

## How It Works

1. **Size Check**: Before downloading, the system checks the file size via HTTP headers
2. **Decision Logic**:
   - File < 500MB: Download and process normally
   - 500MB < File < 2GB: Download and compress before processing
   - File > 2GB: Reject with permanent failure (too large even for compression)

3. **Compression Process**:
   - Converts stereo to mono (50% size reduction)
   - Reduces sample rate to 16kHz (suitable for speech)
   - Applies 64kbps bitrate compression
   - Typically achieves 70-90% size reduction

## Example Compression Results

| Original File | Compressed File | Reduction |
|--------------|-----------------|-----------|
| 1159 MB stereo 44.1kHz | ~115 MB mono 16kHz | 90% |
| 600 MB stereo 48kHz | ~60 MB mono 16kHz | 90% |
| 300 MB stereo 44.1kHz | ~30 MB mono 16kHz | 90% |

## Benefits

1. **Process Large Episodes**: Can now handle episodes up to 2GB (previously limited to 500MB)
2. **Reduced API Costs**: Smaller files mean lower transcription costs
3. **Faster Processing**: Compressed files upload and process faster
4. **Automatic Cleanup**: Original large files are deleted after compression

## Configuration Examples

### Conservative (Default)
```bash
MAX_FILE_SIZE_MB=500
COMPRESS_THRESHOLD_MB=500
MAX_DOWNLOAD_SIZE_MB=2000
```

### Aggressive Compression (Compress everything over 200MB)
```bash
MAX_FILE_SIZE_MB=200
COMPRESS_THRESHOLD_MB=200
MAX_DOWNLOAD_SIZE_MB=3000
```

### No Compression (Original behavior)
```bash
MAX_FILE_SIZE_MB=500
COMPRESS_THRESHOLD_MB=10000  # Very high threshold
MAX_DOWNLOAD_SIZE_MB=500
```

## Monitoring

Look for these log messages:
- `"File size X MB exceeds threshold Y MB - will compress after download"`
- `"Starting audio compression for /path/to/file"`
- `"Compression complete: X MB (Y% reduction)"`
- `"File too large even for compression: X MB (max: Y MB)"`

## Troubleshooting

### FFmpeg Not Found
If compression fails with "ffmpeg not found", ensure FFmpeg is installed:
```bash
# Ubuntu/Debian
sudo apt-get install ffmpeg

# Windows (using chocolatey)
choco install ffmpeg

# MacOS
brew install ffmpeg
```

### Memory Issues
Large files may cause memory issues during compression. Monitor with:
- `"High memory usage (X%), cleaning up before processing episode"`

### Compression Failures
If compression fails, the system will attempt to use the original file. Check logs for:
- `"Error compressing audio: [error details]"`