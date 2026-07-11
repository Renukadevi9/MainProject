import os

# Port binding
bind = f"0.0.0.0:{os.environ.get('PORT', '8000')}"

# Crucial memory optimizations for 512MB RAM constraints on Render Free Tier
# We run 1 worker with 2 threads to conserve memory while allowing concurrency
workers = int(os.environ.get('WEB_CONCURRENCY', 1))
threads = 2
timeout = 30
keepalive = 2

# Recycle workers periodically to combat any memory leaks in dependencies
max_requests = 500
max_requests_jitter = 50
