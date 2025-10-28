from flask import Flask, request, send_file, jsonify
import yt_dlp
import os
import tempfile
import shutil
import logging
import re

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Supported video qualities (for YouTube)
SUPPORTED_QUALITIES = ['144', '240', '360', '480', '540', '720', '1080', '1440', '2160', 'best', 'worst']

# Common cookies file names to check
COOKIES_FILES = [
    'cookies.txt',
    'youtube_cookies.txt', 
    'yt_cookies.txt',
    'cookies.json',
    'auth_cookies.txt'
]

def detect_platform(url):
    """Detect if URL is YouTube or Instagram"""
    if 'youtube.com' in url or 'youtu.be' in url:
        return 'youtube'
    elif 'instagram.com' in url:
        return 'instagram'
    else:
        return 'unknown'

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

def download_video_direct(video_url, quality=None, cookies_file=None):
    """
    Download video directly with specified quality and cookies
    """
    platform = detect_platform(video_url)
    
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
    
    # Set format based on platform
    if platform == 'youtube':
        if not quality:
            quality = 'best'
            
        if quality not in SUPPORTED_QUALITIES:
            raise ValueError(f"Unsupported quality. Use: {', '.join(SUPPORTED_QUALITIES)}")
        
        # YouTube format selection
        if quality == 'best':
            ydl_opts['format'] = 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best'
        elif quality == 'worst':
            ydl_opts['format'] = 'worstvideo[ext=mp4]+worstaudio[ext=m4a]/worst[ext=mp4]/worst'
        else:
            # Specific quality (144, 240, 360, 480, 540, 720, 1080, etc.)
            ydl_opts['format'] = f'bestvideo[height<={quality}][ext=mp4]+bestaudio[ext=m4a]/best[height<={quality}][ext=mp4]/best'
    
    elif platform == 'instagram':
        # Instagram - quality parameter is ignored, always get best
        ydl_opts['format'] = 'best'
        quality = 'best'  # For consistent response
    
    else:
        raise ValueError("Unsupported platform. Only YouTube and Instagram URLs are supported.")
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(video_url, download=True)
            downloaded_file = ydl.prepare_filename(info)
            
            logger.info(f"Successfully downloaded from {platform}: {info.get('title', 'Unknown')} in {quality}")
            return downloaded_file, info.get('title', 'video'), platform
            
    except Exception as e:
        # Cleanup on error
        shutil.rmtree(temp_dir, ignore_errors=True)
        logger.error(f"Download error: {str(e)}")
        raise e

@app.route('/api/video/download', methods=['GET'])
def direct_download():
    """
    Direct download endpoint for YouTube and Instagram
    Query parameters:
    - url: YouTube/Instagram video URL (required)
    - quality: For YouTube: 144, 240, 360, 480, 540, 720, 1080, 1440, 2160, best, worst (optional)
    - cookies: Path to cookies file (optional - auto-detects cookies.txt)
    """
    video_url = request.args.get('url')
    quality = request.args.get('quality')
    cookies_file = request.args.get('cookies')
    
    if not video_url:
        return "Error: Video URL parameter is required", 400
    
    platform = detect_platform(video_url)
    
    # Validate quality for YouTube
    if platform == 'youtube' and quality and quality not in SUPPORTED_QUALITIES:
        return f"Error: Unsupported quality for YouTube. Use: {', '.join(SUPPORTED_QUALITIES)}", 400
    
    # Instagram doesn't need quality parameter
    if platform == 'instagram' and quality:
        logger.info("Quality parameter ignored for Instagram")
    
    try:
        downloaded_file, video_title, platform = download_video_direct(video_url, quality, cookies_file)
        
        # Clean filename for download
        clean_title = "".join(c for c in video_title if c.isalnum() or c in (' ', '-', '_')).rstrip()
        
        if platform == 'youtube':
            filename = f"{clean_title}_{quality}p.mp4"
        else:
            filename = f"{clean_title}_instagram.mp4"
        
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
    Get available formats for a video (YouTube only)
    """
    video_url = request.args.get('url')
    cookies_file = request.args.get('cookies')
    
    if not video_url:
        return jsonify({'error': 'Video URL is required'}), 400
    
    platform = detect_platform(video_url)
    
    if platform != 'youtube':
        return jsonify({
            'platform': platform,
            'message': 'Formats endpoint only available for YouTube videos',
            'supported_qualities': ['best']  # Instagram always uses best quality
        })
    
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
                'platform': 'youtube',
                'title': info.get('title'),
                'duration': info.get('duration'),
                'available_qualities': available_qualities,
                'cookies_used': bool(actual_cookies_file),
                'formats_count': len(formats)
            })
            
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/video/info', methods=['GET'])
def video_info():
    """
    Get basic video information for both YouTube and Instagram
    """
    video_url = request.args.get('url')
    cookies_file = request.args.get('cookies')
    
    if not video_url:
        return jsonify({'error': 'Video URL is required'}), 400
    
    platform = detect_platform(video_url)
    
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
            
            response_data = {
                'platform': platform,
                'title': info.get('title'),
                'duration': info.get('duration'),
                'uploader': info.get('uploader'),
                'view_count': info.get('view_count'),
                'thumbnail': info.get('thumbnail'),
                'cookies_used': bool(actual_cookies_file),
                'url': video_url
            }
            
            if platform == 'youtube':
                response_data['supported_qualities'] = SUPPORTED_QUALITIES
            else:
                response_data['message'] = 'Instagram videos download in best available quality'
            
            return jsonify(response_data)
            
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
    <h1>Video Download API</h1>
    <p>Supports YouTube and Instagram videos</p>
    
    <h2>Available endpoints:</h2>
    <ul>
        <li><strong>Direct Download:</strong> GET /api/video/download?url=URL&quality=720</li>
        <li><strong>Video Info:</strong> GET /api/video/info?url=URL</li>
        <li><strong>YouTube Formats:</strong> GET /api/video/formats?url=YOUTUBE_URL</li>
        <li><strong>Check Cookies:</strong> GET /api/check-cookies</li>
    </ul>
    
    <h2>Supported Platforms:</h2>
    <ul>
        <li><strong>YouTube:</strong> Quality options: 144, 240, 360, 480, 540, 720, 1080, 1440, 2160, best, worst</li>
        <li><strong>Instagram:</strong> Always downloads best available quality (quality parameter ignored)</li>
    </ul>
    
    <h2>Example URLs:</h2>
    <p><strong>YouTube:</strong> http://localhost:5000/api/video/download?url=https://youtu.be/BOF2KmrhJfc&quality=720</p>
    <p><strong>Instagram:</strong> http://localhost:5000/api/video/download?url=https://instagram.com/p/ABC123/</p>
    
    <p>Auto-detects cookies.txt file for age-restricted/private videos</p>
    """

if __name__ == '__main__':
    # Check for cookies file on startup
    cookies_file = find_cookies_file()
    if cookies_file:
        print(f"✅ Cookies file found: {cookies_file}")
    else:
        print("⚠️  No cookies file found. Age-restricted videos may not work.")
    
    print("🚀 Video Download API started - Supports YouTube & Instagram")
    app.run(debug=True, host='0.0.0.0', port=8080)
