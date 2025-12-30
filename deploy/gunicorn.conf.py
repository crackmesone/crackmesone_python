# Gunicorn configuration for crackmes.one
# For a 2-core VPS: 2 * cores + 1 = 5 workers

workers = 5
worker_class = 'sync'
bind = '127.0.0.1:8081'
timeout = 30
keepalive = 2

# Logging
accesslog = '/var/log/gunicorn/access.log'
errorlog = '/var/log/gunicorn/error.log'
loglevel = 'info'

# Process naming
proc_name = 'crackmesone'

# Graceful restart timeout
graceful_timeout = 30
