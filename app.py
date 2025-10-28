from flask import Flask, request, send_file, jsonify
import yt_dlp
import os
import tempfile
import shutil
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Supported video qualities
SUPPORTED_QUALITIES = ['144', '240', '360', '480', '540', '720', '1080', '1440', '2160', 'best', 'worst']

# Common cookies file names to check
COOKIES_FILES = [
    'cookies.txt',
    'youtube_cookies.txt', 
    'yt_cookies.txt',
    'cookies.json',
    'auth_cookies.txt'
]

def find_cookies_file(cookies_file=None):
    """
    Find cookies file automatically if not specified
    """
    # If specific file provided, use it
    if cookies_file and os.path.exists(cookies_file):
        return cookies_file
    
    # Check for common cookies file names
    for cookie_file in COOKIES_FILES:
        if os.path.exists(cookie_file):
            logger.info(f"Using cookies file: {cookie_file}")
            return cookie_file
    
    return None

def download_video_direct(video_url, quality, cookies_file=None):
    """
    Download video directly with specified quality and cookies
    """
    # Validate quality
    if quality not in SUPPORTED_QUALITIES:
        raise ValueError(f"Unsupported quality. Use: {', '.join(SUPPORTED_QUALITIES)}")
    
    # Auto-find cookies file
    actual_cookies_file = find_cookies_file(cookies_file)
    
    # Create temp directory for download
    temp_dir = tempfile.mkdtemp()
    
    ydl_opts = {
        'outtmpl': os.path.join(temp_dir, '%(title)s.%(ext)s'),
        'quiet': True,
        'no_warnings': False,
    }
    
    # Add cookies if available
    if actual_cookies_file:
        ydl_opts['cookiefile'] = actual_cookies_file
        logger.info(f"Using cookies from: {actual_cookies_file}")
    else:
        logger.info("No cookies file found, proceeding without cookies")
    
    # Set format based on quality (video only, no MP3)
    if quality == 'best':
        ydl_opts['format'] = 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best'
    elif quality == 'worst':
        ydl_opts['format'] = 'worstvideo[ext=mp4]+worstaudio[ext=m4a]/worst[ext=mp4]/worst'
    else:
        # Specific quality (144, 240, 360, 480, 540, 720, 1080, etc.)
        ydl_opts['format'] = f'bestvideo[height<={quality}][ext=mp4]+bestaudio[ext=m4a]/best[height<={quality}][ext=mp4]/best'
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(video_url, download=True)
            downloaded_file = ydl.prepare_filename(info)
            
            logger.info(f"Successfully downloaded: {info.get('title', 'Unknown')} in {quality}p")
            return downloaded_file, info.get('title', 'video')
            
    except Exception as e:
        # Cleanup on error
        shutil.rmtree(temp_dir, ignore_errors=True)
        logger.error(f"Download error: {str(e)}")
        raise e

@app.route('/api/video/download', methods=['GET'])
def direct_download():
    """
    Direct download endpoint
    Query parameters:
    - url: YouTube video URL (required)
    - quality: 144, 240, 360, 480, 540, 720, 1080, 1440, 2160, best, worst (required)
    - cookies: Path to cookies file (optional - auto-detects cookies.txt)
    """
    video_url = request.args.get('url')
    quality = request.args.get('quality')
    cookies_file = request.args.get('cookies')
    
    if not video_url:
        return "Error: Video URL parameter is required", 400
    
    if not quality:
        return "Error: Quality parameter is required. Use: 144, 240, 360, 480, 540, 720, 1080, 1440, 2160, best, worst", 400
    
    if quality not in SUPPORTED_QUALITIES:
        return f"Error: Unsupported quality. Use: {', '.join(SUPPORTED_QUALITIES)}", 400
    
    try:
        downloaded_file, video_title = download_video_direct(video_url, quality, cookies_file)
        
        # Clean filename for download
        clean_title = "".join(c for c in video_title if c.isalnum() or c in (' ', '-', '_')).rstrip()
        filename = f"{clean_title}_{quality}p.mp4"
        
        # Send file for download
        response = send_file(
            downloaded_file,
            as_attachment=True,
            download_name=filename,
            mimetype='video/mp4'
        )
        
        # Cleanup temp directory after response
        @response.call_on_close
        def cleanup():
            try:
                dir_path = os.path.dirname(downloaded_file)
                shutil.rmtree(dir_path, ignore_errors=True)
                logger.info("Cleaned up temporary files")
            except Exception as e:
                logger.error(f"Cleanup error: {str(e)}")
        
        return response
        
    except Exception as e:
        return f"Error downloading video: {str(e)}", 500

@app.route('/api/video/formats', methods=['GET'])
def available_formats():
    """
    Get available formats for a video
    """
    video_url = request.args.get('url')
    cookies_file = request.args.get('cookies')
    
    if not video_url:
        return jsonify({'error': 'Video URL is required'}), 400
    
    # Auto-find cookies file
    actual_cookies_file = find_cookies_file(cookies_file)
    
    ydl_opts = {
        'quiet': True,
        'no_warnings': False,
    }
    
    if actual_cookies_file:
        ydl_opts['cookiefile'] = actual_cookies_file
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(video_url, download=False)
            
            formats = []
            for fmt in info.get('formats', []):
                if fmt.get('vcodec') != 'none':  # Video formats only (no audio-only)
                    formats.append({
                        'format_id': fmt.get('format_id'),
                        'resolution': f"{fmt.get('height', 'N/A')}p",
                        'ext': fmt.get('ext'),
                        'filesize': fmt.get('filesize'),
                        'format_note': fmt.get('format_note', 'N/A'),
                        'quality_label': f"{fmt.get('height', 'N/A')}p"
                    })
            
            # Get unique available qualities
            available_qualities = list(set([
                f['quality_label'] for f in formats 
                if f['quality_label'] != 'N/Ap' and f['quality_label'].replace('p', '').isdigit()
            ]))
            available_qualities.sort(key=lambda x: int(x.replace('p', '')))
            
            return jsonify({
                'title': info.get('title'),
                'duration': info.get('duration'),
                'available_qualities': available_qualities,
                'cookies_used': bool(actual_cookies_file),
                'formats_count': len(formats)
            })
            
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/check-cookies', methods=['GET'])
def check_cookies():
    """
    Check if cookies file is available
    """
    cookies_file = find_cookies_file()
    return jsonify({
        'cookies_available': bool(cookies_file),
        'cookies_file': cookies_file,
        'supported_cookies_files': COOKIES_FILES
    })

@app.route('/')
def home():
    return """
    <h1>YouTube Video Download API</h1>
    <p>Available endpoints:</p>
    <ul>
        <li><strong>Direct Download:</strong> GET /api/video/download?url=YOUTUBE_URL&quality=720</li>
        <li><strong>Available Formats:</strong> GET /api/video/formats?url=YOUTUBE_URL</li>
        <li><strong>Check Cookies:</strong> GET /api/check-cookies</li>
    </ul>
    <p>Supported qualities: 144, 240, 360, 480, 540, 720, 1080, 1440, 2160, best, worst</p>
    <p>Auto-detects cookies.txt file for age-restricted videos</p>
    """

if __name__ == '__main__':
    # Check for cookies file on startup
    cookies_file = find_cookies_file()
    if cookies_file:
        print(f"✅ Cookies file found: {cookies_file}")
    else:
        print("⚠️  No cookies file found. Age-restricted videos may not work.")
    
    app.run(debug=True, host='0.0.0.0', port=5000)
