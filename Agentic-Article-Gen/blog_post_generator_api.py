from fastapi import FastAPI, HTTPException, BackgroundTasks
from pydantic import BaseModel
from typing import Optional
from blog_post_generator import BlogPostGenerator
from agno.storage.workflow.sqlite import SqliteWorkflowStorage
from agno.utils.log import logger
from celery import Celery
from celery.result import AsyncResult
from datetime import datetime
from celery.exceptions import SoftTimeLimitExceeded

app = FastAPI(
    title="Blog Post Generator API",
    description="API for generating AI-powered blog posts with research and citations",
    version="1.0.0"
)

# Initialize Celery
celery_app = Celery(
    'blog_post_generator',
    broker='redis://redis:6379/0',
    backend='redis://redis:6379/0'
)

# Configure Celery
celery_app.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
    broker_pool_limit=None,
    worker_prefetch_multiplier=1,
    worker_concurrency=4,
    broker_transport_options={
        'master_name': 'mymaster',  # Remove if not using Redis Sentinel
        'socket_timeout': 30,
        'socket_connect_timeout': 30,
        'retry_on_timeout': True,
    },
    redis_max_connections=None,
)

@celery_app.task(name="generate_blog_post_task",
                 bind=True,
                 retry_backoff=True,
                 max_retries=3,
                 soft_time_limit=1800,  # 30 minutes
                 time_limit=2100)       # 35 minutes
def generate_blog_post_task(self, topic: str, use_search_cache: bool, use_scrape_cache: bool, use_cached_report: bool):
    try:
        # Convert topic to URL-safe string
        url_safe_topic = topic.lower().replace(" ", "-")
        
        # Initialize generator with unique database file per worker
        worker_id = celery_app.current_task.request.hostname
        db_file = f"tmp/workflows_{worker_id}.db"
        
        generator = BlogPostGenerator(
            session_id=f"generate-blog-post-on-{url_safe_topic}",
            storage=SqliteWorkflowStorage(
                table_name="generate_blog_post_workflows",
                db_file=db_file,
            ),
        )

        # Execute workflow
        blog_post_iterator = generator.run(
            topic=topic,
            use_search_cache=use_search_cache,
            use_scrape_cache=use_scrape_cache,
            use_cached_report=use_cached_report,
        )

        # Get final response
        final_content = None
        for response in blog_post_iterator:
            final_content = response.content

        if not final_content:
            raise Exception("Failed to generate blog post")

        return {
            "content": final_content,
            "status": "success"
        }

    except Exception as e:
        logger.error(f"Error generating blog post: {str(e)}")
        self.retry(exc=e)
        return {
            "content": None,
            "status": "error",
            "error": str(e)
        }
    except SoftTimeLimitExceeded:
        logger.error("Task timed out after 30 minutes")
        return {
            "content": None,
            "status": "error",
            "error": "Task timed out after 30 minutes"
        }

class BlogPostRequest(BaseModel):
    topic: str
    use_search_cache: bool = True
    use_scrape_cache: bool = True
    use_cached_report: bool = True

class BlogPostResponse(BaseModel):
    task_id: str
    status: str

class BlogPostStatusResponse(BaseModel):
    task_id: str
    status: str
    content: Optional[str] = None
    error: Optional[str] = None

@app.post("/generate-blog", response_model=BlogPostResponse)
async def generate_blog_post(request: BlogPostRequest):
    try:
        # Submit task to Celery
        task = generate_blog_post_task.delay(
            request.topic,
            request.use_search_cache,
            request.use_scrape_cache,
            request.use_cached_report
        )
        
        return BlogPostResponse(
            task_id=task.id,
            status="pending"
        )

    except Exception as e:
        logger.error(f"Error submitting blog post generation task: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/blog-status/{task_id}", response_model=BlogPostStatusResponse)
async def check_blog_status(task_id: str):
    try:
        task_result = AsyncResult(task_id, app=celery_app)
        
        if task_result.state == 'PENDING' and \
           (datetime.now() - task_result.date_done).total_seconds() > 2100:  # 35 minutes
            task_result.revoke(terminate=True)
            return BlogPostStatusResponse(
                task_id=task_id,
                status="failed",
                error="Task timed out and was terminated"
            )
            
        if task_result.ready():
            result = task_result.get()
            if result["status"] == "success":
                return BlogPostStatusResponse(
                    task_id=task_id,
                    status="completed",
                    content=result["content"]
                )
            else:
                return BlogPostStatusResponse(
                    task_id=task_id,
                    status="failed",
                    error=result["error"]
                )
        else:
            return BlogPostStatusResponse(
                task_id=task_id,
                status="pending"
            )

    except Exception as e:
        logger.error(f"Error checking blog post status: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
