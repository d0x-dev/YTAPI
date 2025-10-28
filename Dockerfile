# Use official Python image
FROM python:3.10-slim

# Set working directory
WORKDIR /app

# Copy all project files (including apis1.py ... apis10.py)
COPY . .

# Install dependencies
RUN pip install --no-cache-dir flask requests yt-dlp

# Expose port
EXPOSE 8080

# Set environment variables
ENV PORT=8080

# Start Flask app
CMD ["python", "app.py"]
