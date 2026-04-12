"""
Monitoring and Observability

Prometheus metrics, health checks, and alerting.
"""
import logging
import time
from datetime import datetime, timezone
from typing import Optional

from prometheus_client import Counter, Gauge, Histogram, generate_latest

logger = logging.getLogger(__name__)

# Metrics
http_requests_total = Counter(
    'http_requests_total',
    'Total HTTP requests',
    ['method', 'endpoint', 'status']
)

http_request_duration_seconds = Histogram(
    'http_request_duration_seconds',
    'HTTP request duration in seconds',
    ['method', 'endpoint']
)

agent_executions_total = Counter(
    'agent_executions_total',
    'Total agent executions',
    ['agent_name', 'status']
)

agent_execution_duration_seconds = Histogram(
    'agent_execution_duration_seconds',
    'Agent execution duration in seconds',
    ['agent_name']
)

llm_calls_total = Counter(
    'llm_calls_total',
    'Total LLM API calls',
    ['model', 'status']
)

llm_cost_usd = Counter(
    'llm_cost_usd',
    'Total LLM cost in USD',
    ['model']
)

scraper_runs_total = Counter(
    'scraper_runs_total',
    'Total scraper runs',
    ['scraper_name', 'status']
)

scraper_items_found = Counter(
    'scraper_items_found',
    'Total items found by scrapers',
    ['scraper_name']
)

database_query_duration_seconds = Histogram(
    'database_query_duration_seconds',
    'Database query duration in seconds',
    ['operation']
)

cache_hits_total = Counter(
    'cache_hits_total',
    'Total cache hits',
    ['cache_type']
)

cache_misses_total = Counter(
    'cache_misses_total',
    'Total cache misses',
    ['cache_type']
)

auth_failed_login_total = Counter(
    'auth_failed_login_total',
    'Failed login attempts',
    ['reason']
)

auth_account_locked_total = Counter(
    'auth_account_locked_total',
    'Account lockout events'
)

security_csrf_violation_total = Counter(
    'security_csrf_violation_total',
    'CSRF validation failures',
    ['path']
)

auth_refresh_token_reuse_total = Counter(
    'auth_refresh_token_reuse_total',
    'Refresh token replay detections'
)

security_rate_limit_triggered_total = Counter(
    'security_rate_limit_triggered_total',
    'Rate limit triggers',
    ['rule']
)

# Gauges (current state)
active_jobs = Gauge('active_jobs', 'Number of active jobs')
active_contacts = Gauge('active_contacts', 'Number of active contacts')
pending_tasks = Gauge('pending_tasks', 'Number of pending tasks')
unread_emails = Gauge('unread_emails', 'Number of unread emails')
daily_cost_usd = Gauge('daily_cost_usd', 'Daily cost in USD')
monthly_cost_usd = Gauge('monthly_cost_usd', 'Monthly cost in USD')
celery_dlq_depth = Gauge('celery_dlq_depth', 'Dead-letter queue depth')
celery_queue_depth = Gauge('celery_queue_depth', 'Queue depth by queue', ['queue'])
circuit_breaker_state = Gauge('circuit_breaker_state', 'Circuit breaker state', ['circuit_name'])
backup_last_success_timestamp_seconds = Gauge(
    'backup_last_success_timestamp_seconds',
    'Last successful backup timestamp',
)
restore_drill_last_success_timestamp_seconds = Gauge(
    'restore_drill_last_success_timestamp_seconds',
    'Last successful restore drill timestamp',
)
celery_workers_online = Gauge('celery_workers_online', 'Number of reachable Celery workers')


class MetricsCollector:
    """Collect and export Prometheus metrics."""
    
    @staticmethod
    def record_http_request(method: str, endpoint: str, status: int, duration: float):
        """Record HTTP request metrics."""
        http_requests_total.labels(method=method, endpoint=endpoint, status=status).inc()
        http_request_duration_seconds.labels(method=method, endpoint=endpoint).observe(duration)
    
    @staticmethod
    def record_agent_execution(agent_name: str, status: str, duration: float):
        """Record agent execution metrics."""
        agent_executions_total.labels(agent_name=agent_name, status=status).inc()
        agent_execution_duration_seconds.labels(agent_name=agent_name).observe(duration)
    
    @staticmethod
    def record_llm_call(model: str, status: str, cost: float):
        """Record LLM call metrics."""
        llm_calls_total.labels(model=model, status=status).inc()
        if cost > 0:
            llm_cost_usd.labels(model=model).inc(cost)
    
    @staticmethod
    def record_scraper_run(scraper_name: str, status: str, items_found: int):
        """Record scraper run metrics."""
        scraper_runs_total.labels(scraper_name=scraper_name, status=status).inc()
        if items_found > 0:
            scraper_items_found.labels(scraper_name=scraper_name).inc(items_found)
    
    @staticmethod
    def record_database_query(operation: str, duration: float):
        """Record database query metrics."""
        database_query_duration_seconds.labels(operation=operation).observe(duration)
    
    @staticmethod
    def record_cache_hit(cache_type: str):
        """Record cache hit."""
        cache_hits_total.labels(cache_type=cache_type).inc()
    
    @staticmethod
    def record_cache_miss(cache_type: str):
        """Record cache miss."""
        cache_misses_total.labels(cache_type=cache_type).inc()

    @staticmethod
    def record_failed_login(reason: str):
        auth_failed_login_total.labels(reason=reason).inc()

    @staticmethod
    def record_account_lock():
        auth_account_locked_total.inc()

    @staticmethod
    def record_csrf_violation(path: str):
        security_csrf_violation_total.labels(path=path).inc()

    @staticmethod
    def record_refresh_token_reuse():
        auth_refresh_token_reuse_total.inc()

    @staticmethod
    def record_rate_limit(rule: str):
        security_rate_limit_triggered_total.labels(rule=rule).inc()

    @staticmethod
    def set_dlq_depth(depth: int):
        celery_dlq_depth.set(depth)

    @staticmethod
    def set_queue_depth(queue_name: str, depth: int):
        celery_queue_depth.labels(queue=queue_name).set(depth)

    @staticmethod
    def set_circuit_breaker_state(circuit_name: str, state: int):
        circuit_breaker_state.labels(circuit_name=circuit_name).set(state)

    @staticmethod
    def set_backup_last_success(timestamp_seconds: float):
        backup_last_success_timestamp_seconds.set(timestamp_seconds)

    @staticmethod
    def set_restore_drill_last_success(timestamp_seconds: float):
        restore_drill_last_success_timestamp_seconds.set(timestamp_seconds)

    @staticmethod
    def set_workers_online(count: int):
        celery_workers_online.set(count)
    
    @staticmethod
    async def update_gauges():
        """Update gauge metrics with current state."""
        try:
            from app.database import AsyncSessionLocal
            from app.models.job_posting import JobPosting
            from app.models.contact import Contact
            from app.models.assistant_task import AssistantTask
            from app.models.email_thread import EmailThread
            from app.models.openclaw_usage import OpenClawUsage
            from sqlalchemy import select, func
            
            async with AsyncSessionLocal() as db:
                # Active jobs
                jobs_query = select(func.count(JobPosting.id)).where(
                    JobPosting.status == "discovered"
                )
                jobs_result = await db.execute(jobs_query)
                active_jobs.set(jobs_result.scalar() or 0)
                
                # Active contacts
                contacts_query = select(func.count(Contact.id))
                contacts_result = await db.execute(contacts_query)
                active_contacts.set(contacts_result.scalar() or 0)
                
                # Pending tasks
                tasks_query = select(func.count(AssistantTask.id)).where(
                    AssistantTask.status == "pending"
                )
                tasks_result = await db.execute(tasks_query)
                pending_tasks.set(tasks_result.scalar() or 0)
                
                # Unread emails
                emails_query = select(func.count(EmailThread.id)).where(
                    EmailThread.status == "unread"
                )
                emails_result = await db.execute(emails_query)
                unread_emails.set(emails_result.scalar() or 0)
                
                # Daily cost
                today = datetime.now(timezone.utc).date()
                daily_query = select(func.sum(OpenClawUsage.cost_usd)).where(
                    func.date(OpenClawUsage.created_at) == today
                )
                daily_result = await db.execute(daily_query)
                daily_cost_usd.set(float(daily_result.scalar() or 0))
                
                # Monthly cost
                month_start = datetime.now(timezone.utc).replace(day=1, hour=0, minute=0, second=0)
                monthly_query = select(func.sum(OpenClawUsage.cost_usd)).where(
                    OpenClawUsage.created_at >= month_start
                )
                monthly_result = await db.execute(monthly_query)
                monthly_cost_usd.set(float(monthly_result.scalar() or 0))
        except Exception as e:
            logger.error(f"Failed to update gauges: {e}")
    
    @staticmethod
    def export_metrics() -> bytes:
        """Export metrics in Prometheus format."""
        return generate_latest()


# Global metrics collector
metrics_collector = MetricsCollector()
