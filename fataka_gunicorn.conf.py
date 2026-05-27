# ==============================================================================
# Gunicorn Production Configuration File (fataka_gunicorn.conf.py)
# ==============================================================================
# Customized high-performance process manager settings for Vighnaharta Fataka API.
# ==============================================================================
import multiprocessing

# --- Process Name ---
# Name of the Gunicorn process visible in process managers like htop/ps
proc_name = "fataka_api"

# --- Socket Binding ---
# Bind to a high-speed Unix Socket located in /run/ for Nginx to proxy directly.
# This is much faster and more secure than binding to a local port (e.g., 127.0.0.1:8000).
bind = "unix:/run/fataka_api.sock"

# --- CPU Worker Scaling ---
# Dynamic calculation: (2 * Number of CPU Cores) + 1.
# This formula ensures optimal CPU utilization during concurrent connections.
workers = multiprocessing.cpu_count() * 2 + 1

# --- Threading ---
# Number of threads per worker process for handling concurrent keep-alive requests.
threads = 2

# --- Resource Tuning ---
# Max number of requests a worker will process before restarting (prevents memory leaks)
max_requests = 1000
max_requests_jitter = 50

# --- Timeouts ---
# How long a worker can execute a single request before Gunicorn kills and restarts it.
# We set this to 120 seconds to allow heavy PDF Invoice and Report generation (ReportLab/xhtml2pdf).
timeout = 120

# Keep-alive connection persistence time (seconds)
keepalive = 5

# --- Logging Setup ---
# Redirect Gunicorn access and error logs to stdout/stderr.
# This is the modern standard for Systemd/Docker, allowing journald or cloud monitors
# to collect, index, and manage logs centrally without needing files on disk.
accesslog = "-"
errorlog = "-"
loglevel = "info"

# Custom log format to capture execution times and requests
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" %(D)sµs'
